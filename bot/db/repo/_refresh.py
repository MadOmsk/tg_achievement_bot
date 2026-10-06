"""The two self-refreshing screens' rows (#167): `/online` per chat
(`online_auto_refresh`, poller/online_refresh.py) and `/admin` per admin
(`admin_panel_refresh`, poller/admin_refresh.py). Both tables have one shape —
a key, the message being redrawn, when it started (the cutoff's clock) and when
it was last redrawn — so one set of statements serves both; the mixins keep
their own names."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.db.repo._models import AdminPanelRefreshRow, OnlineAutoRefreshRow
from bot.util import utcnow_iso


@dataclass(frozen=True)
class RefreshTable:
    table: str
    key: str
    row: type

    def _as_row(self, row: Any) -> Any:
        return self.row(
            **{self.key: row[self.key]},
            message_id=row["message_id"],
            created_at=row["created_at"],
            last_updated_at=row["last_updated_at"],
        )

    async def get(self, conn: Any, key: int) -> Any | None:
        cursor = await conn.execute(
            f"SELECT {self.key}, message_id, created_at, last_updated_at "
            f"FROM {self.table} WHERE {self.key} = ?",
            (key,),
        )
        row = await cursor.fetchone()
        return self._as_row(row) if row else None

    async def start(self, conn: Any, key: int, message_id: int) -> None:
        """A new copy supersedes the one before: the row points at the new
        message and both timestamps start again."""
        now = utcnow_iso()
        await conn.execute(
            f"INSERT INTO {self.table} ({self.key}, message_id, created_at, last_updated_at) "
            "VALUES (?, ?, ?, ?) "
            f"ON CONFLICT({self.key}) DO UPDATE SET"
            " message_id = excluded.message_id, created_at = excluded.created_at,"
            " last_updated_at = excluded.last_updated_at",
            (key, message_id, now, now),
        )
        await conn.commit()

    async def touch(self, conn: Any, key: int) -> None:
        await conn.execute(
            f"UPDATE {self.table} SET last_updated_at = ? WHERE {self.key} = ?",
            (utcnow_iso(), key),
        )
        await conn.commit()

    async def delete(self, conn: Any, key: int) -> None:
        await conn.execute(f"DELETE FROM {self.table} WHERE {self.key} = ?", (key,))
        await conn.commit()

    async def all(self, conn: Any) -> list[Any]:
        cursor = await conn.execute(
            f"SELECT {self.key}, message_id, created_at, last_updated_at FROM {self.table}"
        )
        return [self._as_row(row) for row in await cursor.fetchall()]


ONLINE = RefreshTable("online_auto_refresh", "chat_id", OnlineAutoRefreshRow)
ADMIN_PANEL = RefreshTable("admin_panel_refresh", "admin_id", AdminPanelRefreshRow)
