"""The app's own notifications (#164): the list a person keeps, and the browsers
that allowed push. What to tell and how it reads is `services/notifier.py`'s."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from bot.util import utcnow_iso

# The list keeps the latest this many per person; older ones go on insert.
KEEP_PER_PERSON = 200
# A browser whose push service keeps refusing is forgotten after this many.
MAX_PUSH_FAILURES = 5


@dataclass(slots=True)
class NotificationRow:
    id: int
    kind: str
    data: dict[str, Any]
    created_at: str
    read_at: str | None


@dataclass(slots=True)
class PushSubscription:
    endpoint: str
    person_id: int
    p256dh: str
    auth: str


class _NotificationsRepo:
    async def add_notification(self, person_id: int, kind: str, data: dict[str, Any]) -> int:
        cursor = await self._conn.execute(
            "INSERT INTO notifications (person_id, kind, data, created_at) VALUES (?, ?, ?, ?)",
            (person_id, kind, json.dumps(data, ensure_ascii=False), utcnow_iso()),
        )
        await self._conn.execute(
            "DELETE FROM notifications WHERE person_id = ? AND id NOT IN ("
            "  SELECT id FROM notifications WHERE person_id = ? ORDER BY id DESC LIMIT ?)",
            (person_id, person_id, KEEP_PER_PERSON),
        )
        await self._conn.commit()
        return int(cursor.lastrowid)

    async def notifications_of(self, person_id: int, limit: int = 50) -> list[NotificationRow]:
        cursor = await self._conn.execute(
            "SELECT id, kind, data, created_at, read_at FROM notifications"
            " WHERE person_id = ? ORDER BY id DESC LIMIT ?",
            (person_id, limit),
        )
        return [
            NotificationRow(
                id=row["id"],
                kind=row["kind"],
                data=json.loads(row["data"] or "{}"),
                created_at=row["created_at"],
                read_at=row["read_at"],
            )
            for row in await cursor.fetchall()
        ]

    async def unread_notifications(self, person_id: int) -> int:
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE person_id = ? AND read_at IS NULL",
            (person_id,),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def mark_notifications_read(self, person_id: int) -> None:
        await self._conn.execute(
            "UPDATE notifications SET read_at = ? WHERE person_id = ? AND read_at IS NULL",
            (utcnow_iso(), person_id),
        )
        await self._conn.commit()

    # ------------------------------------------------------------------ push

    async def save_push_subscription(
        self, person_id: int, endpoint: str, p256dh: str, auth: str, user_agent: str | None
    ) -> None:
        """A browser allowed push. The same browser signing in as somebody else
        moves its subscription to them: one browser, one person."""
        await self._conn.execute(
            "INSERT INTO push_subscriptions"
            " (endpoint, person_id, p256dh, auth, user_agent, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(endpoint) DO UPDATE SET person_id = excluded.person_id,"
            "   p256dh = excluded.p256dh, auth = excluded.auth,"
            "   user_agent = excluded.user_agent, failures = 0",
            (endpoint, person_id, p256dh, auth, user_agent, utcnow_iso()),
        )
        await self._conn.commit()

    async def delete_push_subscription(self, endpoint: str, person_id: int | None = None) -> None:
        if person_id is None:
            await self._conn.execute(
                "DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,)
            )
        else:
            await self._conn.execute(
                "DELETE FROM push_subscriptions WHERE endpoint = ? AND person_id = ?",
                (endpoint, person_id),
            )
        await self._conn.commit()

    async def push_subscriptions_of(self, person_id: int) -> list[PushSubscription]:
        cursor = await self._conn.execute(
            "SELECT endpoint, person_id, p256dh, auth FROM push_subscriptions WHERE person_id = ?",
            (person_id,),
        )
        return [
            PushSubscription(
                endpoint=row["endpoint"],
                person_id=row["person_id"],
                p256dh=row["p256dh"],
                auth=row["auth"],
            )
            for row in await cursor.fetchall()
        ]

    async def push_delivered(self, endpoint: str) -> None:
        await self._conn.execute(
            "UPDATE push_subscriptions SET last_ok_at = ?, failures = 0 WHERE endpoint = ?",
            (utcnow_iso(), endpoint),
        )
        await self._conn.commit()

    async def push_refused(self, endpoint: str) -> None:
        """One more refusal; past MAX_PUSH_FAILURES in a row the browser is forgotten."""
        await self._conn.execute(
            "UPDATE push_subscriptions SET failures = failures + 1 WHERE endpoint = ?", (endpoint,)
        )
        await self._conn.execute(
            "DELETE FROM push_subscriptions WHERE endpoint = ? AND failures >= ?",
            (endpoint, MAX_PUSH_FAILURES),
        )
        await self._conn.commit()
