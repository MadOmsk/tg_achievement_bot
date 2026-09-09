"""Connection lifecycle and schema/migration bring-up — split out of what
used to be one 2900-line bot/db/repo.py (2026-09-09); see this package's
own __init__.py for the full picture. Behavior is unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Self

import aiosqlite

from bot.constants import SettingKey
from bot.util import utcnow_iso

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
    # leaderboard, games in /stats' "Игры за 30 дней".
    SettingKey.SUMMARY_TOP_LIMIT: "15",
    SettingKey.STATS_GAMES_LIMIT: "15",
    # /hltb's own two: how many candidates search() and the recent-games
    # shortcuts pool from, and how many of them show per page (6.4, 6.6).
    SettingKey.HLTB_RESULTS_LIMIT: "20",
    SettingKey.HLTB_PAGE_SIZE: "5",
}


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
        await self._apply_schema()
        await self._apply_migrations()
        await self._seed_app_settings()
        await self._conn.commit()
        return self

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _apply_schema(self) -> None:
        await self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    async def _apply_migrations(self) -> None:
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
            log.info("applying migration %s", path.stem)
            await self.conn.executescript(path.read_text(encoding="utf-8"))
            await self.conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (path.stem, utcnow_iso()),
            )

    async def _seed_app_settings(self) -> None:
        for key, value in DEFAULT_APP_SETTINGS.items():
            await self.conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, utcnow_iso()),
            )
