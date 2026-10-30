"""A player's own PSN token (owner, 2026-10-29; #233; migration 142).

A token belongs to one PSN account and to the person holding it: it is read
only while that person's link to the account is active, and deleted when the
link goes (unlink, a takeover). The person's deletion cascades. The value is
Fernet text and never leaves `services/psn/personal.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from bot.db.repo._sql import HANDLE_SHOWN
from bot.util import utcnow_iso

# The token counts only while its person holds the account.
_HELD = (
    "EXISTS (SELECT 1 FROM account_links l WHERE l.platform = 'psn'"
    " AND l.external_id = t.account_id AND l.person_id = t.person_id AND l.is_active = 1)"
)


@dataclass(frozen=True, slots=True)
class PsnTokenRow:
    account_id: str
    person_id: int
    npsso_enc: bytes
    status: str
    verified_at: str
    checked_at: str | None
    dead_at: str | None
    last_error: str | None
    notify_count: int
    last_notified_at: str | None


def _row(row) -> PsnTokenRow:
    return PsnTokenRow(
        account_id=row["account_id"],
        person_id=row["person_id"],
        npsso_enc=bytes(row["npsso_enc"]),
        status=row["status"],
        verified_at=row["verified_at"],
        checked_at=row["checked_at"],
        dead_at=row["dead_at"],
        last_error=row["last_error"],
        notify_count=row["notify_count"],
        last_notified_at=row["last_notified_at"],
    )


class _PsnTokensRepo:
    async def save_psn_token(self, account_id: str, person_id: int, npsso_enc: bytes) -> None:
        """A checked token, replacing any the account had."""
        now = utcnow_iso()
        await self._conn.execute(
            "INSERT INTO psn_tokens (account_id, person_id, npsso_enc, status, verified_at,"
            " checked_at) VALUES (?, ?, ?, 'active', ?, ?)"
            " ON CONFLICT (account_id) DO UPDATE SET person_id = excluded.person_id,"
            " npsso_enc = excluded.npsso_enc, status = 'active',"
            " verified_at = excluded.verified_at, checked_at = excluded.checked_at,"
            " dead_at = NULL, last_error = NULL, notify_count = 0, last_notified_at = NULL",
            (account_id, person_id, npsso_enc, now, now),
        )
        await self._conn.commit()

    async def psn_token(self, account_id: str) -> PsnTokenRow | None:
        """The account's token while its person still holds the account."""
        cursor = await self._conn.execute(
            f"SELECT t.* FROM psn_tokens t WHERE t.account_id = ? AND {_HELD}", (account_id,)
        )
        row = await cursor.fetchone()
        return _row(row) if row else None

    async def psn_tokens_of(self, person_id: int) -> list[PsnTokenRow]:
        cursor = await self._conn.execute(
            f"SELECT t.* FROM psn_tokens t WHERE t.person_id = ? AND {_HELD}"
            " ORDER BY t.verified_at",
            (person_id,),
        )
        return [_row(r) for r in await cursor.fetchall()]

    async def active_psn_tokens(self) -> list[PsnTokenRow]:
        cursor = await self._conn.execute(
            f"SELECT t.* FROM psn_tokens t WHERE t.status = 'active' AND {_HELD}"
            " ORDER BY t.checked_at"
        )
        return [_row(r) for r in await cursor.fetchall()]

    async def personal_psn_accounts(self) -> set[str]:
        """The PSN accounts read with their own live token."""
        return {row.account_id for row in await self.active_psn_tokens()}

    async def psn_token_overview(self) -> list[dict]:
        """Every token of an account still held, for the admin's list (#233):
        the account, its holder, the state — never the token."""
        cursor = await self._conn.execute(
            "SELECT t.account_id, t.person_id, t.status, t.checked_at, t.dead_at,"
            f" a.display_name, {HANDLE_SHOWN}"
            " FROM psn_tokens t"
            " LEFT JOIN accounts a ON a.platform = 'psn' AND a.external_id = t.account_id"
            " LEFT JOIN users u ON u.id = t.person_id"
            f" WHERE {_HELD} ORDER BY t.status, a.display_name"
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def psn_accounts_without_token(self) -> int:
        """Linked PSN accounts read with the shared token."""
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM account_links l WHERE l.platform = 'psn' AND l.is_active = 1"
            " AND NOT EXISTS (SELECT 1 FROM psn_tokens t WHERE t.account_id = l.external_id"
            " AND t.person_id = l.person_id AND t.status = 'active')"
        )
        return int((await cursor.fetchone())[0])

    async def dead_psn_tokens(self) -> list[PsnTokenRow]:
        cursor = await self._conn.execute(
            f"SELECT t.* FROM psn_tokens t WHERE t.status = 'dead' AND {_HELD}"
        )
        return [_row(r) for r in await cursor.fetchall()]

    async def psn_token_counts(self) -> tuple[int, int]:
        """(alive, dead) tokens of accounts still held — the admin's summary."""
        cursor = await self._conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN t.status = 'active' THEN 1 ELSE 0 END), 0),"
            " COALESCE(SUM(CASE WHEN t.status = 'dead' THEN 1 ELSE 0 END), 0)"
            f" FROM psn_tokens t WHERE {_HELD}"
        )
        alive, dead = await cursor.fetchone()
        return int(alive), int(dead)

    async def mark_psn_token_checked(self, account_id: str) -> None:
        await self._conn.execute(
            "UPDATE psn_tokens SET checked_at = ? WHERE account_id = ?",
            (utcnow_iso(), account_id),
        )
        await self._conn.commit()

    async def mark_psn_token_dead(self, account_id: str, error: str) -> bool:
        """True when this turned a live token dead, so its owner is told once."""
        now = utcnow_iso()
        cursor = await self._conn.execute(
            "UPDATE psn_tokens SET status = 'dead', dead_at = ?, checked_at = ?, last_error = ?"
            " WHERE account_id = ? AND status = 'active'",
            (now, now, error[:200], account_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def note_psn_token_reminder(self, account_id: str) -> None:
        await self._conn.execute(
            "UPDATE psn_tokens SET notify_count = notify_count + 1, last_notified_at = ?"
            " WHERE account_id = ?",
            (utcnow_iso(), account_id),
        )
        await self._conn.commit()

    async def delete_psn_token(self, account_id: str) -> None:
        await self._conn.execute("DELETE FROM psn_tokens WHERE account_id = ?", (account_id,))
        await self._conn.commit()

    async def forget_unheld_psn_tokens(self) -> int:
        """Tokens of accounts their person no longer holds (unlinked, taken
        over): a credential never follows an account to somebody else."""
        cursor = await self._conn.execute(f"DELETE FROM psn_tokens AS t WHERE NOT {_HELD}")
        await self._conn.commit()
        return cursor.rowcount
