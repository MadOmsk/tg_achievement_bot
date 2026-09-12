"""Achievement/trophy insert+dedup across all three platforms, publication
bookkeeping, and the admin "reset & resync" action — one mixin of
bot.db.repo.Repo (2026-09-09 split; see this package's own __init__.py).
Behavior is unchanged from before the split.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from bot.constants import AccountPlatform, Platform
from bot.db.repo._models import AchievementRow
from bot.db.repo._sql import OWNED_BY_PERSON
from bot.util import utcnow_iso

log = logging.getLogger(__name__)


class _AchievementsRepo:
    # --------------------------------------------- admin "reset & resync"

    async def reset_xbox_data(self, tg_id: int, xuid: str) -> int:
        """Wipe this person's Xbox achievement history and per-game cache —
        the admin card's "reset & resync" action (user request 2026-09-08):
        deletes both modern and x360 `seen_achievements` rows (there is no
        separate UI concept of "Xbox 360" outside the message/icon itself,
        same reasoning as `achievement_platform_breakdown`) plus their
        `title_history` cache, so a fresh backfill starts from nothing
        rather than a stale gamerscore/progress snapshot lingering next to
        an empty achievement list. The caller re-runs backfill right after.
        """
        cursor = await self._conn.execute(
            "DELETE FROM seen_achievements WHERE xuid = ? "
            "AND platform IN ('xbox_modern', 'xbox_360')",
            (xuid,),
        )
        deleted = cursor.rowcount
        await self._conn.execute("DELETE FROM title_history WHERE xuid = ?", (xuid,))
        await self._conn.commit()
        return deleted

    async def reset_steam_data(self, external_id: str) -> int:
        """Steam's counterpart of `reset_xbox_data` — no per-user cache table
        to clear beyond `seen_achievements` itself (`steam_schema_cache`/
        `steam_rarity_cache` are per-game, shared across every user, and
        must not be touched by resetting one person)."""
        cursor = await self._conn.execute(
            "DELETE FROM seen_achievements WHERE xuid = ? AND platform = 'steam'",
            (external_id,),
        )
        deleted = cursor.rowcount
        await self._conn.commit()
        return deleted

    async def reset_psn_data(self, tg_id: int, account_id: str) -> int:
        """PSN's counterpart of `reset_xbox_data` — also clears the per-game
        progress cache (same table `clear_psn_title_progress` clears for
        #27's stuck-account recovery) and flips `backfill_done` back off, so
        the regular poller (#21's gate) leaves this account alone until the
        caller's fresh backfill flips it back on."""
        cursor = await self._conn.execute(
            "DELETE FROM seen_achievements WHERE xuid = ? AND platform = 'psn'",
            (account_id,),
        )
        deleted = cursor.rowcount
        await self._conn.execute(
            "DELETE FROM psn_title_progress WHERE account_id = ?", (account_id,)
        )
        await self._conn.execute(
            "UPDATE psn_poll_state SET backfill_done = 0 WHERE account_id = ?", (account_id,)
        )
        await self._conn.commit()
        return deleted

    # -------------------------------------------------------- achievements

    async def _ensure_account(self, account_platform: str, external_id: str) -> None:
        """An achievement is proof the account exists, so record it if this
        is the first we hear of it (#52).

        The foreign key from `seen_achievements` to `accounts` is what keeps
        a row attached to something real; without this, a poll for an account
        nobody has linked would raise mid-tick instead of quietly storing
        what it found. Storing it is right: the rows belong to the account
        and simply stay invisible until somebody links it.
        """
        now = utcnow_iso()
        await self._conn.execute(
            "INSERT OR IGNORE INTO accounts (platform, external_id, first_seen_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (account_platform, external_id, now, now),
        )

    async def insert_new_achievements(
        self, xuid: str, achievements: Sequence[AchievementRow], *, is_backfill: bool
    ) -> list[AchievementRow]:
        """Insert what we have not seen and report back only the new rows.

        The primary key (platform, xuid, title_id, achievement_id) is the
        deduplication: INSERT OR IGNORE tells us which rows were actually
        new. Since #52 the account is what identifies whose row this is, so
        no owner lookup happens here at all — which also retires a real
        failure mode: this used to resolve a tg_id from the xuid first and
        drop the whole batch when it found none.
        """
        if not achievements:
            return []
        await self._ensure_account(AccountPlatform.XBOX, xuid)

        new_rows: list[AchievementRow] = []
        now = utcnow_iso()
        for item in achievements:
            cursor = await self._conn.execute(
                "INSERT OR IGNORE INTO seen_achievements "
                "(xuid, title_id, achievement_id, name, description, icon_url, unlocked_at,"
                " gamerscore, rarity_percent, platform, is_backfill, is_secret, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    xuid,
                    item.title_id,
                    item.achievement_id,
                    item.name,
                    item.description,
                    item.icon_url,
                    item.unlocked_at,
                    item.gamerscore,
                    item.rarity_percent,
                    item.platform,
                    1 if is_backfill else 0,
                    1 if item.is_secret else 0,
                    now,
                ),
            )
            if cursor.rowcount:
                new_rows.append(item)
        await self._conn.commit()
        return new_rows

    async def insert_new_achievements_steam(
        self,
        tg_id: int,
        steam_id: str,
        achievements: Sequence[AchievementRow],
        *,
        is_backfill: bool,
    ) -> list[AchievementRow]:
        """Steam's counterpart of `insert_new_achievements` (SPEC 9, M-Steam-
        2c/2d) — no xuid-lookup stopgap needed here: the Steam poller/backfill
        always already has `tg_id` on hand, straight from `platform_links`,
        unlike the Xbox path which only ever has an xuid to start from. The
        `xuid` column in `seen_achievements` is the same generic per-platform
        external_id it's always been (SPEC 9, M-Steam-2a) — holds the
        SteamID64 here, not an Xbox xuid.
        """
        if not achievements:
            return []

        # Xbox's own fetcher caches a title's name via ensure_title_name() on
        # every poll (poller/fetcher.py) — Steam never had an equivalent, so
        # `titles` stayed empty for every appid and /recent's LEFT JOIN onto
        # it fell back to "без названия" for every Steam row. One upsert per
        # unique game in this batch, not per achievement.
        cached_titles: dict[str, str] = {}
        for item in achievements:
            if item.title_name and item.title_id not in cached_titles:
                cached_titles[item.title_id] = item.title_name
        for title_id, name in cached_titles.items():
            await self.upsert_title(title_id, name, Platform.STEAM)
        await self._ensure_account(AccountPlatform.STEAM, steam_id)

        new_rows: list[AchievementRow] = []
        now = utcnow_iso()
        for item in achievements:
            cursor = await self._conn.execute(
                "INSERT OR IGNORE INTO seen_achievements "
                "(xuid, title_id, achievement_id, name, description, icon_url, unlocked_at,"
                " gamerscore, rarity_percent, platform, is_backfill, is_secret, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    steam_id,
                    item.title_id,
                    item.achievement_id,
                    item.name,
                    item.description,
                    item.icon_url,
                    item.unlocked_at,
                    item.gamerscore,
                    item.rarity_percent,
                    item.platform,
                    1 if is_backfill else 0,
                    1 if item.is_secret else 0,
                    now,
                ),
            )
            if cursor.rowcount:
                new_rows.append(item)
        await self._conn.commit()
        return new_rows

    async def insert_new_achievements_psn(
        self,
        tg_id: int,
        account_id: str,
        achievements: Sequence[AchievementRow],
        *,
        is_backfill: bool,
    ) -> list[AchievementRow]:
        """PSN's counterpart of insert_new_achievements_steam (SPEC 9,
        M-PSN-2) — same reasoning, `tg_id` already on hand from
        `platform_links`, no xuid-lookup stopgap needed. The `xuid` column
        holds `account_id` here (the generic per-platform external_id,
        unchanged since M-Steam-2a), `title_id` holds `np_communication_id`,
        `achievement_id` holds the PSN trophy_id, and `trophy_type` (NULL
        for every other platform) carries the tier this method's Xbox/Steam
        siblings never set."""
        if not achievements:
            return []

        cached_titles: dict[str, str] = {}
        for item in achievements:
            if item.title_name and item.title_id not in cached_titles:
                cached_titles[item.title_id] = item.title_name
        for title_id, name in cached_titles.items():
            await self.upsert_title(title_id, name, Platform.PSN)
        await self._ensure_account(AccountPlatform.PSN, account_id)

        new_rows: list[AchievementRow] = []
        now = utcnow_iso()
        for item in achievements:
            cursor = await self._conn.execute(
                "INSERT OR IGNORE INTO seen_achievements "
                "(xuid, title_id, achievement_id, name, description, icon_url, unlocked_at,"
                " gamerscore, rarity_percent, platform, is_backfill, is_secret, trophy_type,"
                " trophy_group_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    account_id,
                    item.title_id,
                    item.achievement_id,
                    item.name,
                    item.description,
                    item.icon_url,
                    item.unlocked_at,
                    item.gamerscore,
                    item.rarity_percent,
                    item.platform,
                    1 if is_backfill else 0,
                    1 if item.is_secret else 0,
                    item.trophy_type,
                    item.trophy_group_id,
                    now,
                ),
            )
            if cursor.rowcount:
                new_rows.append(item)
        await self._conn.commit()
        return new_rows

    async def get_psn_title_progress(self, account_id: str, np_communication_id: str) -> int | None:
        """The last-seen `progress` for one (account, game) — poller/
        psn_fetcher.py skips the expensive full-trophy-detail call unless
        this grew (M-PSN-2, trophy sync has no presence signal to key off)."""
        cursor = await self._conn.execute(
            "SELECT progress FROM psn_title_progress "
            "WHERE account_id = ? AND np_communication_id = ?",
            (account_id, np_communication_id),
        )
        row = await cursor.fetchone()
        return row["progress"] if row else None

    async def set_psn_title_progress(
        self, account_id: str, np_communication_id: str, progress: int
    ) -> None:
        await self._conn.execute(
            "INSERT INTO psn_title_progress"
            " (account_id, np_communication_id, progress, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(account_id, np_communication_id) DO UPDATE SET"
            " progress = excluded.progress, updated_at = excluded.updated_at",
            (account_id, np_communication_id, progress, utcnow_iso()),
        )
        await self._conn.commit()

    async def recent_achievements(self, xuid: str, limit: int = 5) -> list[AchievementRow]:
        """The last N unlocks, newest first — for the panel (SPEC 6.2).
        Undated rows never win: an unknown unlock time is not "recent"."""
        cursor = await self._conn.execute(
            "SELECT s.*, t.name AS game FROM seen_achievements s "
            "LEFT JOIN titles t ON t.title_id = s.title_id "
            "WHERE s.xuid = ? AND s.unlocked_at IS NOT NULL "
            "ORDER BY s.unlocked_at DESC LIMIT ?",
            (xuid, limit),
        )
        return [
            AchievementRow(
                title_id=row["title_id"],
                achievement_id=row["achievement_id"],
                name=row["name"],
                description=row["description"],
                icon_url=row["icon_url"],
                unlocked_at=row["unlocked_at"],
                gamerscore=row["gamerscore"],
                rarity_percent=row["rarity_percent"],
                platform=row["platform"],
                title_name=row["game"],
                is_secret=bool(row["is_secret"]),
                trophy_type=row["trophy_type"],
            )
            for row in await cursor.fetchall()
        ]

    async def has_any_achievements(self, xuid: str) -> bool:
        cursor = await self._conn.execute(
            "SELECT 1 FROM seen_achievements WHERE xuid = ? LIMIT 1", (xuid,)
        )
        return await cursor.fetchone() is not None

    async def record_publication(
        self, chat_id: int, xuid: str, title_id: str, achievement_id: str, message_id: int | None
    ) -> None:
        await self._conn.execute(
            "INSERT OR REPLACE INTO publications "
            "(chat_id, xuid, title_id, achievement_id, message_id, posted_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, xuid, title_id, achievement_id, message_id, utcnow_iso()),
        )
        await self._conn.commit()

    async def is_published(
        self, chat_id: int, xuid: str, title_id: str, achievement_id: str
    ) -> bool:
        cursor = await self._conn.execute(
            "SELECT 1 FROM publications "
            "WHERE chat_id = ? AND xuid = ? AND title_id = ? AND achievement_id = ?",
            (chat_id, xuid, title_id, achievement_id),
        )
        return await cursor.fetchone() is not None

    async def unpublished_achievements(self, tg_id: int, chat_id: int) -> list[AchievementRow]:
        """Every one of this person's achievements — any platform, `xuid`
        populated on each row since they don't all share one — that never
        made it into `publications` for this specific chat (2026-09-09,
        anti-flood filter, poller/flood_flush.py): an achievement the flood
        filter buffered instead of sending individually is, by construction,
        exactly an achievement that is "seen" but not yet "published here" —
        no separate buffer/queue table needed, this table pair already
        distinguishes the two. Backfill rows never qualify (never meant to
        publish at all), same as everywhere else achievements get filtered
        for publication.

        Also finds an achievement that legitimately never passed this chat's
        filters (rare-mode threshold, muted game, ...) — harmless: the
        caller re-runs `passes_filters` before using any of these, so a
        correctly-excluded achievement is excluded again, forever, exactly
        as it is today outside the flood filter entirely.
        """
        cursor = await self._conn.execute(
            "SELECT s.*, t.name AS game FROM seen_achievements s "
            + OWNED_BY_PERSON
            + "LEFT JOIN titles t ON t.title_id = s.title_id "
            "LEFT JOIN publications p ON p.chat_id = ? AND p.xuid = s.xuid"
            "   AND p.title_id = s.title_id AND p.achievement_id = s.achievement_id "
            "WHERE al.tg_id = ? AND s.is_backfill = 0 AND s.unlocked_at IS NOT NULL"
            "   AND p.chat_id IS NULL "
            "ORDER BY s.unlocked_at ASC",
            (chat_id, tg_id),
        )
        return [
            AchievementRow(
                title_id=row["title_id"],
                achievement_id=row["achievement_id"],
                name=row["name"],
                description=row["description"],
                icon_url=row["icon_url"],
                unlocked_at=row["unlocked_at"],
                gamerscore=row["gamerscore"],
                rarity_percent=row["rarity_percent"],
                platform=row["platform"],
                title_name=row["game"],
                is_secret=bool(row["is_secret"]),
                trophy_type=row["trophy_type"],
                xuid=row["xuid"],
            )
            for row in await cursor.fetchall()
        ]
