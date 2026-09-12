"""Users, Xbox tokens, per-user settings, and admin-wide app settings —
one mixin of bot.db.repo.Repo (2026-09-09 split; see this package's own
__init__.py). Behavior is unchanged from before the split.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from bot.constants import AccountPlatform, TokenStatus
from bot.db.repo._models import (
    TokenRecord,
    User,
    UserSettings,
    _as_token,
    _as_user,
    _as_user_settings,
)
from bot.i18n import DEFAULT_LOCALE
from bot.util import utcnow, utcnow_iso


class _AccountsRepo:
    # ---------------------------------------------------------------- users

    async def ensure_user(
        self,
        tg_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> None:
        """Create the user and his settings row on first contact.
        first_name/last_name (Follow-up 2026-09-06, /stats' header) are
        optional here on purpose — most call sites only ever had a username
        to pass before this existed, and the message middleware
        (handlers/chat.py) backfills both from this person's very next
        message regardless."""
        now = utcnow_iso()
        await self._conn.execute(
            "INSERT INTO users (tg_id, username, first_name, last_name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(tg_id) DO UPDATE SET "
            "  username = COALESCE(excluded.username, users.username),"
            "  first_name = COALESCE(excluded.first_name, users.first_name),"
            "  last_name = COALESCE(excluded.last_name, users.last_name),"
            "  updated_at = excluded.updated_at",
            (tg_id, username, first_name, last_name, now, now),
        )
        # show_profile_links is explicit here, not left to the column's own
        # DEFAULT 0 — same move as subscribe()'s default_rarity_mode: an
        # admin-configurable starting point (app_settings
        # ['default_show_profile_links'], handlers/admin.py) decides it for
        # a brand-new person instead of a value baked into the schema. The
        # column default stays 0 regardless, as a safety net for any insert
        # that (today or in the future) doesn't go through this method.
        default_show_links = await self.get_int_setting("default_show_profile_links", 0)
        await self._conn.execute(
            "INSERT OR IGNORE INTO user_settings (tg_id, show_profile_links) VALUES (?, ?)",
            (tg_id, default_show_links),
        )
        await self._conn.commit()

    async def update_username(self, tg_id: int, username: str) -> None:
        await self._conn.execute(
            "UPDATE users SET username = ? WHERE tg_id = ? AND IFNULL(username, '') <> ?",
            (username, tg_id, username),
        )
        await self._conn.commit()

    async def update_names(self, tg_id: int, first_name: str | None, last_name: str | None) -> None:
        """first_name/last_name's own refresh (Follow-up 2026-09-06,
        /stats' header) — separate from update_username above because
        Telegram always sends first_name (called unconditionally from the
        message middleware), unlike username which can be absent."""
        await self._conn.execute(
            "UPDATE users SET "
            "  first_name = COALESCE(?, first_name), last_name = COALESCE(?, last_name) "
            "WHERE tg_id = ?",
            (first_name, last_name, tg_id),
        )
        await self._conn.commit()

    async def get_user(self, tg_id: int) -> User | None:
        cursor = await self._conn.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
        row = await cursor.fetchone()
        return _as_user(row) if row else None

    async def get_user_by_xuid(self, xuid: str) -> User | None:
        cursor = await self._conn.execute("SELECT * FROM users WHERE xuid = ?", (xuid,))
        row = await cursor.fetchone()
        return _as_user(row) if row else None

    async def link_xbox_account(
        self, tg_id: int, xuid: str, gamertag: str | None, gamerscore: int | None
    ) -> int | None:
        """Link an Xbox account, through the same `accounts`/`account_links`
        pair every other platform uses since #52 — Xbox is one account and
        one platform here, both generations together.

        `users.xuid`/`gamertag`/`gamerscore` are still written as a cache of
        the active link, because ~70 Xbox call sites still read them; they
        are scheduled to go in the follow-up step, and this is the single
        writer keeping them true in the meantime.

        Returns the tg_id the account was taken from, when somebody else was
        holding it — same contract as `link_platform_account`.
        """
        taken_from = await self.link_platform_account(tg_id, AccountPlatform.XBOX, xuid, gamertag)
        if taken_from is not None:
            # The cache on the previous owner has to go with the account, or
            # they would keep polling and displaying an account that is no
            # longer theirs.
            await self._conn.execute(
                "UPDATE users SET xuid = NULL, updated_at = ? WHERE tg_id = ?",
                (utcnow_iso(), taken_from),
            )
        await self._conn.execute(
            "UPDATE users SET xuid = ?, gamertag = ?, gamerscore = ?, updated_at = ? "
            "WHERE tg_id = ?",
            (xuid, gamertag, gamerscore, utcnow_iso(), tg_id),
        )
        await self._conn.execute(
            "UPDATE accounts SET gamerscore = COALESCE(?, gamerscore), updated_at = ? "
            "WHERE platform = ? AND external_id = ?",
            (gamerscore, utcnow_iso(), AccountPlatform.XBOX, xuid),
        )
        await self._conn.commit()
        return taken_from

    async def unlink_xbox_account(self, tg_id: int) -> None:
        """/disconnect_xbox: the link is deactivated, the account and
        everything it earned stay (SPEC 6.1, and #52's own rule — relinking
        later finds its history waiting instead of paying for a backfill)."""
        await self.unlink_platform_account(tg_id, AccountPlatform.XBOX)
        await self._conn.execute(
            "UPDATE users SET xuid = NULL, updated_at = ? WHERE tg_id = ?",
            (utcnow_iso(), tg_id),
        )
        await self._conn.commit()

    # --------------------------------------------------------------- tokens

    async def save_refresh_token(self, tg_id: int, token_enc: bytes) -> None:
        """Store a fresh token and clear the failure state.

        Called both on first connect and on every refresh — SPEC 5.1 requires
        the new token to reach the database *before* the request that uses it.
        """
        now = utcnow_iso()
        await self._conn.execute(
            "INSERT INTO tokens (tg_id, refresh_token_enc, status, created_at, last_refresh_at) "
            "VALUES (?, ?, 'active', ?, ?) "
            "ON CONFLICT(tg_id) DO UPDATE SET "
            "  refresh_token_enc = excluded.refresh_token_enc,"
            "  status = 'active',"
            "  fail_count = 0,"
            "  invalid_at = NULL,"
            "  notify_count = 0,"
            "  last_notified_at = NULL,"
            "  last_refresh_at = excluded.last_refresh_at",
            (tg_id, token_enc, now, now),
        )
        await self._conn.commit()

    async def get_token(self, tg_id: int) -> TokenRecord | None:
        cursor = await self._conn.execute("SELECT * FROM tokens WHERE tg_id = ?", (tg_id,))
        row = await cursor.fetchone()
        return _as_token(row) if row else None

    async def set_token_status(self, tg_id: int, status: str) -> None:
        invalid_at = utcnow_iso() if status == TokenStatus.INVALID else None
        await self._conn.execute(
            "UPDATE tokens SET status = ?, invalid_at = ? WHERE tg_id = ?",
            (status, invalid_at, tg_id),
        )
        await self._conn.commit()

    async def bump_token_failure(self, tg_id: int) -> int:
        """A network error is not a dead token (SPEC 5.1) — count and report."""
        await self._conn.execute(
            "UPDATE tokens SET fail_count = fail_count + 1 WHERE tg_id = ?", (tg_id,)
        )
        await self._conn.commit()
        cursor = await self._conn.execute("SELECT fail_count FROM tokens WHERE tg_id = ?", (tg_id,))
        row = await cursor.fetchone()
        return int(row["fail_count"]) if row else 0

    async def tokens_needing_reminder(
        self, max_reminders: int, min_interval_hours: int
    ) -> list[int]:
        """Who to remind about a dead login (SPEC 5.1.1).

        Capped at `max_reminders`: the person may have left on purpose, and a
        bot that nags for months is a bot that gets blocked.
        """
        cutoff = (utcnow() - timedelta(hours=min_interval_hours)).isoformat(timespec="seconds")
        cursor = await self._conn.execute(
            "SELECT tg_id FROM tokens "
            "WHERE status = 'invalid' AND notify_count < ? "
            "  AND (last_notified_at IS NULL OR last_notified_at < ?)",
            (max_reminders, cutoff),
        )
        return [row["tg_id"] for row in await cursor.fetchall()]

    async def mark_token_notified(self, tg_id: int) -> None:
        await self._conn.execute(
            "UPDATE tokens SET notify_count = notify_count + 1, last_notified_at = ? "
            "WHERE tg_id = ?",
            (utcnow_iso(), tg_id),
        )
        await self._conn.commit()

    async def delete_token(self, tg_id: int) -> None:
        await self._conn.execute("DELETE FROM tokens WHERE tg_id = ?", (tg_id,))
        await self._conn.commit()

    # ------------------------------------------------------- user settings

    async def get_user_settings(self, tg_id: int) -> UserSettings | None:
        cursor = await self._conn.execute("SELECT * FROM user_settings WHERE tg_id = ?", (tg_id,))
        row = await cursor.fetchone()
        return _as_user_settings(row) if row else None

    async def user_locale(self, tg_id: int) -> str:
        """This person's own language, used for DMs only (#48) — a group
        follows chat_settings.locale instead. Someone with no settings row
        yet reads as the default, same as every other per-user setting."""
        cursor = await self._conn.execute(
            "SELECT locale FROM user_settings WHERE tg_id = ?", (tg_id,)
        )
        row = await cursor.fetchone()
        return row["locale"] if row else DEFAULT_LOCALE

    async def update_user_settings(self, tg_id: int, **fields: Any) -> None:
        allowed = {"tz_offset_min", "show_profile_links", "locale"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown user_settings fields: {sorted(unknown)}")
        if not fields:
            return
        assignments = ", ".join(f"{name} = ?" for name in fields)
        await self._conn.execute(
            f"UPDATE user_settings SET {assignments} WHERE tg_id = ?",
            (*fields.values(), tg_id),
        )
        await self._conn.commit()

    # --------------------------------------------------------- app settings

    async def get_app_setting(self, key: str, default: str | None = None) -> str | None:
        cursor = await self._conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row["value"] if row else default

    async def get_int_setting(self, key: str, default: int) -> int:
        """The "read an admin-configurable count/limit/interval, fall back
        on garbage" pattern every one of them needed (2026-09-05 refactor —
        six near-identical try/except ValueError blocks collapsed into
        one: chat.py's stats_games_limit, daily.py's summary_top_limit,
        hltb.py's two, message_cleanup.py's TTL, online_refresh.py's two).
        A stored value is always a plain digit string set through
        set_app_setting's own numeric flow (admin.py), so the only way
        `int()` fails here is a hand-edited or pre-migration row."""
        raw = await self.get_app_setting(key, str(default))
        try:
            return int(raw or default)
        except ValueError:
            return default

    async def set_app_setting(self, key: str, value: str, updated_by: int | None = None) -> None:
        await self._conn.execute(
            "INSERT INTO app_settings (key, value, updated_by, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET "
            "  value = excluded.value, updated_by = excluded.updated_by,"
            "  updated_at = excluded.updated_at",
            (key, value, updated_by, utcnow_iso()),
        )
        await self._conn.commit()

    async def delete_app_setting(self, key: str) -> None:
        """Remove a stored setting entirely, reverting it to its code
        default / "not configured" — used by the admin panel's Clear action
        for the Steam key and PSN NPSSO (#17). A no-op if the row is absent."""
        await self._conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
        await self._conn.commit()
