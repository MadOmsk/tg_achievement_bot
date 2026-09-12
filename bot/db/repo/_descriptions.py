"""Bilingual achievement/trophy description cache — `achievement_description_cache`
(2026-09-09 user request). One mixin of bot.db.repo.Repo (2026-09-09 split; see
this package's own __init__.py). Shared across every platform (Xbox, Steam,
PSN), unlike `_platform_links.py`'s own Steam-specific schema/rarity caches —
see schema.sql's own comment on the table for why this is keyed by the
achievement itself, not by who unlocked it.
"""

from __future__ import annotations

from bot.db.repo._models import CachedDescription
from bot.db.repo._sql import OWNED_BY_PERSON
from bot.util import utcnow_iso


class _DescriptionsRepo:
    async def get_cached_description(
        self, platform: str, title_id: str, achievement_id: str
    ) -> CachedDescription | None:
        cursor = await self._conn.execute(
            "SELECT description_ru, description_en, source FROM achievement_description_cache "
            "WHERE platform = ? AND title_id = ? AND achievement_id = ?",
            (platform, title_id, achievement_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return CachedDescription(
            description_ru=row["description_ru"],
            description_en=row["description_en"],
            source=row["source"],
        )

    async def uncached_descriptions(self) -> list[tuple[str, str, str, int, str]]:
        """Every stored achievement that has a description but no cache entry
        — the whole input of the one-time backfill
        (scripts/backfill_descriptions.py, #48).

        Returns (platform, title_id, achievement_id, tg_id, external_id) so
        the caller can group by title and still know whose credentials can be
        used to ask for it: Xbox needs a token-bearing owner, Steam a
        SteamID64, PSN an account_id — all of which live in `xuid` for their
        own platform's rows. The owner comes from the account's *current*
        link (#52), so an account nobody holds any more contributes nothing
        here either: there would be no credentials to ask with.

        Rows with no description are excluded here rather than by the caller:
        there is nothing to translate, so they are not a gap.
        """
        cursor = await self._conn.execute(
            "SELECT s.platform, s.title_id, s.achievement_id, al.tg_id, s.xuid "
            "FROM seen_achievements s "
            + OWNED_BY_PERSON
            + "LEFT JOIN achievement_description_cache d "
            "       ON d.platform = s.platform AND d.title_id = s.title_id "
            "      AND d.achievement_id = s.achievement_id "
            "WHERE d.achievement_id IS NULL "
            "  AND s.description IS NOT NULL AND TRIM(s.description) <> ''"
        )
        return [
            (row["platform"], row["title_id"], row["achievement_id"], row["tg_id"], row["xuid"])
            for row in await cursor.fetchall()
        ]

    async def uncached_description_titles(
        self, platforms: tuple[str, ...], limit: int
    ) -> list[tuple[str, str, int]]:
        """A few titles at a time that still have uncached descriptions, as
        (platform, title_id, tg_id) — the poller's own small bite
        (poller/description_backfill.py, 2026-09-11 user request).

        Deliberately not `uncached_descriptions()` above: that returns the
        whole gap, which is tens of thousands of rows and fine for a one-off
        script but absurd to run every minute. This asks only for as many
        titles as the next tick can actually fetch, and stops there.

        `tg_id` is any one owner of the title — the description belongs to
        the game, not the person, so whoever the group-by happens to pick is
        as good as any other; the caller falls back to another owner itself
        if that one's token turns out to be dead.
        """
        placeholders = ", ".join("?" * len(platforms))
        cursor = await self._conn.execute(
            "SELECT s.platform, s.title_id, MIN(al.tg_id) AS tg_id "
            "FROM seen_achievements s "
            + OWNED_BY_PERSON
            + "LEFT JOIN achievement_description_cache d "
            "       ON d.platform = s.platform AND d.title_id = s.title_id "
            "      AND d.achievement_id = s.achievement_id "
            f"WHERE d.achievement_id IS NULL AND s.platform IN ({placeholders}) "
            "  AND s.description IS NOT NULL AND TRIM(s.description) <> '' "
            "GROUP BY s.platform, s.title_id "
            "LIMIT ?",
            (*platforms, limit),
        )
        return [(row["platform"], row["title_id"], row["tg_id"]) for row in await cursor.fetchall()]

    async def cached_descriptions(
        self, keys: list[tuple[str, str, str]]
    ) -> dict[tuple[str, str, str], CachedDescription]:
        """The bulk form of `get_cached_description` above, for the render
        path (#48): a digest can carry a whole game's worth of achievements,
        and the anti-flood digest can carry several games across several
        platforms, so one query per achievement would be one query per line
        of a message.

        Keyed by the full (platform, title_id, achievement_id) triple rather
        than one shared title, because that flood digest genuinely mixes
        them. Missing keys are simply absent from the result.
        """
        if not keys:
            return {}
        clause = " OR ".join(["(platform = ? AND title_id = ? AND achievement_id = ?)"] * len(keys))
        parameters = [value for key in keys for value in key]
        cursor = await self._conn.execute(
            "SELECT platform, title_id, achievement_id, description_ru, description_en, source "
            f"FROM achievement_description_cache WHERE {clause}",
            parameters,
        )
        return {
            (row["platform"], row["title_id"], row["achievement_id"]): CachedDescription(
                description_ru=row["description_ru"],
                description_en=row["description_en"],
                source=row["source"],
            )
            for row in await cursor.fetchall()
        }

    async def cache_description(
        self,
        platform: str,
        title_id: str,
        achievement_id: str,
        *,
        description_ru: str | None,
        description_en: str | None,
        source: str,
    ) -> None:
        await self._conn.execute(
            "INSERT INTO achievement_description_cache"
            " (platform, title_id, achievement_id, description_ru, description_en,"
            "  source, cached_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(platform, title_id, achievement_id) DO UPDATE SET"
            " description_ru = excluded.description_ru,"
            " description_en = excluded.description_en,"
            " source = excluded.source,"
            " cached_at = excluded.cached_at",
            (
                platform,
                title_id,
                achievement_id,
                description_ru,
                description_en,
                source,
                utcnow_iso(),
            ),
        )
        await self._conn.commit()
