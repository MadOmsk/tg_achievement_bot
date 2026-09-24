"""Connection lifecycle and schema/migration bring-up — split out of what
used to be one 2900-line bot/db/repo.py (2026-09-09); see this package's
own __init__.py for the full picture. Behavior is unchanged.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Self

import aiosqlite

from bot.constants import SettingKey
from bot.util import utcnow_iso
from bot.version import schema_gap

log = logging.getLogger(__name__)

# bot/db/repo/_database.py -> parent is bot/db/repo/, parent.parent is
# bot/db/ — schema.sql and migrations/ live there, one level up from this
# subpackage, unchanged by the 2026-09-09 split.
_DB_DIR = Path(__file__).parent.parent
SCHEMA_PATH = _DB_DIR / "schema.sql"
MIGRATIONS_DIR = _DB_DIR / "migrations"

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


class Database:
    """Owns the connection and brings the file up to the current schema."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("database is not connected")
        return self._conn

    async def connect(self) -> Self:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        # WAL keeps the poller writing while a panel reads; foreign keys are off
        # by default in SQLite and our ON DELETE CASCADE depends on them.
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA busy_timeout = 30000")
        try:
            # Whether this file had anything in it *before* schema.sql ran —
            # see _apply_migrations for why that one bit matters.
            fresh = await self._is_empty()
            await self._refuse_a_newer_database()
            await self._apply_schema()
            await self._apply_migrations(fresh=fresh)
            await self._seed_app_settings()
            await self._conn.commit()
        except BaseException:
            # Bring-up failing has to *stop* the process, and until this
            # existed it hung it instead: aiosqlite runs its own worker
            # thread, and a connection left open keeps a non-daemon thread
            # alive after the exception has unwound everything else — the
            # bot neither serves nor exits. Found while testing the
            # fail-fast path added in #56, which is precisely the path that
            # has to end in a clean exit.
            await self.close()
            raise
        return self

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _is_empty(self) -> bool:
        cursor = await self.conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'  AND name NOT LIKE 'sqlite_%'"
        )
        row = await cursor.fetchone()
        return (row[0] if row else 0) == 0

    async def _refuse_a_newer_database(self) -> None:
        """Stop before touching a database that a *newer* build has already
        migrated (#56).

        This is the 2026-09-14 outage in one check. A script run out of the
        accounts-52 worktree opened production's bot.db, `connect()` applied
        that branch's migrations to it, and the production bot — older code,
        on main — then crashed on tables it had never heard of. Every step
        was reasonable on its own; nothing compared the two.

        Only "database ahead of code" is fatal. Behind is the normal state
        of an upgrade and is what the migrations below are for.
        """
        cursor = await self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        )
        if await cursor.fetchone() is None:
            return  # nothing has ever been applied here
        cursor = await self.conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        complaint = schema_gap(row["version"] if row else None)
        if complaint is not None:
            raise SchemaTooNewError(complaint)

    async def _apply_schema(self) -> None:
        await self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    async def _apply_migrations(self, *, fresh: bool = False) -> None:
        """Bring an existing database up to the current schema.

        A brand-new one is *baselined* instead: schema.sql already created
        the current shape, so its migrations are recorded as applied without
        being run (2026-09-12). Running them was the older behaviour and it
        quietly constrained every migration ever written — each had to stay
        executable against the finished schema as well as against the older
        one it was written for, which is impossible the moment a migration
        reads a column that a later one removes. That trap was hit three
        times in two days (#52): a column renamed, a table dropped, and
        finally `users.xuid` moving out to `accounts`, where there was no
        way to write 037 so that it also parsed against a schema without
        that column.

        The bit that decides is "was the file empty before schema.sql ran",
        not "does schema_migrations exist" — a database old enough to
        predate that table must still have its migrations applied.
        """
        await self.conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "  version TEXT PRIMARY KEY,"
            "  applied_at TEXT NOT NULL)"
        )
        cursor = await self.conn.execute("SELECT version FROM schema_migrations")
        applied = {row["version"] for row in await cursor.fetchall()}

        if not MIGRATIONS_DIR.exists():
            return
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.stem in applied:
                continue
            if fresh:
                log.info("baselining migration %s (new database)", path.stem)
            else:
                log.info("applying migration %s", path.stem)
                await self._apply_one(path)
            await self.conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (path.stem, utcnow_iso()),
            )

    async def _apply_one(self, path: Path) -> None:
        """One migration, with the one collision schema.sql can cause.

        A database that skips several versions at once meets both halves of
        the bring-up: schema.sql runs first and creates every table that does
        not exist yet — in its *finished* shape — and only then do the
        migrations run. So a migration that creates a table and a later one
        that adds a column to it are fine on a database old enough to have
        neither (the table is made whole, both are skipped in effect) and fine
        on one that has the table already... except that the ADD COLUMN then
        hits a column schema.sql just put there.

        Found by rehearsing the accounts-52 merge against a copy of production
        (2026-09-16): `title_groups` did not exist there, schema.sql created it
        with `name_ru`, and 044 died on "duplicate column name: name_ru" —
        which would have been the production deploy, not a rehearsal.

        Only that one error is swallowed, and it is logged: it means the column
        is already exactly where the migration wanted it.
        """
        # A local file of a few kilobytes, read once at startup before the
        # bot serves anything — the blocking read ASYNC240 warns about is
        # what this has always done, just now one call further in.
        script = path.read_text(encoding="utf-8")  # noqa: ASYNC240
        try:
            await self.conn.executescript(script)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc):
                raise
            log.info("migration %s: %s — schema.sql had already added it", path.stem, exc)

    async def _seed_app_settings(self) -> None:
        for key, value in DEFAULT_APP_SETTINGS.items():
            await self.conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, utcnow_iso()),
            )
