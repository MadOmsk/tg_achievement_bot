"""Browser sessions (#157, migration 074): what a Telegram Login in a plain
browser leaves behind. The token itself is only ever in the person's cookie."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from bot.util import parse_iso, utcnow, utcnow_iso

SESSION_DAYS = 30
# Touching `last_seen_at` on every request would be a write per click.
_TOUCH_AFTER = timedelta(hours=6)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class _SessionsRepo:
    async def create_session(self, person_id: int, user_agent: str | None) -> str:
        """A new session; returns the token to put in the cookie."""
        token = secrets.token_urlsafe(32)
        now = utcnow()
        await self._conn.execute(
            "INSERT INTO web_sessions (token_hash, person_id, created_at, last_seen_at,"
            " expires_at, user_agent) VALUES (?, ?, ?, ?, ?, ?)",
            (
                _hash(token),
                person_id,
                now.isoformat(timespec="seconds"),
                now.isoformat(timespec="seconds"),
                (now + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds"),
                (user_agent or "")[:200] or None,
            ),
        )
        await self._conn.commit()
        return token

    async def session_person(self, token: str) -> int | None:
        """The person behind a live session, or None (unknown or expired)."""
        cursor = await self._conn.execute(
            "SELECT token_hash, expires_at, last_seen_at, person_id "
            "FROM web_sessions WHERE token_hash = ?",
            (_hash(token),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        expires = parse_iso(row["expires_at"])
        if expires is None or expires <= utcnow():
            await self.end_session(token)
            return None
        seen = parse_iso(row["last_seen_at"])
        if seen is None or utcnow() - seen > _TOUCH_AFTER:
            await self._conn.execute(
                "UPDATE web_sessions SET last_seen_at = ? WHERE token_hash = ?",
                (utcnow_iso(), row["token_hash"]),
            )
            await self._conn.commit()
        return row["person_id"]

    async def end_session(self, token: str) -> None:
        await self._conn.execute("DELETE FROM web_sessions WHERE token_hash = ?", (_hash(token),))
        await self._conn.commit()
