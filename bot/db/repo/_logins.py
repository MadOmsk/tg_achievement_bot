"""The ways a person signs in besides a Telegram update (#162): an email address
proved with a one-time code, and a Telegram account added to a person who
started elsewhere. The rules — what an address looks like, how long a code
lives, how often one may be sent — are `services/email_login.py`'s; this only
stores."""

from __future__ import annotations

from dataclasses import dataclass

from bot.util import utcnow_iso


@dataclass(slots=True)
class EmailCode:
    id: int
    email: str
    purpose: str
    person_id: int | None
    code_hash: str
    attempts: int
    created_at: str
    expires_at: str


class LoginTaken(Exception):
    """The address or Telegram account already belongs to another person."""


class _LoginsRepo:
    async def person_by_email(self, email: str) -> int | None:
        cursor = await self._conn.execute("SELECT id FROM users WHERE email = ?", (email,))
        row = await cursor.fetchone()
        return int(row["id"]) if row else None

    async def create_email_person(self, email: str) -> int:
        """A new person who arrives by email: no Telegram id, the address as
        their only way in, settings from the admin's defaults like anybody's."""
        now = utcnow_iso()
        cursor = await self._conn.execute(
            "INSERT INTO users (email, email_linked_at, created_at, updated_at)"
            " VALUES (?, ?, ?, ?)",
            (email, now, now, now),
        )
        person = int(cursor.lastrowid)
        default_rarity_mode = await self.get_app_setting("default_rarity_mode", "all")  # type: ignore[attr-defined]
        await self._conn.execute(
            "INSERT OR IGNORE INTO user_settings (person_id, rarity_mode) VALUES (?, ?)",
            (person, default_rarity_mode or "all"),
        )
        await self._conn.commit()
        return person

    async def set_email(self, person_id: int, email: str) -> None:
        """Give a person an address, or a new one in place of the old. Never
        none: email is the main way in (owner, 2026-10-05). Raises LoginTaken
        when another person already signs in with it."""
        owner = await self.person_by_email(email)
        if owner is not None and owner != person_id:
            raise LoginTaken(email)
        now = utcnow_iso()
        await self._conn.execute(
            "UPDATE users SET email = ?, email_linked_at = ?, updated_at = ? WHERE id = ?",
            (email, now, now, person_id),
        )
        await self._conn.commit()

    async def email_prompt_due(self, person_id: int) -> bool:
        """Whether to ask this person for an email on opening the app: they have
        none, and have not put it off."""
        cursor = await self._conn.execute(
            "SELECT 1 FROM users WHERE id = ? AND email IS NULL AND email_prompted_at IS NULL",
            (person_id,),
        )
        return await cursor.fetchone() is not None

    async def put_off_email_prompt(self, person_id: int) -> None:
        await self._conn.execute(
            "UPDATE users SET email_prompted_at = ? WHERE id = ?", (utcnow_iso(), person_id)
        )
        await self._conn.commit()

    async def set_telegram(
        self,
        person_id: int,
        tg_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> None:
        """Add a Telegram account to a person who has none. Raises LoginTaken
        when that Telegram account is already somebody's — joining two people
        is a merge, the person's own request, not a side effect of linking."""
        cursor = await self._conn.execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,))
        row = await cursor.fetchone()
        if row is not None and int(row["id"]) != person_id:
            raise LoginTaken(str(tg_id))
        await self._conn.execute(
            "UPDATE users SET tg_id = ?, username = ?,"
            " first_name = COALESCE(?, first_name), last_name = COALESCE(?, last_name),"
            " updated_at = ? WHERE id = ?",
            (tg_id, username, first_name, last_name, utcnow_iso(), person_id),
        )
        await self._conn.commit()

    async def remove_telegram(self, person_id: int) -> str | None:
        """Take Telegram away from a person (#162): the id, and what came with
        it — the names and photo Telegram gave, the chats (publishing to them
        needs Telegram), and where they were seen writing. The nickname, the
        accounts and their history, the follows all stay. Returns the stored
        photo's path for the caller to delete, if there was one.

        The Telegram account itself is then nobody's: opening the bot again
        makes it a new person. The reset cooldowns keyed by it stay, on purpose
        (they must outlive a person)."""
        cursor = await self._conn.execute(
            "SELECT tg_id, photo_path FROM users WHERE id = ?", (person_id,)
        )
        row = await cursor.fetchone()
        if row is None or row["tg_id"] is None:
            return None
        tg_id = row["tg_id"]
        await self._conn.execute("DELETE FROM subscriptions WHERE person_id = ?", (person_id,))
        await self._conn.execute("DELETE FROM chat_seen WHERE tg_id = ?", (tg_id,))
        await self._conn.execute(
            "UPDATE users SET tg_id = NULL, username = NULL, first_name = NULL,"
            " last_name = NULL, photo_file_id = NULL, photo_unique_id = NULL,"
            " photo_checked_at = NULL, photo_path = NULL, updated_at = ? WHERE id = ?",
            (utcnow_iso(), person_id),
        )
        await self._conn.commit()
        return row["photo_path"]

    # ------------------------------------------------------------------ codes

    async def add_email_code(
        self,
        email: str,
        purpose: str,
        person_id: int | None,
        code_hash: str,
        expires_at: str,
    ) -> None:
        """A new code replaces every earlier unused one for the same address and
        purpose: only the latest email counts."""
        now = utcnow_iso()
        await self._conn.execute(
            "UPDATE email_codes SET used_at = ? "
            "WHERE email = ? AND purpose = ? AND used_at IS NULL",
            (now, email, purpose),
        )
        await self._conn.execute(
            "INSERT INTO email_codes (email, purpose, person_id, code_hash, created_at, expires_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (email, purpose, person_id, code_hash, now, expires_at),
        )
        await self._conn.commit()

    async def email_codes_since(self, email: str, since: str) -> list[str]:
        """When codes were sent to this address since `since`, newest first —
        what the sending limits count."""
        cursor = await self._conn.execute(
            "SELECT created_at FROM email_codes WHERE email = ? AND created_at >= ? "
            "ORDER BY created_at DESC",
            (email, since),
        )
        return [row["created_at"] for row in await cursor.fetchall()]

    async def live_email_code(self, email: str, purpose: str) -> EmailCode | None:
        cursor = await self._conn.execute(
            "SELECT * FROM email_codes WHERE email = ? AND purpose = ? AND used_at IS NULL "
            "ORDER BY id DESC LIMIT 1",
            (email, purpose),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return EmailCode(
            id=row["id"],
            email=row["email"],
            purpose=row["purpose"],
            person_id=row["person_id"],
            code_hash=row["code_hash"],
            attempts=row["attempts"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
        )

    async def take_email_code_attempt(self, code_id: int, max_attempts: int) -> int | None:
        """Spend one guess on a live code before it is compared, and return how
        many have been spent with it; None when none was left (or the code is
        used). Counting first, in one statement, is what holds the limit: a
        check of an earlier read let parallel guesses all see the same count."""
        cursor = await self._conn.execute(
            "UPDATE email_codes SET attempts = attempts + 1 "
            "WHERE id = ? AND used_at IS NULL AND attempts < ? RETURNING attempts",
            (code_id, max_attempts),
        )
        row = await cursor.fetchone()
        await self._conn.commit()
        return int(row["attempts"]) if row else None

    async def use_email_code(self, code_id: int) -> bool:
        """Mark a code used; False when somebody already did — a code proves
        one sign-in, never two."""
        cursor = await self._conn.execute(
            "UPDATE email_codes SET used_at = ? WHERE id = ? AND used_at IS NULL",
            (utcnow_iso(), code_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def forget_old_email_codes(self, before: str) -> None:
        await self._conn.execute("DELETE FROM email_codes WHERE created_at < ?", (before,))
        await self._conn.commit()
