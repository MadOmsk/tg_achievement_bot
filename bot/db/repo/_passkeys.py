"""Passkeys (owner, 2026-10-08; migration 089): the public half of a key a
person keeps on a phone or a computer, and how often it has signed in."""

from __future__ import annotations

from dataclasses import dataclass

from bot.util import utcnow_iso


@dataclass(frozen=True, slots=True)
class PasskeyRow:
    id: str
    person_id: int
    public_key: bytes
    sign_count: int
    transports: list[str]
    name: str | None
    created_at: str
    last_used_at: str | None


def _row(row) -> PasskeyRow:
    return PasskeyRow(
        id=row["id"],
        person_id=row["person_id"],
        public_key=bytes(row["public_key"]),
        sign_count=row["sign_count"],
        transports=[t for t in (row["transports"] or "").split(",") if t],
        name=row["name"],
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
    )


class _PasskeysRepo:
    async def add_passkey(
        self,
        person_id: int,
        credential_id: str,
        public_key: bytes,
        sign_count: int,
        transports: list[str],
        name: str | None,
    ) -> None:
        await self._conn.execute(
            "INSERT INTO passkeys (id, person_id, public_key, sign_count, transports, name,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                credential_id,
                person_id,
                public_key,
                sign_count,
                ",".join(transports) or None,
                (name or "")[:80] or None,
                utcnow_iso(),
            ),
        )
        await self._conn.commit()

    async def passkeys_of(self, person_id: int) -> list[PasskeyRow]:
        cursor = await self._conn.execute(
            "SELECT * FROM passkeys WHERE person_id = ? ORDER BY created_at", (person_id,)
        )
        return [_row(row) for row in await cursor.fetchall()]

    async def passkey(self, credential_id: str) -> PasskeyRow | None:
        cursor = await self._conn.execute("SELECT * FROM passkeys WHERE id = ?", (credential_id,))
        row = await cursor.fetchone()
        return _row(row) if row else None

    async def passkey_used(self, credential_id: str, sign_count: int) -> None:
        """A sign-in by this key: its new count, and when."""
        await self._conn.execute(
            "UPDATE passkeys SET sign_count = ?, last_used_at = ? WHERE id = ?",
            (sign_count, utcnow_iso(), credential_id),
        )
        await self._conn.commit()

    async def delete_passkey(self, person_id: int, credential_id: str) -> bool:
        """Only one's own key; False when there was none such."""
        cursor = await self._conn.execute(
            "DELETE FROM passkeys WHERE id = ? AND person_id = ?", (credential_id, person_id)
        )
        await self._conn.commit()
        return cursor.rowcount > 0
