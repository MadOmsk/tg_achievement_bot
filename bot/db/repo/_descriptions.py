"""An achievement's names, descriptions and rarity, in the catalog
(`title_achievements`) — one mixin of bot.db.repo.Repo.

These methods kept their names from when each fact had a cache table of its
own (descriptions 2026-09-09, names #61, rarity 2026-09-17); the catalog
absorbed all three in #119, so what one path learns every other path sees.
Every write here is a partial upsert: it touches only its own columns, and a
row it creates is filled in by the catalog refresh later.
"""

from __future__ import annotations

from bot.db.repo._models import CachedDescription
from bot.db.repo._sql import OWNED_BY_PERSON
from bot.util import utcnow_iso

# The catalog row of a `seen_achievements s`, as `d`.
_CATALOG_ROW = (
    "LEFT JOIN title_achievements d ON d.platform = s.platform AND d.title_id = s.title_id "
    "      AND d.achievement_id = s.achievement_id "
)

# Whether the game of a `seen_achievements s` has any percentage at all.
_TITLE_HAS_RARITY = (
    "SELECT 1 FROM title_achievements ta WHERE ta.platform = s.platform"
    " AND ta.title_id = s.title_id AND ta.rarity_percent IS NOT NULL"
)


class _DescriptionsRepo:
    # ------------------------------------------------- achievement names (#61)

    async def cache_names(
        self, platform: str, title_id: str, names: dict[str, tuple[str | None, str | None]]
    ) -> None:
        """One game's achievement names in both languages, as the platform
        itself wrote them (#61) — `{achievement_id: (name_ru, name_en)}`.

        Never a translation: a name is only ever the platform's own string
        (CLAUDE.md), so there is nothing here about where it came from, and a
        side the platform did not give stays NULL. Rewriting the same pair is
        free and happens whenever a second-locale response passes by.
        """
        if not names:
            return
        now = utcnow_iso()
        for achievement_id, (name_ru, name_en) in names.items():
            await self._conn.execute(
                "INSERT INTO title_achievements"
                " (platform, title_id, achievement_id, name_ru, name_en, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(platform, title_id, achievement_id) DO UPDATE SET "
                "  name_ru = COALESCE(excluded.name_ru, title_achievements.name_ru),"
                "  name_en = COALESCE(excluded.name_en, title_achievements.name_en),"
                "  updated_at = excluded.updated_at",
                (platform, title_id, achievement_id, name_ru, name_en, now),
            )
        await self._conn.commit()

    # --------------------------------------------------------- rarity (#69's tail)

    async def cache_rarity(self, platform: str, title_id: str, rarity: dict[str, float]) -> None:
        """One game's rarity percentages, `{achievement_id: percent}`.

        A fact about the achievement, not about anyone who earned it, which
        is why it lives here rather than only on the `seen_achievements` rows
        — those are written once with INSERT OR IGNORE and never updated, so
        a row stored before its platform reported a percentage keeps none
        forever. Rewriting the same value is free and happens on every poll
        of a game somebody is playing. Never an expiry: a year-old
        percentage is worth more than none (owner, 2026-09-17).
        """
        if not rarity:
            return
        now = utcnow_iso()
        await self._conn.executemany(
            "INSERT INTO title_achievements"
            " (platform, title_id, achievement_id, rarity_percent, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(platform, title_id, achievement_id) DO UPDATE SET "
            "  rarity_percent = excluded.rarity_percent, updated_at = excluded.updated_at",
            [
                (platform, title_id, achievement_id, percent, now)
                for achievement_id, percent in rarity.items()
            ],
        )
        await self._conn.commit()

    async def titles_missing_rarity(self, platform: str, limit: int) -> list[tuple[str, int]]:
        """Games whose achievements have no cached rarity, rarest-known
        first — `(title_id, tg_id)`, paired with somebody who can be asked.

        Xbox needs a *person's* token to answer for a title (unlike Steam's
        one shared key), so a walker cannot just take a title id: it needs
        one owner. Any owner will do — contract 4 returns the whole title's
        achievement list including the ones that caller never earned, so one
        person's request fills the cache for everybody.
        """
        cursor = await self._conn.execute(
            "SELECT s.title_id, MIN(al.tg_id) AS tg_id "
            "FROM seen_achievements s " + OWNED_BY_PERSON + "WHERE s.platform = ? "
            "  AND NOT EXISTS (" + _TITLE_HAS_RARITY + ") "
            "GROUP BY s.title_id LIMIT ?",
            (platform, limit),
        )
        return [(row["title_id"], int(row["tg_id"])) for row in await cursor.fetchall()]

    async def rarity_coverage(self, platform: str) -> tuple[int, int]:
        """(titles with cached rarity, titles seen at all) — what the walker
        has left to do, for the admin panel and for the one-off script's own
        progress line."""
        cursor = await self._conn.execute(
            "SELECT COUNT(DISTINCT s.title_id),"
            "       COUNT(DISTINCT CASE WHEN EXISTS (" + _TITLE_HAS_RARITY + ")"
            "             THEN s.title_id END) "
            "FROM seen_achievements s "
            "WHERE s.platform = ?",
            (platform,),
        )
        row = await cursor.fetchone()
        return (int(row[1]), int(row[0])) if row else (0, 0)

    async def cached_names(
        self, keys: list[tuple[str, str, str]]
    ) -> dict[tuple[str, str, str], tuple[str | None, str | None]]:
        """The bulk read the render path needs — same shape and the same
        reasoning as `cached_descriptions` below: a digest can carry a whole
        game's worth of achievements, and the anti-flood one can mix games and
        platforms, so one query per line would be one query per line."""
        if not keys:
            return {}
        clause = " OR ".join(["(platform = ? AND title_id = ? AND achievement_id = ?)"] * len(keys))
        parameters = [value for key in keys for value in key]
        cursor = await self._conn.execute(
            "SELECT platform, title_id, achievement_id, name_ru, name_en "
            f"FROM title_achievements WHERE ({clause})"
            "  AND (name_ru IS NOT NULL OR name_en IS NOT NULL)",
            parameters,
        )
        return {
            (row["platform"], row["title_id"], row["achievement_id"]): (
                row["name_ru"],
                row["name_en"],
            )
            for row in await cursor.fetchall()
        }

    async def names_missing(self, platform: str, title_id: str, ids: list[str]) -> set[str]:
        """Which of these achievements have no cached name yet — the other
        half of "is this game's bilingual fetch still worth making" (#61).
        Without it, a game whose descriptions were all cached before names
        existed would never fetch the second locale again, and would keep
        showing English names in a Russian chat forever."""
        if not ids:
            return set()
        placeholders = ", ".join("?" * len(ids))
        cursor = await self._conn.execute(
            "SELECT achievement_id FROM title_achievements "
            f"WHERE platform = ? AND title_id = ? AND achievement_id IN ({placeholders}) "
            "  AND name_ru IS NOT NULL AND name_en IS NOT NULL",
            (platform, title_id, *ids),
        )
        cached = {row["achievement_id"] for row in await cursor.fetchall()}
        return set(ids) - cached

    async def get_cached_description(
        self, platform: str, title_id: str, achievement_id: str
    ) -> CachedDescription | None:
        """The description as `bilingual_descriptions` left it — None until a
        row has been through it, whatever the catalog refresh stored: a pair
        the platform gave twice in one language still needs its translation."""
        cursor = await self._conn.execute(
            "SELECT description_ru, description_en, description_source AS source "
            "FROM title_achievements "
            "WHERE platform = ? AND title_id = ? AND achievement_id = ?"
            "  AND description_source IS NOT NULL",
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
            + _CATALOG_ROW
            + "WHERE d.description_source IS NULL "
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
        the game, not the person, so on Xbox (the one caller) whoever the
        group-by picks is as good as any other; the caller falls back to
        another owner itself if that one's token turns out to be dead. Not
        so on PSN, where one account's answer lists only its own trophies
        unless asked for the whole list (scripts/backfill_descriptions.py
        does, #50).
        """
        placeholders = ", ".join("?" * len(platforms))
        cursor = await self._conn.execute(
            "SELECT s.platform, s.title_id, MIN(al.tg_id) AS tg_id "
            "FROM seen_achievements s "
            + OWNED_BY_PERSON
            + _CATALOG_ROW
            # A `fallback` row counts as unfinished: the text is stored and
            # on screen, but nothing has translated it yet, so the next pass
            # offers it to the translator again. Without a key that pass
            # rewrites the same row, caches nothing new, and the poller drops
            # the title for the rest of the process.
            + "WHERE (d.description_source IS NULL OR d.description_source = 'fallback') "
            f"  AND s.platform IN ({placeholders}) "
            "  AND s.description IS NOT NULL AND TRIM(s.description) <> '' "
            "GROUP BY s.platform, s.title_id "
            "LIMIT ?",
            (*platforms, limit),
        )
        return [(row["platform"], row["title_id"], row["tg_id"]) for row in await cursor.fetchall()]

    async def untranslated_descriptions(
        self, platform: str, title_id: str
    ) -> dict[str, tuple[str | None, str]]:
        """`{achievement_id: (description_ru, description_en)}` for one game's
        earned achievements whose descriptions never went through the
        translator (or are waiting on it, `fallback`) — for a platform whose
        English text is already stored, so no request is needed (#127)."""
        cursor = await self._conn.execute(
            "SELECT s.achievement_id, d.description_ru,"
            "       COALESCE(d.description_en, s.description) AS english "
            "FROM seen_achievements s "
            + OWNED_BY_PERSON
            + _CATALOG_ROW
            + "WHERE s.platform = ? AND s.title_id = ?"
            "  AND (d.description_source IS NULL OR d.description_source = 'fallback')"
            "  AND TRIM(COALESCE(d.description_en, s.description, '')) <> '' "
            "GROUP BY s.achievement_id",
            (platform, title_id),
        )
        return {
            row["achievement_id"]: (row["description_ru"], row["english"])
            for row in await cursor.fetchall()
        }

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
        # Any stored description renders, even one never through the
        # translator: it is what the platform said, and better than nothing.
        cursor = await self._conn.execute(
            "SELECT platform, title_id, achievement_id, description_ru, description_en,"
            "       description_source AS source "
            f"FROM title_achievements WHERE ({clause})"
            "  AND (description_ru IS NOT NULL OR description_en IS NOT NULL)",
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
            "INSERT INTO title_achievements"
            " (platform, title_id, achievement_id, description_ru, description_en,"
            "  description_source, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(platform, title_id, achievement_id) DO UPDATE SET"
            " description_ru = excluded.description_ru,"
            " description_en = excluded.description_en,"
            " description_source = excluded.description_source,"
            " updated_at = excluded.updated_at",
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
