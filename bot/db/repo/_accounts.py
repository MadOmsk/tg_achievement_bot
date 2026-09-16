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
from bot.db.repo._sql import XBOX_ACCOUNT, XBOX_COLUMNS
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

    async def users_needing_avatar(self, before: str, limit: int) -> list[int]:
        """Who has not had their profile photo looked at since `before` —
        oldest first, so a backlog drains in order rather than by chance
        (poller/avatars.py, 2026-09-13). A NULL `photo_checked_at` has never
        been checked at all and goes first."""
        cursor = await self._conn.execute(
            "SELECT tg_id FROM users "
            "WHERE photo_checked_at IS NULL OR photo_checked_at < ? "
            "ORDER BY photo_checked_at IS NOT NULL, photo_checked_at LIMIT ?",
            (before, limit),
        )
        return [row["tg_id"] for row in await cursor.fetchall()]

    async def set_user_photo(
        self,
        tg_id: int,
        file_id: str | None,
        unique_id: str | None,
        path: str | None = None,
    ) -> None:
        """The result of one look, including "this person has no photo we can
        see" — `photo_checked_at` is stamped either way, or a private profile
        would be asked about again every single tick.

        `path` is the downloaded copy (#55). It is only written when one was
        actually saved: a look that found the same picture as last time keeps
        the file it already has rather than clearing the column."""
        await self._conn.execute(
            "UPDATE users SET photo_file_id = ?, photo_unique_id = ?, "
            "  photo_path = COALESCE(?, photo_path), photo_checked_at = ? "
            "WHERE tg_id = ?",
            (file_id, unique_id, path, utcnow_iso(), tg_id),
        )
        await self._conn.commit()

    async def user_photo(self, tg_id: int) -> tuple[str | None, str | None]:
        """`(unique_id, path)` — what the last look found, for deciding
        whether this one has anything to download."""
        cursor = await self._conn.execute(
            "SELECT photo_unique_id, photo_path FROM users WHERE tg_id = ?", (tg_id,)
        )
        row = await cursor.fetchone()
        return (row["photo_unique_id"], row["photo_path"]) if row else (None, None)

    async def accounts_needing_avatar(self, before: str, limit: int) -> list[tuple[str, str]]:
        """A few platform accounts whose picture has not been looked at since
        `before`, oldest first — the account half of poller/avatars.py's own
        sweep (#55). Only accounts somebody currently holds: an account
        nobody is linked to is invisible everywhere else too (#52)."""
        cursor = await self._conn.execute(
            "SELECT a.platform, a.external_id FROM accounts a "
            "JOIN account_links al ON al.platform = a.platform "
            "  AND al.external_id = a.external_id AND al.is_active = 1 "
            "WHERE a.avatar_checked_at IS NULL OR a.avatar_checked_at < ? "
            "ORDER BY a.avatar_checked_at IS NOT NULL, a.avatar_checked_at LIMIT ?",
            (before, limit),
        )
        return [(row["platform"], row["external_id"]) for row in await cursor.fetchall()]

    async def set_account_avatar_url(self, external_id: str, url: str) -> None:
        """Xbox's own picture URL, learned from the profile call the fetcher
        makes with that person's token (#55). Deliberately does *not* stamp
        `avatar_checked_at`: the check that matters is "has it been
        downloaded", which is poller/avatars.py's to make."""
        await self._conn.execute(
            "UPDATE accounts SET avatar_url = ? WHERE platform = 'xbox' AND external_id = ?",
            (url, external_id),
        )
        await self._conn.commit()

    async def account_avatar(
        self, platform: str, external_id: str
    ) -> tuple[str | None, str | None]:
        """`(url, hash)` as last stored — the url answers "has the platform
        changed its mind", the hash answers "are these the same bytes"."""
        cursor = await self._conn.execute(
            "SELECT avatar_url, avatar_hash FROM accounts WHERE platform = ? AND external_id = ?",
            (platform, external_id),
        )
        row = await cursor.fetchone()
        return (row["avatar_url"], row["avatar_hash"]) if row else (None, None)

    async def set_account_avatar(
        self,
        platform: str,
        external_id: str,
        url: str | None,
        path: str | None = None,
        avatar_hash: str | None = None,
    ) -> None:
        """Same shape as set_user_photo above: the timestamp is always
        stamped, the file and its hash only when something was downloaded."""
        await self._conn.execute(
            "UPDATE accounts SET avatar_url = ?, "
            "  avatar_path = COALESCE(?, avatar_path), avatar_hash = COALESCE(?, avatar_hash), "
            "  avatar_checked_at = ? "
            "WHERE platform = ? AND external_id = ?",
            (url, path, avatar_hash, utcnow_iso(), platform, external_id),
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

    # `users` is only the Telegram identity now (#52); the Xbox columns that
    # used to sit beside it are an `accounts` row reached through the active
    # link, and are aliased back to their old names so every caller of
    # `User` keeps reading `user.xuid` / `user.gamertag` unchanged.
    _USER_COLUMNS = "SELECT u.*, " + XBOX_COLUMNS + "FROM users u " + XBOX_ACCOUNT

    async def get_user(self, tg_id: int) -> User | None:
        cursor = await self._conn.execute(self._USER_COLUMNS + "WHERE u.tg_id = ?", (tg_id,))
        row = await cursor.fetchone()
        return _as_user(row) if row else None

    async def get_user_by_xuid(self, xuid: str) -> User | None:
        """Whoever currently holds that Xbox account — nobody, once they
        unlink it (#52). The poller only ever asks about accounts it just
        got a link for, so "nobody" here means the link moved mid-poll."""
        cursor = await self._conn.execute(self._USER_COLUMNS + "WHERE xb.external_id = ?", (xuid,))
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
        await self._conn.execute(
            "UPDATE accounts SET secondary_name = COALESCE(?, secondary_name),"
            "       gamerscore = COALESCE(?, gamerscore), updated_at = ? "
            "WHERE platform = ? AND external_id = ?",
            (gamertag, gamerscore, utcnow_iso(), AccountPlatform.XBOX, xuid),
        )
        await self._conn.commit()
        return taken_from

    async def unlink_xbox_account(self, tg_id: int) -> None:
        """/disconnect_xbox: the link is deactivated, the account and
        everything it earned stay (SPEC 6.1, and #52's own rule — relinking
        later finds its history waiting instead of paying for a backfill)."""
        await self.unlink_platform_account(tg_id, AccountPlatform.XBOX)

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
