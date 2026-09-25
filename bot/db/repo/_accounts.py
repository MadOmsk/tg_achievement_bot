"""Users, Xbox tokens, per-user settings, and admin-wide app settings —
one mixin of bot.db.repo.Repo (2026-09-09 split; see this package's own
__init__.py). Behavior is unchanged from before the split.
"""

from __future__ import annotations

import logging
from datetime import UTC, timedelta
from typing import Any

from bot.constants import AccountPlatform, TokenStatus
from bot.db.repo._models import (
    CooldownCheckResult,
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

log = logging.getLogger(__name__)


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
        if tg_id <= 0:
            log.warning("refusing to create user with non-user tg_id=%s (#66)", tg_id)
            return

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
        # The rarity mode too (#126): it moved here from the subscription, and
        # the admin's default for new people moved with it.
        default_rarity_mode = await self.get_app_setting("default_rarity_mode", "all")
        await self._conn.execute(
            "INSERT OR IGNORE INTO user_settings (tg_id, show_profile_links, rarity_mode)"
            " VALUES (?, ?, ?)",
            (tg_id, default_show_links, default_rarity_mode or "all"),
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
            "WHERE (photo_checked_at IS NULL OR photo_checked_at < ?) "
            "  AND tg_id > 0 "
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

    async def delete_user(self, tg_id: int, *, is_admin: bool = False) -> bool:
        """Completely remove a user, their linked platform accounts, and all related
        rows (tokens, subscriptions, settings, seen achievements, publications,
        presence/poll state, cached history, avatars).

        If not is_admin: records platform reset in `platform_cooldowns` for anti-abuse.
        If is_admin: clears cooldown for this user.

        Returns True if a user was deleted, False if no such user existed.
        """
        cursor = await self._conn.execute("SELECT photo_path FROM users WHERE tg_id = ?", (tg_id,))
        row = await cursor.fetchone()
        if not row:
            return False
        photo_path = row["photo_path"]

        # Step 1: Find all linked platform accounts for this user
        cursor = await self._conn.execute(
            "SELECT platform, external_id FROM account_links WHERE tg_id = ?",
            (tg_id,),
        )
        linked_accounts = [(r["platform"], r["external_id"]) for r in await cursor.fetchall()]

        from bot.services.avatars import avatar_dir

        # Step 2: Clean up platform accounts that belong to this user
        for platform, external_id in linked_accounts:
            # Check if any OTHER active user has linked this account
            cursor = await self._conn.execute(
                "SELECT tg_id FROM account_links "
                "WHERE platform = ? AND external_id = ? AND is_active = 1 AND tg_id != ?",
                (platform, external_id, tg_id),
            )
            other_owner = await cursor.fetchone()

            if not other_owner:
                # Wipe seen_achievements
                await self._conn.execute(
                    "DELETE FROM seen_achievements WHERE account_platform = ? AND xuid = ?",
                    (platform, external_id),
                )
                # Wipe publications
                await self._conn.execute(
                    "DELETE FROM publications WHERE xuid = ?",
                    (external_id,),
                )
                # Wipe title_history
                await self._conn.execute(
                    "DELETE FROM title_history WHERE xuid = ?",
                    (external_id,),
                )
                # Wipe presence and poller state
                if platform in (AccountPlatform.XBOX, "xbox_modern", "xbox_360"):
                    await self._conn.execute(
                        "DELETE FROM presence_state WHERE xuid = ?",
                        (external_id,),
                    )
                elif platform == AccountPlatform.STEAM:
                    await self._conn.execute(
                        "DELETE FROM steam_presence_state WHERE steam_id = ?",
                        (external_id,),
                    )
                elif platform == AccountPlatform.PSN:
                    await self._conn.execute(
                        "DELETE FROM psn_presence_state WHERE account_id = ?",
                        (external_id,),
                    )
                    await self._conn.execute(
                        "DELETE FROM psn_title_progress WHERE account_id = ?",
                        (external_id,),
                    )
                    await self._conn.execute(
                        "DELETE FROM psn_poll_state WHERE account_id = ?",
                        (external_id,),
                    )

                # Wipe avatar on disk
                cursor = await self._conn.execute(
                    "SELECT avatar_path FROM accounts WHERE platform = ? AND external_id = ?",
                    (platform, external_id),
                )
                acc_row = await cursor.fetchone()
                if acc_row and acc_row["avatar_path"]:
                    try:
                        acc_path = avatar_dir() / acc_row["avatar_path"]
                        if acc_path.is_file():
                            acc_path.unlink()
                    except OSError:
                        log.warning(
                            "failed to remove platform avatar platform=%s ext_id=%s path=%s",
                            platform,
                            external_id,
                            acc_row["avatar_path"],
                        )

                # Wipe account_links and accounts
                await self._conn.execute(
                    "DELETE FROM account_links WHERE platform = ? AND external_id = ?",
                    (platform, external_id),
                )
                await self._conn.execute(
                    "DELETE FROM accounts WHERE platform = ? AND external_id = ?",
                    (platform, external_id),
                )

            # Record cooldown if user-initiated
            if not is_admin:
                await self.record_platform_reset(tg_id, platform, external_id)

        if is_admin:
            await self.clear_platform_cooldown(tg_id)

        # Step 3: Remove user, tokens, and related records
        await self._conn.execute("DELETE FROM tokens WHERE tg_id = ?", (tg_id,))
        await self._conn.execute("DELETE FROM users WHERE tg_id = ?", (tg_id,))
        await self._conn.execute(
            "DELETE FROM tracked_messages WHERE chat_id = ? OR (kind = 'stats' AND subject_id = ?)",
            (tg_id, tg_id),
        )
        await self._conn.execute(
            "DELETE FROM admin_panel_refresh WHERE admin_id = ?",
            (tg_id,),
        )

        await self._conn.commit()

        if photo_path:
            try:
                path = avatar_dir() / photo_path
                if path.is_file():
                    path.unlink()
            except OSError:
                log.warning("failed to remove avatar for tg_id=%s path=%s", tg_id, photo_path)

        return True

    async def record_platform_reset(
        self, tg_id: int, platform: str, external_id: str | None = None
    ) -> None:
        """Record an account deletion/reset event in `platform_cooldowns`.
        If within existing cooldown window, increment reset_count; otherwise reset to 1.
        """
        from datetime import datetime

        from bot.constants import SettingKey
        from bot.services.admin_settings import DEFAULT_ACCOUNT_RESET_COOLDOWN_HOURS

        cursor = await self._conn.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            (SettingKey.ACCOUNT_RESET_COOLDOWN_HOURS,),
        )
        row = await cursor.fetchone()
        cooldown_hours = int(row["value"]) if row else DEFAULT_ACCOUNT_RESET_COOLDOWN_HOURS
        if cooldown_hours <= 0:
            return

        cursor = await self._conn.execute(
            "SELECT reset_count, last_reset_at FROM platform_cooldowns "
            "WHERE tg_id = ? AND platform = ?",
            (tg_id, platform),
        )
        existing = await cursor.fetchone()
        now = utcnow()
        now_iso = utcnow_iso()

        new_count = 1
        if existing:
            try:
                last_reset_at = datetime.fromisoformat(existing["last_reset_at"])
                if last_reset_at.tzinfo is None:
                    last_reset_at = last_reset_at.replace(tzinfo=UTC)
                elapsed_seconds = (now - last_reset_at).total_seconds()
                if elapsed_seconds < cooldown_hours * 3600:
                    new_count = int(existing["reset_count"]) + 1
            except Exception:
                pass

        await self._conn.execute(
            "INSERT INTO platform_cooldowns "
            "(tg_id, platform, external_id, reset_count, last_reset_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(tg_id, platform) DO UPDATE SET "
            "  external_id = COALESCE(excluded.external_id, platform_cooldowns.external_id), "
            "  reset_count = excluded.reset_count, "
            "  last_reset_at = excluded.last_reset_at",
            (tg_id, platform, str(external_id) if external_id else None, new_count, now_iso),
        )
        await self._conn.commit()

    async def check_platform_cooldown(
        self, tg_id: int, platform: str, external_id: str | None = None
    ) -> CooldownCheckResult:
        """Check if re-linking `platform` is currently blocked by anti-abuse cooldown.
        Rules:
        - Setting `account_reset_cooldown_hours` sets the window (default 24h, 0 = off).
        - reset_count <= 1: 1 free re-link is allowed immediately without cooldown.
        - reset_count > 1 and within window: blocked until elapsed >= window.
        - Checks both (tg_id, platform) and (platform, external_id).
        """
        from datetime import datetime

        from bot.constants import SettingKey
        from bot.services.admin_settings import DEFAULT_ACCOUNT_RESET_COOLDOWN_HOURS

        cursor = await self._conn.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            (SettingKey.ACCOUNT_RESET_COOLDOWN_HOURS,),
        )
        row = await cursor.fetchone()
        cooldown_hours = int(row["value"]) if row else DEFAULT_ACCOUNT_RESET_COOLDOWN_HOURS
        if cooldown_hours <= 0:
            return CooldownCheckResult(is_blocked=False)

        # Check by (tg_id, platform) or (platform, external_id)
        if external_id:
            cursor = await self._conn.execute(
                "SELECT reset_count, last_reset_at FROM platform_cooldowns "
                "WHERE (tg_id = ? AND platform = ?) OR (platform = ? AND external_id = ?) "
                "ORDER BY last_reset_at DESC LIMIT 1",
                (tg_id, platform, platform, str(external_id)),
            )
        else:
            cursor = await self._conn.execute(
                "SELECT reset_count, last_reset_at FROM platform_cooldowns "
                "WHERE tg_id = ? AND platform = ?",
                (tg_id, platform),
            )
        row = await cursor.fetchone()
        if not row:
            return CooldownCheckResult(is_blocked=False)

        reset_count = int(row["reset_count"])
        last_reset_at_str = row["last_reset_at"]
        try:
            last_reset_at = datetime.fromisoformat(last_reset_at_str)
            if last_reset_at.tzinfo is None:
                last_reset_at = last_reset_at.replace(tzinfo=UTC)
            now = utcnow()
            elapsed_seconds = (now - last_reset_at).total_seconds()
        except Exception:
            elapsed_seconds = 0

        cooldown_seconds = cooldown_hours * 3600
        if elapsed_seconds >= cooldown_seconds:
            return CooldownCheckResult(is_blocked=False, reset_count=reset_count)

        if reset_count <= 1:
            return CooldownCheckResult(is_blocked=False, reset_count=reset_count)

        remaining_seconds = max(0, int(cooldown_seconds - elapsed_seconds))
        return CooldownCheckResult(
            is_blocked=True,
            remaining_seconds=remaining_seconds,
            reset_count=reset_count,
        )

    async def clear_platform_cooldown(self, tg_id: int, platform: str | None = None) -> None:
        """Clear cooldown records for tg_id (e.g. on admin operations)."""
        if platform:
            await self._conn.execute(
                "DELETE FROM platform_cooldowns WHERE tg_id = ? AND platform = ?",
                (tg_id, platform),
            )
        else:
            await self._conn.execute(
                "DELETE FROM platform_cooldowns WHERE tg_id = ?",
                (tg_id,),
            )
        await self._conn.commit()

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
        allowed = {"tz_offset_min", "show_profile_links", "show_secrets", "locale", "rarity_mode"}
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

    async def any_active_xbox_tg_id(self) -> int | None:
        """Find any user with an active Xbox link and active token (e.g. for catalog queries)."""
        cursor = await self._conn.execute(
            "SELECT al.tg_id FROM account_links al "
            "JOIN tokens tok ON tok.tg_id = al.tg_id AND tok.status = 'active' "
            "WHERE al.platform = 'xbox' AND al.is_active = 1 LIMIT 1"
        )
        row = await cursor.fetchone()
        return int(row["tg_id"]) if row else None
