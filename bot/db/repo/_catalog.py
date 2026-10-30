"""Full game achievement catalog repo mixin — `title_achievements` (Issue #99, #80)."""

from __future__ import annotations

import json

from bot.constants import MAIN_GAME_GROUP, achievement_group
from bot.db.repo._models import TitleAchievementRow, TitleAchievementWithUnlock
from bot.db.repo._sql import platform_is
from bot.db.repo._tx import GatedConnection
from bot.util import looks_russian, utcnow_iso


def _group_source(platform: str, group_id: str | None) -> str | None:
    """A group a platform's answer carried is the platform's; Steam's is our
    stand-in (`main_game`), no source."""
    group = achievement_group(platform, group_id)
    return "platform" if group and group != MAIN_GAME_GROUP else None


class _CatalogRepo:
    _conn: GatedConnection

    async def upsert_title_achievements(
        self, rows: list[TitleAchievementRow], *, complete: bool = False
    ) -> None:
        """Upsert a game's full or partial achievement catalog.

        `complete` says the rows are the game's *whole* list (#119) — the
        catalog refresh, Steam's per-game response. A live poll that holds
        only what one person earned passes False: its rows still land, but
        do not become the game's list, or one person's unlocks would pass for
        the whole game (and count as a 100% completion)."""
        if not rows:
            return
        now = utcnow_iso()
        for r in rows:
            updated_at = r.updated_at or now
            # The platform answers a Russian request with its English (or a
            # placeholder) when it has no Russian, and storing that as
            # `description_ru` made every reader take it for a translation
            # (#127). A Russian side is kept only when it reads as Russian;
            # the translator settles the rest.
            description_ru = r.description_ru if looks_russian(r.description_ru) else None
            await self._conn.execute(
                "INSERT INTO title_achievements ("
                "  platform, title_id, achievement_id, name_ru, name_en,"
                "  description_ru, description_en, icon_url, is_secret,"
                "  gamerscore, trophy_type, trophy_group_id, rarity_percent, updated_at,"
                "  listed, group_source"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(platform, title_id, achievement_id) DO UPDATE SET "
                "  name_ru = COALESCE(excluded.name_ru, title_achievements.name_ru),"
                "  name_en = COALESCE(excluded.name_en, title_achievements.name_en),"
                # Once a description went through the translator
                # (description_source set), it is the translator's: the raw
                # pair a refresh passes by must not overwrite a translation.
                "  description_ru = CASE WHEN title_achievements.description_source"
                "      IS NOT NULL THEN title_achievements.description_ru"
                "      ELSE COALESCE(excluded.description_ru, title_achievements.description_ru)"
                "  END,"
                "  description_en = CASE WHEN title_achievements.description_source"
                "      IS NOT NULL THEN title_achievements.description_en"
                "      ELSE COALESCE(excluded.description_en, title_achievements.description_en)"
                "  END,"
                "  icon_url = COALESCE(excluded.icon_url, title_achievements.icon_url),"
                "  is_secret = excluded.is_secret,"
                "  gamerscore = COALESCE(excluded.gamerscore, title_achievements.gamerscore),"
                "  trophy_type = COALESCE(excluded.trophy_type, title_achievements.trophy_type),"
                "  trophy_group_id = COALESCE(excluded.trophy_group_id, "
                "                             title_achievements.trophy_group_id),"
                # The platform's own group replaces one we derived.
                "  group_source = CASE WHEN excluded.trophy_group_id IS NOT NULL"
                "   THEN excluded.group_source ELSE title_achievements.group_source END,"
                "  rarity_percent = COALESCE(excluded.rarity_percent, "
                "                            title_achievements.rarity_percent),"
                "  updated_at = excluded.updated_at,"
                "  listed = GREATEST(title_achievements.listed, excluded.listed)",
                (
                    r.platform,
                    r.title_id,
                    r.achievement_id,
                    r.name_ru,
                    r.name_en,
                    description_ru,
                    r.description_en,
                    r.icon_url,
                    1 if r.is_secret else 0,
                    r.gamerscore,
                    r.trophy_type,
                    achievement_group(r.platform, r.trophy_group_id),
                    r.rarity_percent,
                    updated_at,
                    1 if complete else 0,
                    _group_source(r.platform, r.trophy_group_id),
                ),
            )
        # A 360 list read whole is grouped by its ids and gamerscore (it says
        # nothing of its groups itself; `xbox_models.x360_groups`).
        if complete:
            for title_id in {r.title_id for r in rows if r.platform == "xbox_360"}:
                await self.derive_x360_groups(title_id, commit=False)
        # An Xbox list read whole gives each achievement its group (base or
        # non_base, 2026-10-15); the rows people earned take it from here,
        # and its Mythic and completion can be told (mark_xbox_completions,
        # after the commit below).
        for platform, title_id in {
            (r.platform, r.title_id) for r in rows if r.platform in ("xbox_modern", "xbox_360")
        }:
            await self._conn.execute(
                "UPDATE seen_achievements SET trophy_group_id = (SELECT ta.trophy_group_id"
                "  FROM title_achievements ta WHERE ta.platform = seen_achievements.platform"
                "  AND ta.title_id = seen_achievements.title_id"
                "  AND ta.achievement_id = seen_achievements.achievement_id)"
                " WHERE platform = ? AND title_id = ? AND trophy_group_id IS NULL",
                (platform, title_id),
            )
        await self._conn.commit()
        if complete:
            for platform, title_id in {
                (r.platform, r.title_id) for r in rows if r.platform in ("xbox_modern", "xbox_360")
            }:
                await self.mark_xbox_completions_of_title(platform, title_id)

    async def mark_xbox_completions(self, platform: str, xuid: str, title_id: str) -> None:
        """An account's Mythic and completion of one Xbox game (owner,
        2026-10-16): once every achievement of its base list is earned, the
        last of them earned is marked `mythic`; once every achievement of its
        whole list is, the last is marked `completes`. Only a list read whole
        (`listed`) counts, the base list only where its groups are known.
        A Mythic is kept for good; a completion is taken back when the list
        grows past what was earned, and marked again on its new last one."""
        cursor = await self._conn.execute(
            "SELECT achievement_id, trophy_group_id FROM title_achievements"
            " WHERE platform = ? AND title_id = ? AND listed = 1",
            (platform, title_id),
        )
        listed = {str(r[0]): r[1] for r in await cursor.fetchall()}
        if not listed:
            return
        cursor = await self._conn.execute(
            "SELECT achievement_id, COALESCE(unlocked_at, created_at) AS at, mythic, completes"
            " FROM seen_achievements WHERE platform = ? AND xuid = ? AND title_id = ?",
            (platform, xuid, title_id),
        )
        earned = {
            str(r[0]): (str(r[1] or ""), int(r[2]), int(r[3])) for r in await cursor.fetchall()
        }
        if not earned:
            return

        def last_of(ids: set[str]) -> str:
            return max(ids, key=lambda a: (earned[a][0], a))

        marks: list[tuple[str, str]] = []
        base = {a for a, group in listed.items() if group == "base"}
        if base and base <= earned.keys() and not any(v[1] for v in earned.values()):
            marks.append(("mythic", last_of(base)))
        complete = listed.keys() <= earned.keys()
        if complete and not any(v[2] for v in earned.values()):
            marks.append(("completes", last_of(set(listed))))
        if not complete and any(v[2] for v in earned.values()):
            # The list grew (a DLC, an update): the game is not complete any
            # more, until its new last achievement is earned. A Mythic stays —
            # its base list never grows (owner, 2026-10-16).
            await self._conn.execute(
                "UPDATE seen_achievements SET completes = 0"
                " WHERE platform = ? AND xuid = ? AND title_id = ? AND completes = 1",
                (platform, xuid, title_id),
            )
            await self._conn.commit()
        for column, achievement_id in marks:
            await self._conn.execute(
                f"UPDATE seen_achievements SET {column} = 1"
                " WHERE platform = ? AND xuid = ? AND title_id = ? AND achievement_id = ?",
                (platform, xuid, title_id, achievement_id),
            )
        if marks:
            await self._conn.commit()

    async def completion_marks(self) -> dict[str, int]:
        """How many Mythics and completions are marked, per platform."""
        cursor = await self._conn.execute(
            "SELECT platform, SUM(mythic), SUM(completes) FROM seen_achievements GROUP BY platform"
        )
        return {
            f"{r[0]} mythic/complete": f"{int(r[1] or 0)}/{int(r[2] or 0)}"  # type: ignore[misc]
            for r in await cursor.fetchall()
        }

    async def mark_xbox_completions_of_title(self, platform: str, title_id: str) -> None:
        """Every account's marks in one game — when its list was read whole."""
        cursor = await self._conn.execute(
            "SELECT DISTINCT xuid FROM seen_achievements WHERE platform = ? AND title_id = ?",
            (platform, title_id),
        )
        for row in await cursor.fetchall():
            await self.mark_xbox_completions(platform, str(row[0]), title_id)

    async def derive_x360_groups(self, title_id: str, *, commit: bool = True) -> int:
        """A 360 list's groups, derived from its listed achievements' ids and
        gamerscore. The number of achievements grouped."""
        from bot.services.xbox.models import x360_groups

        cursor = await self._conn.execute(
            "SELECT achievement_id, gamerscore FROM title_achievements"
            " WHERE platform = 'xbox_360' AND title_id = ? AND listed = 1",
            (title_id,),
        )
        listed = [(str(r[0]), int(r[1] or 0)) for r in await cursor.fetchall()]
        for achievement_id, group in x360_groups(title_id, listed).items():
            # Derived, never over what the platform said itself.
            await self._conn.execute(
                "UPDATE title_achievements SET trophy_group_id = ?, group_source = 'derived'"
                " WHERE platform = 'xbox_360' AND title_id = ? AND achievement_id = ?"
                " AND group_source IS DISTINCT FROM 'platform'",
                (group, title_id, achievement_id),
            )
            await self._conn.execute(
                "UPDATE seen_achievements SET trophy_group_id = ?, group_source = 'derived'"
                " WHERE platform = 'xbox_360' AND title_id = ? AND achievement_id = ?"
                " AND group_source IS DISTINCT FROM 'platform'",
                (group, title_id, achievement_id),
            )
        if commit:
            await self._conn.commit()
        return len(listed)

    async def set_achievement_groups(
        self, platform: str, title_id: str, groups: dict[str, str]
    ) -> int:
        """Each achievement's group as its platform told it (Xbox's base /
        non_base), on the list and on the rows people earned. The number of
        list rows that took one."""
        changed = 0
        async with self.transaction():
            for achievement_id, group in groups.items():
                cursor = await self._conn.execute(
                    "UPDATE title_achievements SET trophy_group_id = ?, group_source = 'platform'"
                    " WHERE platform = ? AND title_id = ? AND achievement_id = ?",
                    (group, platform, title_id, achievement_id),
                )
                changed += cursor.rowcount
                await self._conn.execute(
                    "UPDATE seen_achievements SET trophy_group_id = ?, group_source = 'platform'"
                    " WHERE platform = ? AND title_id = ? AND achievement_id = ?",
                    (group, platform, title_id, achievement_id),
                )
        return changed

    async def get_title_achievements(
        self, platform: str, title_id: str
    ) -> list[TitleAchievementRow]:
        """All achievements in the catalog for one game."""
        cursor = await self._conn.execute(
            "SELECT platform, title_id, achievement_id, name_ru, name_en, "
            "       description_ru, description_en, icon_url, is_secret, "
            "       gamerscore, trophy_type, trophy_group_id, rarity_percent, updated_at,"
            "       description_source "
            "FROM title_achievements "
            "WHERE platform = ? AND title_id = ? AND listed = 1 "
            "ORDER BY seq ASC",
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
                description_source=row["description_source"],
            )
            for row in rows
        ]

    async def achievement_name_pair(
        self, platform: str, title_id: str, achievement_id: str
    ) -> tuple[str | None, str | None]:
        """One achievement's two names, Russian and English, as the platform
        gave them."""
        cursor = await self._conn.execute(
            "SELECT name_ru, name_en FROM title_achievements"
            " WHERE platform = ? AND title_id = ? AND achievement_id = ?",
            (platform, title_id, achievement_id),
        )
        row = await cursor.fetchone()
        return (row["name_ru"], row["name_en"]) if row else (None, None)

    async def title_achievement_names(
        self, platform: str, title_id: str
    ) -> list[TitleAchievementRow]:
        """Every achievement known for the game — its whole list, or, for a game
        whose list was never read, the ones people earned — with its names and
        descriptions, except PlayStation's platinum. For matching text (the Steam
        guides' tips) where knowing the name is enough."""
        cursor = await self._conn.execute(
            "SELECT platform, title_id, achievement_id, name_ru, name_en,"
            "       description_ru, description_en "
            "FROM title_achievements WHERE platform = ? AND title_id = ? "
            # PlayStation's platinum is for having every other trophy: no guide
            # has anything to say about it.
            "  AND COALESCE(trophy_type, '') <> 'platinum' "
            "ORDER BY seq ASC",
            (platform, title_id),
        )
        return [
            TitleAchievementRow(
                platform=row["platform"],
                title_id=row["title_id"],
                achievement_id=row["achievement_id"],
                name_ru=row["name_ru"],
                name_en=row["name_en"],
                description_ru=row["description_ru"],
                description_en=row["description_en"],
            )
            for row in await cursor.fetchall()
        ]

    async def title_achievements_count(self, platform: str, title_id: str) -> int:
        """How many achievements are currently in catalog for this game."""
        cursor = await self._conn.execute(
            "SELECT COUNT(*) AS c FROM title_achievements"
            " WHERE platform = ? AND title_id = ? AND listed = 1",
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
                "WHERE ta.platform = ? AND ta.title_id = ? AND ta.listed = 1 "
                "ORDER BY ta.seq ASC",
                (xuid, platform, title_id),
            )
        else:
            cursor = await self._conn.execute(
                "SELECT ta.platform, ta.title_id, ta.achievement_id, ta.name_ru, ta.name_en, "
                "       ta.description_ru, ta.description_en, ta.icon_url, ta.is_secret, "
                "       ta.gamerscore, ta.trophy_type, ta.trophy_group_id, ta.rarity_percent, "
                "       ta.updated_at, NULL AS unlocked_at "
                "FROM title_achievements ta "
                "WHERE ta.platform = ? AND ta.title_id = ? AND ta.listed = 1 "
                "ORDER BY ta.seq ASC",
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

    async def title_achievements_checked_at(self, platform: str, title_id: str) -> str | None:
        """When this title's achievement catalog was last verified against the platform API."""
        where, params = platform_is(platform)
        cursor = await self._conn.execute(
            f"SELECT achievements_checked_at FROM achievement_list_connectors WHERE {where} AND "
            f"title_id = ?",
            (*params, title_id),
        )
        row = await cursor.fetchone()
        return row["achievements_checked_at"] if row else None

    async def set_title_achievements_checked_at(
        self, platform: str, title_id: str, checked_at: str | None = None
    ) -> None:
        """Stamp when this title was checked against the platform API."""
        ts = checked_at or utcnow_iso()
        where, params = platform_is(platform)
        await self._conn.execute(
            f"UPDATE achievement_list_connectors SET achievements_checked_at = ? WHERE {where} "
            f"AND title_id = ?",
            (ts, *params, title_id),
        )
        await self._conn.commit()

    async def title_record(self, platform: str, title_id: str) -> dict[str, object] | None:
        """Fetch title record if it exists. `platform` may be `xbox`."""
        where, params = platform_is(platform)
        cursor = await self._conn.execute(
            "SELECT title_id, name, name_ru, name_en, platform, platforms, "
            "       icon_url, achievements_total, cover_path, achievements_checked_at "
            f"FROM achievement_list_connectors WHERE {where} AND title_id = ?",
            (*params, title_id),
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
        # The title, its rows and its catalog move together (#167).
        async with self.transaction():
            if new_platform in ("xbox_360", "x360"):
                new_plat, old_plat = "xbox_360", "xbox_modern"
            elif new_platform == "xbox_modern":
                new_plat, old_plat = "xbox_modern", "xbox_360"
            else:
                return
            await self._move_title_rows(title_id, old_plat, new_plat)
            if new_plat == "xbox_360":
                await self._conn.execute(
                    "UPDATE achievement_list_connectors SET platforms = '[\"Xbox360\"]'"
                    " WHERE platform = 'xbox_360' AND title_id = ?",
                    (title_id,),
                )

    # What a game's row keeps when it moves onto a row the other generation
    # already has: whatever the target has not learned yet.
    _MERGED_TITLE_COLUMNS = (
        "name_ru",
        "name_en",
        "platforms",
        "icon_url",
        "achievements_total",
        "cover_path",
        "cover_hash",
        "cover_checked_at",
        "achievements_checked_at",
        "tips_checked_at",
    )

    async def _move_title_rows(self, title_id: str, old_plat: str, new_plat: str) -> None:
        """A game, its earned rows and its catalog move to another Xbox
        platform together (#167): moving only `seen_achievements` left the
        names, descriptions, rarity and listed size behind. The `titles` row
        is keyed by its platform (090): it moves too, and onto a row the other
        generation already has, it fills what that one lacks and goes. No
        commit — the caller's."""
        merged = ", ".join(
            f"{column} = COALESCE(achievement_list_connectors.{column}, o.{column})"
            for column in self._MERGED_TITLE_COLUMNS
        )
        await self._conn.execute(
            f"UPDATE achievement_list_connectors SET {merged} FROM achievement_list_connectors o "
            "WHERE achievement_list_connectors.platform = ? AND "
            "achievement_list_connectors.title_id = ?"
            "  AND o.platform = ? AND o.title_id = achievement_list_connectors.title_id",
            (new_plat, title_id, old_plat),
        )
        await self._conn.execute(
            # Each "UPDATE OR IGNORE" of SQLite is an update of the rows the
            # new key leaves free (#234); the rest go with the DELETE after.
            "UPDATE achievement_list_connectors SET platform = ? WHERE platform = ?"
            " AND title_id = ? AND NOT EXISTS (SELECT 1 FROM achievement_list_connectors o"
            "  WHERE o.platform = ? AND o.title_id = achievement_list_connectors.title_id)",
            (new_plat, old_plat, title_id, new_plat),
        )
        await self._conn.execute(
            "DELETE FROM achievement_list_connectors WHERE platform = ? AND title_id = ?",
            (old_plat, title_id),
        )
        # When its HLTB entry was last asked about is the list's too.
        await self._conn.execute(
            "UPDATE fetch_state SET subject = ? WHERE source = 'hltb_match' AND subject = ?"
            " AND NOT EXISTS (SELECT 1 FROM fetch_state o"
            "  WHERE o.source = fetch_state.source AND o.subject = ?)",
            (f"{new_plat}:{title_id}", f"{old_plat}:{title_id}", f"{new_plat}:{title_id}"),
        )
        await self._conn.execute(
            "DELETE FROM fetch_state WHERE source = 'hltb_match' AND subject = ?",
            (f"{old_plat}:{title_id}",),
        )
        await self._conn.execute(
            "UPDATE fetch_state SET subject = ? WHERE source = 'steam_app' AND subject = ?"
            " AND NOT EXISTS (SELECT 1 FROM fetch_state o"
            "  WHERE o.source = fetch_state.source AND o.subject = ?)",
            (f"{new_plat}:{title_id}", f"{old_plat}:{title_id}", f"{new_plat}:{title_id}"),
        )
        await self._conn.execute(
            "DELETE FROM fetch_state WHERE source = 'steam_app' AND subject = ?",
            (f"{old_plat}:{title_id}",),
        )
        # The versions whose list it is follow it (2026-10-14: they used to be
        # left on the old generation, pointing at a list that was gone).
        await self._conn.execute(
            "UPDATE versions SET platform = ? WHERE platform = ? AND title_id = ?",
            (new_plat, old_plat, title_id),
        )
        cursor = await self._conn.execute(
            "SELECT version_id FROM versions WHERE platform = ? AND title_id = ?",
            (new_plat, title_id),
        )
        for row in await cursor.fetchall():
            ids = await self.store_ids_of(int(row[0]))
            moved = [
                ("list", f"{new_plat}:{title_id}") if i == ("list", f"{old_plat}:{title_id}") else i
                for i in ids
            ]
            await self._conn.execute(
                "UPDATE versions SET store_ids = ? WHERE version_id = ?",
                (json.dumps(list(dict.fromkeys(moved))), int(row[0])),
            )
        await self._conn.execute(
            "UPDATE title_guide_reads SET platform = ? WHERE platform = ? AND title_id = ?"
            " AND NOT EXISTS (SELECT 1 FROM title_guide_reads o WHERE o.platform = ?"
            "  AND o.title_id = title_guide_reads.title_id"
            "  AND o.guide_id = title_guide_reads.guide_id)",
            (new_plat, old_plat, title_id, new_plat),
        )
        await self._conn.execute(
            "DELETE FROM title_guide_reads WHERE platform = ? AND title_id = ?",
            (old_plat, title_id),
        )
        await self._conn.execute(
            "UPDATE seen_achievements SET platform = ? WHERE title_id = ? AND platform = ?"
            " AND NOT EXISTS (SELECT 1 FROM seen_achievements o WHERE o.platform = ?"
            "  AND o.xuid = seen_achievements.xuid AND o.title_id = seen_achievements.title_id"
            "  AND o.achievement_id = seen_achievements.achievement_id)",
            (new_plat, title_id, old_plat, new_plat),
        )
        await self._conn.execute(
            "DELETE FROM seen_achievements WHERE title_id = ? AND platform = ?",
            (title_id, old_plat),
        )
        await self._conn.execute(
            "UPDATE title_achievements SET platform = ? WHERE title_id = ? AND platform = ?"
            " AND NOT EXISTS (SELECT 1 FROM title_achievements o WHERE o.platform = ?"
            "  AND o.title_id = title_achievements.title_id"
            "  AND o.achievement_id = title_achievements.achievement_id)",
            (new_plat, title_id, old_plat, new_plat),
        )
        await self._conn.execute(
            "DELETE FROM title_achievements WHERE title_id = ? AND platform = ?",
            (title_id, old_plat),
        )
