"""Bilingual achievement/trophy description cache — `achievement_description_cache`
(2026-09-09 user request). One mixin of bot.db.repo.Repo (2026-09-09 split; see
this package's own __init__.py). Shared across every platform (Xbox, Steam,
PSN), unlike `_platform_links.py`'s own Steam-specific schema/rarity caches —
see schema.sql's own comment on the table for why this is keyed by the
achievement itself, not by who unlocked it.
"""

from __future__ import annotations

from bot.db.repo._models import CachedDescription
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
