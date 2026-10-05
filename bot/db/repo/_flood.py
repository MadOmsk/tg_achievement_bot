"""Anti-flood throttle state — `notification_throttle` (2026-09-09 user
request). One mixin of bot.db.repo.Repo (2026-09-09 split; see this
package's own __init__.py). See schema.sql's own comment on the table and
poller/flood_flush.py for the mechanism this backs.
"""

from __future__ import annotations

from datetime import datetime

from bot.db.repo._models import FloodState
from bot.util import parse_iso


class _FloodRepo:
    async def get_flood_state(self, tg_id: int, chat_id: int) -> FloodState | None:
        cursor = await self._conn.execute(
            "SELECT window_started_at, count_in_window, throttled FROM notification_throttle "
            "WHERE tg_id = ? AND chat_id = ?",
            (tg_id, chat_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        started = parse_iso(row["window_started_at"])
        assert started is not None  # column is NOT NULL, always our own utcnow_iso()
        return FloodState(
            tg_id=tg_id,
            chat_id=chat_id,
            window_started_at=started,
            count_in_window=row["count_in_window"],
            throttled=bool(row["throttled"]),
        )

    async def set_flood_state(
        self,
        tg_id: int,
        chat_id: int,
        *,
        window_started_at: datetime,
        count_in_window: int,
        throttled: bool,
    ) -> None:
        await self._conn.execute(
            "INSERT INTO notification_throttle"
            " (tg_id, chat_id, window_started_at, count_in_window, throttled) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(tg_id, chat_id) DO UPDATE SET"
            " window_started_at = excluded.window_started_at,"
            " count_in_window = excluded.count_in_window,"
            " throttled = excluded.throttled",
            (
                tg_id,
                chat_id,
                window_started_at.isoformat(timespec="seconds"),
                count_in_window,
                1 if throttled else 0,
            ),
        )
        await self._conn.commit()

    async def clear_flood_state(self, tg_id: int, chat_id: int) -> None:
        await self._conn.execute(
            "DELETE FROM notification_throttle WHERE tg_id = ? AND chat_id = ?", (tg_id, chat_id)
        )
        await self._conn.commit()

    async def throttled_flood_states(self) -> list[FloodState]:
        """Every (person, chat) currently buffering instead of posting —
        poller/flood_flush.py's own sweep, both its per-minute tick and the
        forced sweeps (startup, 5 minutes before a chat's daily summary).
        A `throttled = 0` row (still just counting, nothing buffered yet)
        never needs attention here — it either keeps counting or lapses and
        gets silently replaced next time an achievement arrives
        (publisher.py's own job, not this one)."""
        cursor = await self._conn.execute(
            "SELECT tg_id, chat_id, window_started_at, count_in_window FROM notification_throttle "
            "WHERE throttled = 1"
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            started = parse_iso(row["window_started_at"])
            assert started is not None  # column is NOT NULL, always our own utcnow_iso()
            result.append(
                FloodState(
                    tg_id=row["tg_id"],
                    chat_id=row["chat_id"],
                    window_started_at=started,
                    count_in_window=row["count_in_window"],
                    throttled=True,
                )
            )
        return result
