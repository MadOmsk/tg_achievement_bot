"""Steam's own achievement schema/rarity caches, and the generic
platform_links table shared by Steam and PSN (link/unlink, visibility
status) — one mixin of bot.db.repo.Repo (2026-09-09 split; see this
package's own __init__.py). Behavior is unchanged from before the split.
"""

from __future__ import annotations

import json

from bot.db.repo._models import PlatformLink, SteamSchemaAchievement
from bot.util import utcnow_iso


class _PlatformLinksRepo:
    # ---------------------------------------------- Steam achievement cache

    async def steam_schema_get_cached(
        self, appid: str
    ) -> tuple[str | None, list[SteamSchemaAchievement]] | None:
        """The game's own achievement list — cached forever, one row per
        appid, never invalidated (SPEC 9, M-Steam-2b): a game's achievements
        don't change between polls the way unlock percentages do."""
        cursor = await self._conn.execute(
            "SELECT game_name, achievements FROM steam_schema_cache WHERE appid = ?",
            (appid,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        achievements = [
            SteamSchemaAchievement(
                apiname=item["apiname"], icon=item["icon"], hidden=item["hidden"]
            )
            for item in json.loads(row["achievements"])
        ]
        return row["game_name"], achievements

    async def steam_schema_cache_result(
        self, appid: str, game_name: str | None, achievements: list[SteamSchemaAchievement]
    ) -> None:
        blob = json.dumps(
            [{"apiname": a.apiname, "icon": a.icon, "hidden": a.hidden} for a in achievements]
        )
        await self._conn.execute(
            "INSERT OR REPLACE INTO steam_schema_cache (appid, game_name, achievements, cached_at) "
            "VALUES (?, ?, ?, ?)",
            (appid, game_name, blob, utcnow_iso()),
        )
        await self._conn.commit()

    async def steam_rarity_get_cached(self, appid: str) -> tuple[dict[str, float], str] | None:
        """Percentages plus their own cache timestamp — unlike the schema
        above, real percentages drift over time, so the caller (services/
        steam/achievements.py) decides whether `cached_at` is too old and
        needs a fresh fetch, this layer just reports what's there."""
        cursor = await self._conn.execute(
            "SELECT percentages, cached_at FROM steam_rarity_cache WHERE appid = ?",
            (appid,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return json.loads(row["percentages"]), row["cached_at"]

    async def steam_rarity_cache_result(self, appid: str, percentages: dict[str, float]) -> None:
        await self._conn.execute(
            "INSERT OR REPLACE INTO steam_rarity_cache (appid, percentages, cached_at) "
            "VALUES (?, ?, ?)",
            (appid, json.dumps(percentages), utcnow_iso()),
        )
        await self._conn.commit()

    async def link_platform_account(
        self, tg_id: int, platform: str, external_id: str, display_name: str | None
    ) -> None:
        """One row per (person, platform) — a second /connect_steam replaces
        the link, same as reconnecting Xbox replaces the old identity."""
        await self._conn.execute(
            "INSERT INTO platform_links (tg_id, platform, external_id, display_name, linked_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(tg_id, platform) DO UPDATE SET "
            "  external_id = excluded.external_id,"
            "  display_name = excluded.display_name,"
            "  linked_at = excluded.linked_at",
            (tg_id, platform, external_id, display_name, utcnow_iso()),
        )
        await self._conn.commit()

    async def update_platform_display_name(
        self, tg_id: int, platform: str, display_name: str
    ) -> None:
        """Opportunistic refresh only (SPEC 9, M-Steam-2c) — the presence
        poller already has a fresh persona name from the same batch call it
        used to update presence, so the panel/connect card doesn't drift
        stale between actual /connect_steam calls. A no-op if the link was
        removed in the meantime (no row to update)."""
        await self._conn.execute(
            "UPDATE platform_links SET display_name = ? WHERE tg_id = ? AND platform = ?",
            (display_name, tg_id, platform),
        )
        await self._conn.commit()

    async def get_platform_link(self, tg_id: int, platform: str) -> PlatformLink | None:
        cursor = await self._conn.execute(
            "SELECT tg_id, platform, external_id, display_name, linked_at, psn_trophy_level,"
            "       achievements_visible, achievements_visible_checked_at "
            "FROM platform_links WHERE tg_id = ? AND platform = ?",
            (tg_id, platform),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return PlatformLink(
            tg_id=row["tg_id"],
            platform=row["platform"],
            external_id=row["external_id"],
            display_name=row["display_name"],
            linked_at=row["linked_at"],
            psn_trophy_level=row["psn_trophy_level"],
            achievements_visible=(
                bool(row["achievements_visible"])
                if row["achievements_visible"] is not None
                else None
            ),
            achievements_visible_checked_at=row["achievements_visible_checked_at"],
        )

    async def platform_links_of(self, tg_id: int) -> list[PlatformLink]:
        cursor = await self._conn.execute(
            "SELECT tg_id, platform, external_id, display_name, linked_at, psn_trophy_level,"
            "       achievements_visible, achievements_visible_checked_at "
            "FROM platform_links WHERE tg_id = ?",
            (tg_id,),
        )
        return [
            PlatformLink(
                tg_id=row["tg_id"],
                platform=row["platform"],
                external_id=row["external_id"],
                display_name=row["display_name"],
                linked_at=row["linked_at"],
                psn_trophy_level=row["psn_trophy_level"],
                achievements_visible=(
                    bool(row["achievements_visible"])
                    if row["achievements_visible"] is not None
                    else None
                ),
                achievements_visible_checked_at=row["achievements_visible_checked_at"],
            )
            for row in await cursor.fetchall()
        ]

    async def set_psn_trophy_level(self, tg_id: int, level: int) -> None:
        """Called by poller/psn_fetcher.py after backfill and after each poll
        that finds new trophies (Follow-up 2026-09-06) — level can only
        change when a trophy is earned, so there is no reason to touch this
        on a tick that found nothing."""
        await self._conn.execute(
            "UPDATE platform_links SET psn_trophy_level = ? WHERE tg_id = ? AND platform = 'psn'",
            (level, tg_id),
        )
        await self._conn.commit()

    async def set_achievements_visible(self, tg_id: int, platform: str, visible: bool) -> None:
        """Set at connect time and refreshed by every backfill/resync (#5,
        SteamFetcher/PsnFetcher) — /panel's login row and the admin card read
        this to show the last actually-checked achievement/trophy
        visibility, and when it was checked, not nothing."""
        await self._conn.execute(
            "UPDATE platform_links SET achievements_visible = ?,"
            "       achievements_visible_checked_at = ? "
            "WHERE tg_id = ? AND platform = ?",
            (int(visible), utcnow_iso(), tg_id, platform),
        )
        await self._conn.commit()

    async def platform_links_all(self, platform: str) -> list[PlatformLink]:
        """Every linked account on one platform, across every user —
        `platform_links_of` narrowed to one person, this is the admin-wide
        counterpart (2026-09-05, scripts/backfill_steam_titles.py: needs
        every Steam link to reconcile, not any one person's).

        `psn_trophy_level` is selected too (Follow-up 2026-09-08,
        scripts/backfill_psn_levels.py: needs to tell "already cached" apart
        from "never cached" per link) — always NULL for a non-PSN platform,
        harmless to always select.
        """
        cursor = await self._conn.execute(
            "SELECT tg_id, platform, external_id, display_name, linked_at, psn_trophy_level,"
            "       achievements_visible, achievements_visible_checked_at "
            "FROM platform_links WHERE platform = ?",
            (platform,),
        )
        return [
            PlatformLink(
                tg_id=row["tg_id"],
                platform=row["platform"],
                external_id=row["external_id"],
                display_name=row["display_name"],
                linked_at=row["linked_at"],
                psn_trophy_level=row["psn_trophy_level"],
                achievements_visible=(
                    bool(row["achievements_visible"])
                    if row["achievements_visible"] is not None
                    else None
                ),
                achievements_visible_checked_at=row["achievements_visible_checked_at"],
            )
            for row in await cursor.fetchall()
        ]

    async def unlink_platform_account(self, tg_id: int, platform: str) -> None:
        await self._conn.execute(
            "DELETE FROM platform_links WHERE tg_id = ? AND platform = ?", (tg_id, platform)
        )
        await self._conn.commit()
