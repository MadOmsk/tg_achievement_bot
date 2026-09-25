"""The catalog is the one store of an achievement's names, descriptions and
rarity (#119)."""

from __future__ import annotations

from pathlib import Path

import aiosqlite

from bot.db.repo import Repo, TitleAchievementRow

MIGRATION_062 = Path("bot/db/migrations/062_catalog_absorbs_caches.sql").read_text(encoding="utf-8")


def _listed(achievement_id: str, **fields) -> TitleAchievementRow:
    return TitleAchievementRow(
        platform="xbox_modern",
        title_id="g",
        achievement_id=achievement_id,
        name_ru=fields.get("name_ru", "Имя"),
        name_en=fields.get("name_en", "Name"),
        description_ru=fields.get("description_ru"),
        description_en=fields.get("description_en"),
        icon_url=None,
        is_secret=False,
        rarity_percent=None,
        updated_at="2026-09-25T00:00:00+00:00",
    )


async def test_facts_a_poll_learned_are_not_the_games_list(repo: Repo) -> None:
    """A percentage or a name for every achievement a poll saw must not pass
    for the whole game: a game "complete" with its unlocks alone would never
    be asked for the rest, and would count as 100% done."""
    await repo.cache_rarity("xbox_modern", "g", {"1": 5.0, "2": 50.0})
    await repo.cache_names("xbox_modern", "g", {"1": ("Имя", "Name")})

    assert await repo.title_achievements_count("xbox_modern", "g") == 0
    assert await repo.get_title_achievements("xbox_modern", "g") == []

    await repo.upsert_title_achievements([_listed("1"), _listed("2"), _listed("3")])

    assert await repo.title_achievements_count("xbox_modern", "g") == 3
    rows = {r.achievement_id: r for r in await repo.get_title_achievements("xbox_modern", "g")}
    assert rows["1"].rarity_percent == 5.0  # the poll's fact survives the refresh


async def test_a_refresh_never_overwrites_a_translation(repo: Repo) -> None:
    await repo.cache_description(
        "xbox_modern",
        "g",
        "1",
        description_ru="Победи",
        description_en="Win",
        source="llm",
    )
    # The platform gave the same English twice; the refresh passes it by.
    await repo.upsert_title_achievements([_listed("1", description_ru="Win", description_en="Win")])

    cached = await repo.get_cached_description("xbox_modern", "g", "1")
    assert cached is not None
    assert (cached.description_ru, cached.description_en, cached.source) == (
        "Победи",
        "Win",
        "llm",
    )


async def test_a_description_the_refresh_stored_still_goes_to_the_translator(
    repo: Repo,
) -> None:
    """Stored by the catalog refresh, never through bilingual_descriptions:
    rendered as it is, but not yet "cached" — its Russian may be the English
    given twice."""
    await repo.upsert_title_achievements([_listed("1", description_ru="Win", description_en="Win")])

    assert await repo.get_cached_description("xbox_modern", "g", "1") is None
    rendered = await repo.cached_descriptions([("xbox_modern", "g", "1")])
    assert rendered[("xbox_modern", "g", "1")].description_en == "Win"


async def test_migration_062_moves_the_caches_into_the_catalog(tmp_path) -> None:
    async with aiosqlite.connect(tmp_path / "m062.db") as conn:
        await conn.executescript(
            """
            CREATE TABLE title_achievements (
                platform TEXT NOT NULL, title_id TEXT NOT NULL, achievement_id TEXT NOT NULL,
                name_ru TEXT, name_en TEXT, description_ru TEXT, description_en TEXT,
                icon_url TEXT, is_secret INTEGER NOT NULL DEFAULT 0, gamerscore INTEGER,
                trophy_type TEXT, trophy_group_id TEXT, rarity_percent REAL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (platform, title_id, achievement_id));
            CREATE TABLE achievement_description_cache (
                platform TEXT, title_id TEXT, achievement_id TEXT, description_ru TEXT,
                description_en TEXT, source TEXT, cached_at TEXT);
            CREATE TABLE achievement_name_cache (
                platform TEXT, title_id TEXT, achievement_id TEXT, name_ru TEXT,
                name_en TEXT, cached_at TEXT);
            CREATE TABLE achievement_rarity_cache (
                platform TEXT, title_id TEXT, achievement_id TEXT, rarity_percent REAL,
                checked_at TEXT);
            CREATE INDEX idx_rarity_cache_title
                ON achievement_rarity_cache(platform, title_id, checked_at);

            -- in the catalog already, with an untranslated Russian
            INSERT INTO title_achievements VALUES
                ('psn', 'P', '1', 'Trophy', 'Trophy', 'Win', 'Win', 'icon', 0, NULL,
                 'gold', 'default', 9.5, 't0');
            INSERT INTO achievement_description_cache VALUES
                ('psn', 'P', '1', 'Победи', 'Win', 'llm', 't1'),
                ('psn', 'P', '2', NULL, 'Lose', 'fallback', 't1');
            INSERT INTO achievement_name_cache VALUES
                ('psn', 'P', '1', 'Трофей', NULL, 't1'),
                ('xbox_modern', 'X', 'a', 'Имя', 'Name', 't1');
            INSERT INTO achievement_rarity_cache VALUES
                ('psn', 'P', '1', 7.0, 't1'),
                ('xbox_modern', 'X', 'b', 3.0, 't1');
            """
        )
        await conn.executescript(MIGRATION_062)
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT platform, title_id, achievement_id, name_ru, name_en, description_ru,"
            " description_en, description_source, rarity_percent, listed FROM title_achievements"
        )
        rows = {(r[0], r[1], r[2]): dict(r) for r in await cursor.fetchall()}
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'achievement_%'"
        )
        leftover = [r[0] for r in await cursor.fetchall()]

    assert leftover == []
    one = rows[("psn", "P", "1")]
    assert (one["name_ru"], one["name_en"]) == ("Трофей", "Trophy")
    assert (one["description_ru"], one["description_source"]) == ("Победи", "llm")
    assert one["rarity_percent"] == 7.0
    assert one["listed"] == 1
    two = rows[("psn", "P", "2")]
    assert (two["description_ru"], two["description_en"], two["description_source"]) == (
        None,
        "Lose",
        "fallback",
    )
    assert two["listed"] == 0  # a fact, not a known entry of the game's list
    assert rows[("xbox_modern", "X", "a")]["name_en"] == "Name"
    assert rows[("xbox_modern", "X", "b")]["rarity_percent"] == 3.0
