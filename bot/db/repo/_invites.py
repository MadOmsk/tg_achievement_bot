"""Invites (migration 082): codes members make, and who came by each."""

from __future__ import annotations

from dataclasses import dataclass

from bot.db.repo._sql import HANDLE_SHOWN
from bot.util import utcnow_iso


@dataclass(slots=True)
class InviteRow:
    code: str
    created_at: str
    used_by: int | None
    used_at: str | None
    # The nickname of whoever came by it, as shown.
    used_handle: str | None


class _InvitesRepo:
    async def create_invite(self, person_id: int, code: str) -> None:
        await self._conn.execute(
            "INSERT INTO invites (code, created_by, created_at) VALUES (?, ?, ?)",
            (code, person_id, utcnow_iso()),
        )
        await self._conn.commit()

    async def invites_of(self, person_id: int) -> list[InviteRow]:
        """This person's codes, unused first, then newest first."""
        cursor = await self._conn.execute(
            "SELECT i.code, i.created_at, i.used_by, i.used_at, " + HANDLE_SHOWN + " "
            "FROM invites i LEFT JOIN users u ON u.id = i.used_by "
            "WHERE i.created_by = ? "
            "ORDER BY i.used_at IS NOT NULL, COALESCE(i.used_at, i.created_at) DESC",
            (person_id,),
        )
        return [
            InviteRow(
                code=row["code"],
                created_at=row["created_at"],
                used_by=row["used_by"],
                used_at=row["used_at"],
                used_handle=row["handle"] if row["used_by"] is not None else None,
            )
            for row in await cursor.fetchall()
        ]

    async def invite_usable(self, code: str) -> bool:
        cursor = await self._conn.execute(
            "SELECT 1 FROM invites WHERE code = ? AND used_at IS NULL", (code,)
        )
        return await cursor.fetchone() is not None

    async def redeem_invite(self, code: str, person_id: int) -> bool:
        """Spend the code on this person. False when it is unknown or was spent
        a moment ago by somebody else."""
        cursor = await self._conn.execute(
            "UPDATE invites SET used_by = ?, used_at = ? WHERE code = ? AND used_at IS NULL",
            (person_id, utcnow_iso(), code),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def delete_invite(self, person_id: int, code: str) -> bool:
        """Take back an unused code of one's own."""
        cursor = await self._conn.execute(
            "DELETE FROM invites WHERE code = ? AND created_by = ? AND used_at IS NULL",
            (code, person_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0
