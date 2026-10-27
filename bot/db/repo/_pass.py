"""The season pass: the themes each person claimed (131)."""

from __future__ import annotations

from bot.util import utcnow


class _PassRepo:
    async def pass_claims(self, person_id: int) -> set[str]:
        cursor = await self._conn.execute(
            "SELECT palette FROM pass_claims WHERE person_id = ?", (person_id,)
        )
        return {row[0] for row in await cursor.fetchall()}

    async def set_pass_claim(self, person_id: int, palette: str, month: str, on: bool) -> None:
        if on:
            await self._conn.execute(
                "INSERT OR IGNORE INTO pass_claims (person_id, palette, month, claimed_at)"
                " VALUES (?, ?, ?, ?)",
                (person_id, palette, month, utcnow().isoformat(timespec="seconds")),
            )
        else:
            await self._conn.execute(
                "DELETE FROM pass_claims WHERE person_id = ? AND palette = ?",
                (person_id, palette),
            )
        await self._conn.commit()
