"""Full game achievement catalog repo mixin — `title_achievements` (Issue #99, #80)."""

from __future__ import annotations

import aiosqlite

from bot.db.repo._models import TitleAchievementRow, TitleAchievementWithUnlock
from bot.util import utcnow_iso


class _CatalogRepo:
    _conn: aiosqlite.Connection

    async def upsert_title_achievements(self, rows: list[TitleAchievementRow]) -> None:
        """Upsert a game's full or partial achievement catalog."""
        if not rows:
            return
        now = utcnow_iso()
        for r in rows:
            updated_at = r.updated_at or now
            await self._conn.execute(
                "INSERT INTO title_achievements ("
                "  platform, title_id, achievement_id, name_ru, name_en,"
                "  description_ru, description_en, icon_url, is_secret,"
                "  gamerscore, trophy_type, trophy_group_id, rarity_percent, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(platform, title_id, achievement_id) DO UPDATE SET "
                "  name_ru = COALESCE(excluded.name_ru, title_achievements.name_ru),"
                "  name_en = COALESCE(excluded.name_en, title_achievements.name_en),"
                "  description_ru = COALESCE(excluded.description_ru, "
                "                            title_achievements.description_ru),"
                "  description_en = COALESCE(excluded.description_en, "
                "                            title_achievements.description_en),"
                "  icon_url = COALESCE(excluded.icon_url, title_achievements.icon_url),"
                "  is_secret = excluded.is_secret,"
                "  gamerscore = COALESCE(excluded.gamerscore, title_achievements.gamerscore),"
                "  trophy_type = COALESCE(excluded.trophy_type, title_achievements.trophy_type),"
                "  trophy_group_id = COALESCE(excluded.trophy_group_id, "
                "                             title_achievements.trophy_group_id),"
                "  rarity_percent = COALESCE(excluded.rarity_percent, "
                "                            title_achievements.rarity_percent),"
                "  updated_at = excluded.updated_at",
                (
                    r.platform,
                    r.title_id,
                    r.achievement_id,
                    r.name_ru,
                    r.name_en,
                    r.description_ru,
                    r.description_en,
                    r.icon_url,
                    1 if r.is_secret else 0,
                    r.gamerscore,
                    r.trophy_type,
                    r.trophy_group_id,
                    r.rarity_percent,
                    updated_at,
                ),
            )
        await self._conn.commit()

    async def get_title_achievements(
        self, platform: str, title_id: str
    ) -> list[TitleAchievementRow]:
        """All achievements in the catalog for one game."""
        cursor = await self._conn.execute(
            "SELECT platform, title_id, achievement_id, name_ru, name_en, "
            "       description_ru, description_en, icon_url, is_secret, "
            "       gamerscore, trophy_type, trophy_group_id, rarity_percent, updated_at "
            "FROM title_achievements "
            "WHERE platform = ? AND title_id = ? "
            "ORDER BY rowid ASC",
            (platform, title_id),
        )
        rows = await cursor.fetchall()
        return [
            TitleAchievementRow(
                platform=row["platform"],
                title_id=row["title_id"],
                achievement_id=row["achievement_id"],
                name_ru=row["name_ru"],
                name_en=row["name_en"],
                description_ru=row["description_ru"],
                description_en=row["description_en"],
                icon_url=row["icon_url"],
                is_secret=bool(row["is_secret"]),
                gamerscore=row["gamerscore"],
                trophy_type=row["trophy_type"],
                trophy_group_id=row["trophy_group_id"],
                rarity_percent=row["rarity_percent"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    async def title_achievements_count(self, platform: str, title_id: str) -> int:
        """How many achievements are currently in catalog for this game."""
        cursor = await self._conn.execute(
            "SELECT COUNT(*) AS c FROM title_achievements WHERE platform = ? AND title_id = ?",
            (platform, title_id),
        )
        row = await cursor.fetchone()
        return int(row["c"]) if row else 0

    async def get_title_achievements_with_user_unlocks(
        self, platform: str, title_id: str, xuid: str | None = None
    ) -> list[TitleAchievementWithUnlock]:
        """All achievements of a game merged with user's unlock history."""
        if xuid:
            cursor = await self._conn.execute(
                "SELECT ta.platform, ta.title_id, ta.achievement_id, ta.name_ru, ta.name_en, "
                "       ta.description_ru, ta.description_en, ta.icon_url, ta.is_secret, "
                "       ta.gamerscore, ta.trophy_type, ta.trophy_group_id, ta.rarity_percent, "
                "       ta.updated_at, sa.unlocked_at "
                "FROM title_achievements ta "
                "LEFT JOIN seen_achievements sa "
                "  ON sa.platform = ta.platform AND sa.title_id = ta.title_id "
                " AND sa.achievement_id = ta.achievement_id AND sa.xuid = ? "
                "WHERE ta.platform = ? AND ta.title_id = ? "
                "ORDER BY ta.rowid ASC",
                (xuid, platform, title_id),
            )
        else:
            cursor = await self._conn.execute(
                "SELECT ta.platform, ta.title_id, ta.achievement_id, ta.name_ru, ta.name_en, "
                "       ta.description_ru, ta.description_en, ta.icon_url, ta.is_secret, "
                "       ta.gamerscore, ta.trophy_type, ta.trophy_group_id, ta.rarity_percent, "
                "       ta.updated_at, NULL AS unlocked_at "
                "FROM title_achievements ta "
                "WHERE ta.platform = ? AND ta.title_id = ? "
                "ORDER BY ta.rowid ASC",
                (platform, title_id),
            )
        rows = await cursor.fetchall()
        return [
            TitleAchievementWithUnlock(
                achievement=TitleAchievementRow(
                    platform=row["platform"],
                    title_id=row["title_id"],
                    achievement_id=row["achievement_id"],
                    name_ru=row["name_ru"],
                    name_en=row["name_en"],
                    description_ru=row["description_ru"],
                    description_en=row["description_en"],
                    icon_url=row["icon_url"],
                    is_secret=bool(row["is_secret"]),
                    gamerscore=row["gamerscore"],
                    trophy_type=row["trophy_type"],
                    trophy_group_id=row["trophy_group_id"],
                    rarity_percent=row["rarity_percent"],
                    updated_at=row["updated_at"],
                ),
                is_unlocked=row["unlocked_at"] is not None,
                unlocked_at=row["unlocked_at"],
            )
            for row in rows
        ]

    async def title_achievements_checked_at(self, title_id: str) -> str | None:
        """When this title's achievement catalog was last verified against the platform API."""
        cursor = await self._conn.execute(
            "SELECT achievements_checked_at FROM titles WHERE title_id = ?",
            (title_id,),
        )
        row = await cursor.fetchone()
        return row["achievements_checked_at"] if row else None

    async def set_title_achievements_checked_at(
        self, title_id: str, checked_at: str | None = None
    ) -> None:
        """Stamp when this title was checked against the platform API."""
        ts = checked_at or utcnow_iso()
        await self._conn.execute(
            "UPDATE titles SET achievements_checked_at = ? WHERE title_id = ?",
            (ts, title_id),
        )
        await self._conn.commit()

    async def title_record(self, title_id: str) -> dict[str, object] | None:
        """Fetch title record if it exists."""
        cursor = await self._conn.execute(
            "SELECT title_id, name, name_ru, name_en, platform, platforms, "
            "       icon_url, achievements_total, cover_path, achievements_checked_at "
            "FROM titles WHERE title_id = ?",
            (title_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return dict(row)

    async def get_title_groups(self, title_id: str) -> list[dict[str, object]]:
        """Return cached trophy groups for a title (PSN DLCs / base game)."""
        cursor = await self._conn.execute(
            "SELECT group_id, name, total, name_ru, name_en FROM title_groups "
            "WHERE title_id = ? ORDER BY group_id",
            (title_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "group_id": row["group_id"],
                "name": row["name"],
                "total": row["total"],
                "name_ru": row["name_ru"],
                "name_en": row["name_en"],
            }
            for row in rows
        ]

    async def achievement_icon_url(
        self, platform: str, title_id: str, achievement_id: str
    ) -> str | None:
        """Return the icon URL for an achievement from title_achievements or seen_achievements."""
        cursor = await self._conn.execute(
            "SELECT icon_url FROM title_achievements "
            "WHERE platform = ? AND title_id = ? AND achievement_id = ? AND icon_url IS NOT NULL "
            "LIMIT 1",
            (platform, title_id, achievement_id),
        )
        row = await cursor.fetchone()
        if row and row["icon_url"]:
            return str(row["icon_url"])

        cursor = await self._conn.execute(
            "SELECT icon_url FROM seen_achievements "
            "WHERE platform = ? AND title_id = ? AND achievement_id = ? AND icon_url IS NOT NULL "
            "LIMIT 1",
            (platform, title_id, achievement_id),
        )
        row = await cursor.fetchone()
        if row and row["icon_url"]:
            return str(row["icon_url"])

        if platform in ("xbox_360", "xbox360"):
            from bot.services.xbox.models import x360_achievement_icon_url

            return x360_achievement_icon_url(title_id, achievement_id)

        return None

    async def update_title_platform(self, title_id: str, new_platform: str) -> None:
        """Update platform across titles, seen_achievements, title_achievements (#99, #80)."""
        if new_platform in ("xbox_360", "x360"):
            new_plat = "xbox_360"
            old_plat = "xbox_modern"
            await self._conn.execute(
                "UPDATE titles SET platform = 'xbox_360', platforms = '[\"Xbox360\"]' "
                "WHERE title_id = ?",
                (title_id,),
            )
        elif new_platform == "xbox_modern":
            new_plat = "xbox_modern"
            old_plat = "xbox_360"
            await self._conn.execute(
                "UPDATE titles SET platform = 'xbox_modern' "
                "WHERE title_id = ? AND platform = 'xbox_360'",
                (title_id,),
            )
        else:
            return

        # Migrate seen_achievements
        await self._conn.execute(
            "UPDATE OR IGNORE seen_achievements SET platform = ? "
            "WHERE title_id = ? AND platform = ?",
            (new_plat, title_id, old_plat),
        )
        await self._conn.execute(
            "DELETE FROM seen_achievements WHERE title_id = ? AND platform = ?",
            (title_id, old_plat),
        )

        # Migrate title_achievements
        await self._conn.execute(
            "UPDATE OR IGNORE title_achievements SET platform = ? "
            "WHERE title_id = ? AND platform = ?",
            (new_plat, title_id, old_plat),
        )
        await self._conn.execute(
            "DELETE FROM title_achievements WHERE title_id = ? AND platform = ?",
            (title_id, old_plat),
        )
        await self._conn.commit()
