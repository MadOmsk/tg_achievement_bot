"""Connection lifecycle and schema/migration bring-up, on PostgreSQL (#234).

One database, three schemas: the server's own (`prod`, `test`, `dev`, …: its
people, accounts, chats and settings) and `games`, the catalog the servers
share (#229). The connection's search path is "<server>, games", so a table
nobody qualified is found in the server's schema first, then in the catalog —
what attaching the games file did on SQLite — and queries are as they were.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Self

from bot.constants import SettingKey
from bot.db.postgres import Connection
from bot.db.repo._games_db import GAMES
from bot.db.repo._tx import TransactionGate
from bot.util import utcnow_iso
from bot.version import schema_gap

log = logging.getLogger(__name__)

_PG_DIR = Path(__file__).parent.parent / "pg"
APP_SCHEMA_PATH = _PG_DIR / "app.sql"
GAMES_SCHEMA_PATH = _PG_DIR / "games.sql"
MIGRATIONS_DIR = _PG_DIR / "migrations"

DEFAULT_APP_SETTINGS: dict[str, str] = {
    # Row caps for the game/player tables (SPEC 6.3, 6.6, 7.2) — separate
    # settings because they cap different things: players in /summary's
    # leaderboard, games in /stats' own list.
    SettingKey.SUMMARY_TOP_LIMIT: "15",
    SettingKey.STATS_GAMES_LIMIT: "15",
    # /hltb's own two: how many candidates search() and the recent-games
    # shortcuts pool from, and how many of them show per page (6.4, 6.6).
    SettingKey.HLTB_RESULTS_LIMIT: "20",
    SettingKey.HLTB_PAGE_SIZE: "5",
}


class SchemaTooNewError(RuntimeError):
    """The database has migrations this code does not ship (#56)."""


class EmptySchemaError(RuntimeError):
    """A bot asked to start on a schema nothing was imported into."""


class Database:
    """Owns the connection and brings the schemas up to the current shape."""

    def __init__(
        self, dsn: str, *, schema: str, data_dir: Path | None = None, new_ok: bool = True
    ) -> None:
        self._new_ok = new_ok
        self._dsn = dsn
        self.schema = schema
        # Where the server keeps its files beside the database (the advisers'
        # answers, the lock): the folder `DB_PATH` used to name.
        self.data_dir = data_dir or Path("data")
        self._conn: Connection | None = None
        # Who holds the connection for a block of writes (#167, `_tx.py`).
        self.gate = TransactionGate()

    @property
    def conn(self) -> Connection:
        if self._conn is None:
            raise RuntimeError("database is not connected")
        return self._conn

    async def connect(self) -> Self:
        self._conn = await Connection.connect(self._dsn, search_path=f"{self.schema},{GAMES}")
        try:
            await self.conn.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
            await self.conn.execute(f"CREATE SCHEMA IF NOT EXISTS {GAMES}")
            fresh = not await self._has_tables(self.schema)
            if fresh and not self._new_ok:
                raise EmptySchemaError(
                    f"schema {self.schema} has no tables: its import has not run. Refusing to"
                    " start on an empty database; DATABASE_NEW_OK=true makes a new one"
                )
            await self._refuse_a_newer_database()
            if not await self._has_tables(GAMES):
                log.info("making the games catalog's schema")
                await self._run_in(GAMES, GAMES_SCHEMA_PATH)
            if fresh:
                log.info("making schema %s", self.schema)
                await self._run_in(self.schema, APP_SCHEMA_PATH)
            await self._apply_migrations(fresh=fresh)
            await self._seed_app_settings()
        except BaseException:
            # Bring-up failing has to *stop* the process: a connection left
            # open would keep the bot from exiting cleanly (#56).
            await self.close()
            raise
        return self

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _has_tables(self, schema: str) -> bool:
        cursor = await self.conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = ? LIMIT 1", (schema,)
        )
        return await cursor.fetchone() is not None

    async def _run_in(self, schema: str, script: Path) -> None:
        """A schema file, its tables created in `schema`."""
        # A local file, read once at startup before the bot serves anything.
        sql = script.read_text(encoding="utf-8")  # noqa: ASYNC240
        await self.conn.executescript(
            f"BEGIN; SET LOCAL search_path TO {schema}, {GAMES};\n{sql}\nCOMMIT;"
        )

    async def _refuse_a_newer_database(self) -> None:
        """Stop before touching a database that a *newer* build has already
        migrated (#56). Behind is the normal state of an upgrade and is what
        the migrations are for; only "database ahead of code" is fatal."""
        if not await self._has_table(self.schema, "schema_migrations"):
            return
        cursor = await self.conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        complaint = schema_gap(row["version"] if row else None)
        if complaint is not None:
            raise SchemaTooNewError(complaint)

    async def _has_table(self, schema: str, table: str) -> bool:
        cursor = await self.conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
            (schema, table),
        )
        return await cursor.fetchone() is not None

    async def _apply_migrations(self, *, fresh: bool = False) -> None:
        """Bring an existing schema up to the current shape.

        A brand-new one is *baselined* instead: app.sql already made the
        current shape, so the migrations are recorded as applied without
        running. A migration runs with the search path "<server>, games": what
        it creates unqualified lands in the server's schema, the catalog's is
        written `games.<name>` — and, the catalog being shared, only ever
        added to, idempotently (#229).
        """
        cursor = await self.conn.execute("SELECT version FROM schema_migrations")
        applied = {row["version"] for row in await cursor.fetchall()}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.stem in applied:
                continue
            if fresh:
                log.info("baselining migration %s (new schema)", path.stem)
            else:
                log.info("applying migration %s", path.stem)
                # A local file of a few kilobytes, read once at startup.
                script = path.read_text(encoding="utf-8")
                # Its record in its own transaction: a crash between the two
                # would run it again, and a plain ADD COLUMN would then stop
                # every start.
                await self.conn.executescript(
                    f"BEGIN;\n{script}\nINSERT INTO schema_migrations (version, applied_at)"
                    f" VALUES ('{path.stem}', '{utcnow_iso()}');\nCOMMIT;"
                )
                continue
            await self.conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (path.stem, utcnow_iso()),
            )

    async def _seed_app_settings(self) -> None:
        for key, value in DEFAULT_APP_SETTINGS.items():
            await self.conn.execute(
                "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)"
                " ON CONFLICT DO NOTHING",
                (key, value, utcnow_iso()),
            )
