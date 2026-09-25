"""/admin's own auto-refresh bookkeeping, the user/chat lists and settings
behind it, and the shared titles/HLTB caches that happen to live in this
same historical section — one mixin of bot.db.repo.Repo (2026-09-09 split;
see this package's own __init__.py). Behavior is unchanged from before the
split.
"""

from __future__ import annotations

import json
from typing import Any

from bot.db.repo._models import (
    AdminPanelRefreshRow,
    AdminUserRow,
    ChatTarget,
    HltbCacheRow,
    TitleCoverRow,
)
from bot.db.repo._sql import XBOX_ACCOUNT, XBOX_COLUMNS, active_account
from bot.util import utcnow_iso


class _AdminRepo:
    # ----------------------------------------------- admin panel auto-refresh

    async def get_admin_panel_refresh(self, admin_id: int) -> AdminPanelRefreshRow | None:
        cursor = await self._conn.execute(
            "SELECT admin_id, message_id, created_at, last_updated_at "
            "FROM admin_panel_refresh WHERE admin_id = ?",
            (admin_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return AdminPanelRefreshRow(
            admin_id=row["admin_id"],
            message_id=row["message_id"],
            created_at=row["created_at"],
            last_updated_at=row["last_updated_at"],
        )

    async def start_admin_panel_refresh(self, admin_id: int, message_id: int) -> None:
        """A fresh /admin supersedes whatever was auto-refreshing for this
        admin before (Follow-up 2026-09-06, poller/admin_refresh.py) — the
        caller deletes the old *message* itself (get_admin_panel_refresh
        above gives it the id to delete); this just points the one row at
        the new one, same reset-both-timestamps shape as
        start_online_auto_refresh."""
        now = utcnow_iso()
        await self._conn.execute(
            "INSERT INTO admin_panel_refresh (admin_id, message_id, created_at, last_updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(admin_id) DO UPDATE SET"
            " message_id = excluded.message_id, created_at = excluded.created_at,"
            " last_updated_at = excluded.last_updated_at",
            (admin_id, message_id, now, now),
        )
        await self._conn.commit()

    async def touch_admin_panel_refresh(self, admin_id: int) -> None:
        await self._conn.execute(
            "UPDATE admin_panel_refresh SET last_updated_at = ? WHERE admin_id = ?",
            (utcnow_iso(), admin_id),
        )
        await self._conn.commit()

    async def delete_admin_panel_refresh(self, admin_id: int) -> None:
        await self._conn.execute("DELETE FROM admin_panel_refresh WHERE admin_id = ?", (admin_id,))
        await self._conn.commit()

    async def all_admin_panel_refreshes(self) -> list[AdminPanelRefreshRow]:
        cursor = await self._conn.execute(
            "SELECT admin_id, message_id, created_at, last_updated_at FROM admin_panel_refresh"
        )
        return [
            AdminPanelRefreshRow(
                admin_id=row["admin_id"],
                message_id=row["message_id"],
                created_at=row["created_at"],
                last_updated_at=row["last_updated_at"],
            )
            for row in await cursor.fetchall()
        ]

    # ----------------------------------------------------------------- admin

    async def admin_users(self) -> list[AdminUserRow]:
        """Every connected person, Xbox or Steam or PSN or any mix
        (2026-09-05 follow-up, extended for M-PSN-1) — used to be
        `WHERE u.xuid IS NOT NULL`, which hid every Steam-only person from
        the admin panel entirely."""
        cursor = await self._conn.execute(
            "SELECT u.tg_id, u.username, u.first_name,"
            "       u.last_name, u.is_excluded, " + XBOX_COLUMNS + ","
            "       u.last_online_at, t.status, t.last_refresh_at,"
            "       ps.external_id AS steam_id, ps.display_name AS steam_name,"
            "       ps.achievements_visible AS steam_achievements_visible,"
            "       pp.external_id AS psn_account_id, pp.display_name AS psn_online_id,"
            "       pp.achievements_visible AS psn_achievements_visible "
            "FROM users u "
            + XBOX_ACCOUNT
            + "LEFT JOIN tokens t ON t.tg_id = u.tg_id "
            + active_account("ps", "steam")
            + active_account("pp", "psn")
            + "WHERE xb.external_id IS NOT NULL OR ps.external_id IS NOT NULL"
            "   OR pp.external_id IS NOT NULL "
            "ORDER BY u.is_excluded, u.last_online_at DESC"
        )
        return [
            AdminUserRow(
                tg_id=row["tg_id"],
                gamertag=row["gamertag"],
                username=row["username"],
                xuid=row["xuid"],
                gamerscore=row["gamerscore"],
                is_excluded=bool(row["is_excluded"]),
                last_online_at=row["last_online_at"],
                token_status=row["status"],
                last_refresh_at=row["last_refresh_at"],
                steam_id=row["steam_id"],
                steam_name=row["steam_name"],
                psn_account_id=row["psn_account_id"],
                psn_online_id=row["psn_online_id"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                gamertag_modern=row["gamertag_modern"],
                steam_achievements_visible=(
                    bool(row["steam_achievements_visible"])
                    if row["steam_achievements_visible"] is not None
                    else None
                ),
                psn_achievements_visible=(
                    bool(row["psn_achievements_visible"])
                    if row["psn_achievements_visible"] is not None
                    else None
                ),
            )
            for row in await cursor.fetchall()
        ]

    async def admin_user_chat_ids(self) -> dict[int, list[int]]:
        """Active chat ids each person is subscribed to — Mini App admin
        people list filters by chat, so the list endpoint needs this in
        one round-trip rather than N chats_of_user calls."""
        cursor = await self._conn.execute(
            "SELECT s.tg_id, s.chat_id FROM subscriptions s "
            "JOIN chats c ON c.chat_id = s.chat_id "
            "WHERE c.is_active = 1 "
            "ORDER BY s.tg_id, c.title"
        )
        by_user: dict[int, list[int]] = {}
        for row in await cursor.fetchall():
            by_user.setdefault(int(row["tg_id"]), []).append(int(row["chat_id"]))
        return by_user

    async def set_excluded(self, tg_id: int, excluded: bool, by: int | None) -> None:
        """Exclusion is never silent: the person sees it in his panel (SPEC 6.4)."""
        await self._conn.execute(
            "UPDATE users SET is_excluded = ?, excluded_by = ?, excluded_at = ?, updated_at = ? "
            "WHERE tg_id = ?",
            (
                1 if excluded else 0,
                by if excluded else None,
                utcnow_iso() if excluded else None,
                utcnow_iso(),
                tg_id,
            ),
        )
        await self._conn.commit()

    async def admin_chats(self) -> list[ChatTarget]:
        cursor = await self._conn.execute(
            "SELECT c.chat_id, c.title, c.is_active, s.min_gamerscore,"
            "       s.daily_summary, s.muted_title_ids, s.rare_threshold_percent,"
            "       s.daily_summary_time, s.tz_offset_min, s.flood_limit, s.flood_window_minutes,"
            "       s.locale,"
            "       (SELECT COUNT(*) FROM subscriptions WHERE chat_id = c.chat_id) AS subs "
            "FROM chats c JOIN chat_settings s ON s.chat_id = c.chat_id "
            "ORDER BY c.is_active DESC, c.title"
        )
        return [
            ChatTarget(
                chat_id=row["chat_id"],
                title=row["title"],
                min_gamerscore=row["min_gamerscore"],
                muted_title_ids=json.loads(row["muted_title_ids"] or "[]"),
                rare_threshold_percent=row["rare_threshold_percent"],
                daily_summary_time=row["daily_summary_time"],
                tz_offset_min=row["tz_offset_min"],
                flood_limit=row["flood_limit"],
                flood_window_minutes=row["flood_window_minutes"],
                locale=row["locale"],
                is_active=bool(row["is_active"]),
                daily_summary=bool(row["daily_summary"]),
                subscribers=int(row["subs"]),
            )
            for row in await cursor.fetchall()
        ]

    async def update_chat_settings(self, chat_id: int, **fields: Any) -> None:
        allowed = {
            "min_gamerscore",
            "daily_summary",
            "rare_threshold_percent",
            "daily_summary_time",
            "tz_offset_min",
            "flood_limit",
            "flood_window_minutes",
            "locale",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown chat_settings fields: {sorted(unknown)}")
        if not fields:
            return
        assignments = ", ".join(f"{name} = ?" for name in fields)
        await self._conn.execute(
            f"UPDATE chat_settings SET {assignments} WHERE chat_id = ?",
            (*fields.values(), chat_id),
        )
        await self._conn.commit()

    async def set_chat_active(self, chat_id: int, active: bool) -> None:
        await self._conn.execute(
            "UPDATE chats SET is_active = ? WHERE chat_id = ?", (1 if active else 0, chat_id)
        )
        await self._conn.commit()

    async def set_title_names(
        self, title_id: str, name_ru: str | None, name_en: str | None
    ) -> None:
        """A game's own name in both languages, where a platform has two (#61
        — PlayStation does, verified on "Marvel's Wolverine" / "Marvel:
        Росомаха"; Xbox and Steam return one string for both locales).

        Updates only: the row is created by whoever learned the game exists,
        and a side the platform did not give leaves what is stored alone.
        """
        if name_ru is None and name_en is None:
            return
        now = utcnow_iso()
        cursor = await self._conn.execute(
            "UPDATE titles SET name_ru = COALESCE(?, name_ru), name_en = COALESCE(?, name_en),"
            "  updated_at = ? WHERE title_id = ?",
            (name_ru, name_en, now, title_id),
        )
        if not cursor.rowcount:
            # The game is not in `titles` yet — the first poll of it learns
            # the localized names before anything stores the achievements that
            # would create the row. One of the two names it just fetched is a
            # perfectly good `name`, and waiting for the next poll would mean
            # asking the platform for the same thing twice.
            await self._conn.execute(
                "INSERT INTO titles (title_id, name, name_ru, name_en, updated_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(title_id) DO NOTHING",
                (title_id, name_en or name_ru, name_ru, name_en, now),
            )
        await self._conn.commit()

    async def titles_missing_localized_name(self, platform: str, limit: int) -> list[str]:
        """A few games at a time whose name is stored in one language only
        (#61) — poller/steam_localization.py's own small bite. Oldest first,
        so a backlog drains in order rather than by chance."""
        cursor = await self._conn.execute(
            "SELECT title_id FROM titles WHERE platform = ? AND name_ru IS NULL "
            "ORDER BY updated_at LIMIT ?",
            (platform, limit),
        )
        return [row["title_id"] for row in await cursor.fetchall()]

    async def has_localized_title(self, title_id: str) -> bool:
        """Whether this game's name is already stored in both languages —
        what keeps the one storefront request per game (#61) from becoming one
        per poll."""
        cursor = await self._conn.execute(
            "SELECT 1 FROM titles WHERE title_id = ? AND name_ru IS NOT NULL LIMIT 1",
            (title_id,),
        )
        return await cursor.fetchone() is not None

    async def title_names(self, title_ids: list[str]) -> dict[str, tuple[str | None, str | None]]:
        """`{title_id: (name_ru, name_en)}` for the render path — one query
        for a whole digest, same reasoning as `cached_descriptions`."""
        if not title_ids:
            return {}
        placeholders = ", ".join("?" * len(title_ids))
        cursor = await self._conn.execute(
            f"SELECT title_id, name_ru, name_en FROM titles WHERE title_id IN ({placeholders})",
            title_ids,
        )
        return {
            row["title_id"]: (row["name_ru"], row["name_en"]) for row in await cursor.fetchall()
        }

    async def title_platforms(self, title_ids: list[str]) -> dict[str, str]:
        """`{title_id: platforms}` for notifications (#79) — one query for a batch."""
        if not title_ids:
            return {}
        placeholders = ", ".join("?" * len(title_ids))
        cursor = await self._conn.execute(
            f"SELECT title_id, platforms FROM titles "
            f"WHERE title_id IN ({placeholders}) AND platforms IS NOT NULL",
            title_ids,
        )
        return {row["title_id"]: row["platforms"] for row in await cursor.fetchall()}

    # An Xbox game's platforms, looked up in titlehub until found or given up
    # on (#114, migration 060): the lookup is retried an hour apart at most,
    # so one bad minute of Microsoft's cannot spend all three attempts.
    PLATFORMS_LOOKUP_ATTEMPTS = 3

    _PLATFORMS_DUE = (
        "t.platform = 'xbox_modern' AND t.platforms IS NULL"
        f" AND t.platforms_attempts < {PLATFORMS_LOOKUP_ATTEMPTS}"
        " AND (t.platforms_checked_at IS NULL"
        "      OR t.platforms_checked_at < strftime('%Y-%m-%dT%H:%M:%S', 'now', '-1 hour'))"
    )

    async def platforms_lookup_due(self, title_id: str) -> bool:
        """Whether publishing this game should ask titlehub for its platforms first."""
        cursor = await self._conn.execute(
            f"SELECT 1 FROM titles t WHERE t.title_id = ? AND {self._PLATFORMS_DUE}",
            (title_id,),
        )
        return await cursor.fetchone() is not None

    async def titles_needing_platforms(self, limit: int) -> list[tuple[str, int]]:
        """`(title_id, owner_tg_id)` for Xbox games whose platforms are still
        unknown — the same "somebody here with a live token" owner the cover
        walker asks through, since titlehub answers only through a person's."""
        cursor = await self._conn.execute(
            "SELECT t.title_id,"
            "       (SELECT MIN(al.tg_id) FROM seen_achievements s "
            "        JOIN account_links al ON al.platform = s.account_platform"
            "         AND al.external_id = s.xuid AND al.is_active = 1 "
            "        JOIN tokens tok ON tok.tg_id = al.tg_id AND tok.status = 'active' "
            "        JOIN users u ON u.tg_id = al.tg_id AND u.is_excluded = 0 "
            "        WHERE s.title_id = t.title_id) AS owner_tg_id "
            f"FROM titles t WHERE {self._PLATFORMS_DUE} "
            # Filtered before the LIMIT: a game nobody here can be asked about
            # must not take a place in the batch, or a head of such games
            # would stall the queue for good.
            "AND owner_tg_id IS NOT NULL "
            "ORDER BY t.platforms_checked_at IS NOT NULL, t.platforms_checked_at "
            "LIMIT ?",
            (limit,),
        )
        return [(row["title_id"], row["owner_tg_id"]) for row in await cursor.fetchall()]

    async def record_platforms_lookup(self, title_id: str, platforms_json: str | None) -> None:
        """What one titlehub lookup found. None counts as a failed attempt; the
        third one stores '[]' — "known to be unknown" — and leaves the queue."""
        if platforms_json:
            await self._conn.execute(
                "UPDATE titles SET platforms = ?, platforms_checked_at = ? WHERE title_id = ?",
                (platforms_json, utcnow_iso(), title_id),
            )
        else:
            await self._conn.execute(
                "UPDATE titles SET platforms_attempts = platforms_attempts + 1,"
                " platforms_checked_at = ?,"
                " platforms = CASE WHEN platforms_attempts + 1 >= ? THEN '[]' ELSE platforms END "
                "WHERE title_id = ?",
                (utcnow_iso(), self.PLATFORMS_LOOKUP_ATTEMPTS, title_id),
            )
        await self._conn.commit()

    async def set_title_total(self, title_id: str, total: int) -> None:
        """How many achievements a game has, without touching anything else
        about it (#46).

        Not `upsert_title`: that one needs a name, and the poller learns the
        total from the achievements response *before* it resolves a name —
        presence gives none at all for PC titles. So this updates the row when
        there is one and does nothing when there is not; the name arrives
        moments later through `ensure_title_name`, and the next poll stores
        the total against it.
        """
        await self._conn.execute(
            "UPDATE titles SET achievements_total = ?, updated_at = ? WHERE title_id = ?",
            (total, utcnow_iso(), title_id),
        )
        await self._conn.commit()

    async def upsert_title(
        self,
        title_id: str,
        name: str,
        platform: str | None,
        icon_url: str | None = None,
        achievements_total: int | None = None,
        platforms: str | None = None,
    ) -> None:
        # icon_url only overwrites when this call actually has one —
        # ensure_title_name() (fetcher.py) upserts just the name/platform on
        # every new title it resolves, and must not blank out an icon_url a
        # separate ensure_title_icon() call already cached here.
        await self._conn.execute(
            "INSERT INTO titles"
            " (title_id, name, platform, icon_url, achievements_total, platforms, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(title_id) DO UPDATE SET name = excluded.name,"
            " platform = COALESCE(excluded.platform, titles.platform),"
            " updated_at = excluded.updated_at,"
            " icon_url = COALESCE(excluded.icon_url, titles.icon_url),"
            # Same "only overwrite when this call actually has one" rule as
            # icon_url above (#46): most upserts here know the name and
            # nothing else, and must not blank a total somebody else cached.
            " achievements_total = COALESCE(excluded.achievements_total,"
            "                               titles.achievements_total),"
            " platforms = COALESCE(excluded.platforms, titles.platforms)",
            (title_id, name, platform, icon_url, achievements_total, platforms, utcnow_iso()),
        )
        await self._conn.commit()

    async def title_name(self, title_id: str) -> str | None:
        cursor = await self._conn.execute("SELECT name FROM titles WHERE title_id = ?", (title_id,))
        row = await cursor.fetchone()
        return row["name"] if row else None

    async def title_icon_url(self, title_id: str) -> str | None:
        cursor = await self._conn.execute(
            "SELECT icon_url FROM titles WHERE title_id = ?", (title_id,)
        )
        row = await cursor.fetchone()
        return row["icon_url"] if row else None

    async def titles_missing_from_catalogue(self, limit: int) -> list[tuple[str, int]]:
        """Games somebody has achievements in that have no `titles` row at
        all — `(title_id, tg_id)`, paired with an owner who can be asked.

        These render as "без названия" everywhere and nothing fills them in:
        a name is learned when a game is *polled*, and a game nobody plays
        any more is never polled again. 76 of them on production, 658
        achievements between them, all Xbox — Steam's own version of this
        was #70 and is long closed.

        Xbox needs a person's token to answer for a title, so the owner
        comes along; only one whose token is active and who is not excluded,
        the same condition `pollable_users` applies.
        """
        cursor = await self._conn.execute(
            "SELECT s.title_id, MIN(al.tg_id) AS tg_id "
            "FROM seen_achievements s "
            "JOIN account_links al ON al.platform = s.account_platform"
            "   AND al.external_id = s.xuid AND al.is_active = 1 "
            "JOIN tokens tok ON tok.tg_id = al.tg_id AND tok.status = 'active' "
            "JOIN users u ON u.tg_id = al.tg_id AND u.is_excluded = 0 "
            "LEFT JOIN titles t ON t.title_id = s.title_id "
            "WHERE t.title_id IS NULL "
            "GROUP BY s.title_id LIMIT ?",
            (limit,),
        )
        return [(row["title_id"], int(row["tg_id"])) for row in await cursor.fetchall()]

    async def titles_without_platform(self) -> list[tuple[str, str]]:
        """`(title_id, platform)` for rows whose own platform is NULL while
        their achievements know perfectly well what it is.

        125 of them on production. Nothing reads `titles.platform` on a hot
        path today, which is why this went unnoticed — but anything that
        routes by platform (the cover walker does) has to guess for them.
        Free to fix: the answer is already in the rows next door.
        """
        cursor = await self._conn.execute(
            "SELECT t.title_id, MIN(s.platform) AS platform "
            "FROM titles t JOIN seen_achievements s ON s.title_id = t.title_id "
            "WHERE t.platform IS NULL AND s.platform IS NOT NULL "
            "GROUP BY t.title_id"
        )
        return [(row["title_id"], row["platform"]) for row in await cursor.fetchall()]

    async def set_title_platform(self, title_id: str, platform: str) -> None:
        """Only where it is still unknown: a platform already recorded is
        the one the game was actually seen on, and must not be overwritten
        by a guess from a stray row."""
        await self._conn.execute(
            "UPDATE titles SET platform = ? WHERE title_id = ? AND platform IS NULL",
            (platform, title_id),
        )
        await self._conn.commit()

    async def titles_needing_cover(self, limit: int) -> list[TitleCoverRow]:
        """Games whose art is missing or has never been looked at, oldest
        check first (migration 050).

        Two different gaps in one queue, because the walker handles both in
        the same visit: a title with no `icon_url` needs the URL found, and
        a title with a URL but no `cover_path` needs the bytes fetched. A
        title already carrying both is never returned — the covers do not
        expire, unlike an avatar, because the art of a released game does
        not change.

        `cover_checked_at` is what keeps a game nobody can find art for out
        of the queue forever; it is stamped on every visit, found or not.
        """
        cursor = await self._conn.execute(
            # `owner_tg_id` is somebody who has earned something in this game,
            # because Xbox answers about a title only through a *person's*
            # token (unlike Steam's one shared key, or PSN's). Any owner will
            # do — the art is a fact about the game, not about them.
            #
            # Only an owner whose token is **active**, the same condition
            # `pollable_users` applies: asking through a dead one buys a
            # refusal from Microsoft and a doomed refresh attempt per visit.
            # NULL when nobody here can be asked, which is exactly the title
            # the walker should stamp and leave alone.
            "SELECT t.title_id, t.name, t.platform, t.icon_url, t.cover_path, t.cover_hash,"
            "       (SELECT MIN(al.tg_id) FROM seen_achievements s "
            "        JOIN account_links al ON al.platform = s.account_platform"
            "         AND al.external_id = s.xuid AND al.is_active = 1 "
            "        JOIN tokens tok ON tok.tg_id = al.tg_id AND tok.status = 'active' "
            "        JOIN users u ON u.tg_id = al.tg_id AND u.is_excluded = 0 "
            "        WHERE s.title_id = t.title_id) AS owner_tg_id "
            "FROM titles t "
            "WHERE t.cover_path IS NULL "
            "ORDER BY t.cover_checked_at IS NOT NULL, t.cover_checked_at, t.updated_at DESC "
            "LIMIT ?",
            (limit,),
        )
        return [
            TitleCoverRow(
                title_id=row["title_id"],
                name=row["name"],
                platform=row["platform"],
                icon_url=row["icon_url"],
                cover_path=row["cover_path"],
                cover_hash=row["cover_hash"],
                owner_tg_id=row["owner_tg_id"],
            )
            for row in await cursor.fetchall()
        ]

    async def set_title_cover(
        self,
        title_id: str,
        *,
        icon_url: str | None = None,
        cover_path: str | None = None,
        cover_hash: str | None = None,
    ) -> None:
        """Record whatever this visit found, and that the visit happened.

        Each of the three only overwrites when this call actually has one,
        the same rule `upsert_title` above keeps for `icon_url`: a walker
        that found the URL but could not download it must not blank a file
        somebody else already fetched.
        """
        await self._conn.execute(
            "UPDATE titles SET"
            "  icon_url = COALESCE(?, icon_url),"
            "  cover_path = COALESCE(?, cover_path),"
            "  cover_hash = COALESCE(?, cover_hash),"
            "  cover_checked_at = ? "
            "WHERE title_id = ?",
            (icon_url, cover_path, cover_hash, utcnow_iso(), title_id),
        )
        await self._conn.commit()

    async def cover_coverage(self) -> tuple[int, int, int]:
        """(with a file, with a URL, total) — what the admin panel and the
        one-off script both report progress against."""
        cursor = await self._conn.execute(
            "SELECT COUNT(*),"
            "       SUM(CASE WHEN icon_url IS NOT NULL AND icon_url != '' THEN 1 ELSE 0 END),"
            "       SUM(CASE WHEN cover_path IS NOT NULL THEN 1 ELSE 0 END) "
            "FROM titles"
        )
        row = await cursor.fetchone()
        if row is None:
            return 0, 0, 0
        return int(row[2] or 0), int(row[1] or 0), int(row[0] or 0)

    async def hltb_all_ids(self) -> list[int]:
        """For the one-off platforms backfill (scripts/backfill_hltb_platforms.py)
        — every id already cached, so it can be re-resolved with the field
        that didn't exist when it was first cached."""
        cursor = await self._conn.execute("SELECT hltb_id FROM hltb_cache")
        return [row[0] for row in await cursor.fetchall()]

    async def hltb_get_cached(self, hltb_id: int) -> HltbCacheRow | None:
        cursor = await self._conn.execute(
            "SELECT hltb_id, name, release_year, main_hours, extra_hours,"
            " completionist_hours, platforms, game_url, image_url, genre,"
            " description_en, description_ru "
            "FROM hltb_cache WHERE hltb_id = ?",
            (hltb_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return HltbCacheRow(
            hltb_id=row["hltb_id"],
            name=row["name"],
            release_year=row["release_year"],
            main_hours=row["main_hours"],
            extra_hours=row["extra_hours"],
            completionist_hours=row["completionist_hours"],
            platforms=json.loads(row["platforms"] or "[]"),
            game_url=row["game_url"],
            image_url=row["image_url"],
            genre=row["genre"],
            description_en=row["description_en"],
            description_ru=row["description_ru"],
        )

    async def hltb_cache_result(self, entry: HltbCacheRow) -> None:
        """Cached forever (SPEC 6.6) — only called once someone actually
        picks a search result, never for the rest of the candidate list."""
        await self._conn.execute(
            "INSERT OR REPLACE INTO hltb_cache "
            "(hltb_id, name, release_year, main_hours, extra_hours, completionist_hours,"
            " platforms, game_url, image_url, genre, description_en, description_ru,"
            " cached_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.hltb_id,
                entry.name,
                entry.release_year,
                entry.main_hours,
                entry.extra_hours,
                entry.completionist_hours,
                json.dumps(entry.platforms),
                entry.game_url,
                entry.image_url,
                entry.genre,
                entry.description_en,
                entry.description_ru,
                utcnow_iso(),
            ),
        )
        await self._conn.commit()
