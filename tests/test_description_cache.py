"""db/repo/_descriptions.py — the shared bilingual achievement-description
cache (2026-09-09 user request). Shared across every person who unlocks the
same achievement, not per-seen_achievements-row — see schema.sql's own
comment on achievement_description_cache."""

from __future__ import annotations

from bot.db.repo import Repo

PLATFORM = "steam"
TITLE_ID = "570"
ACHIEVEMENT_ID = "WIN_GAME"


async def test_uncached_lookup_returns_none(repo: Repo) -> None:
    assert await repo.get_cached_description(PLATFORM, TITLE_ID, ACHIEVEMENT_ID) is None


async def test_cache_then_get_round_trips(repo: Repo) -> None:
    await repo.cache_description(
        PLATFORM,
        TITLE_ID,
        ACHIEVEMENT_ID,
        description_ru="Победи в игре",
        description_en="Win the game",
        source="native",
    )

    cached = await repo.get_cached_description(PLATFORM, TITLE_ID, ACHIEVEMENT_ID)

    assert cached is not None
    assert cached.description_ru == "Победи в игре"
    assert cached.description_en == "Win the game"
    assert cached.source == "native"


async def test_caching_again_overwrites_the_previous_entry(repo: Repo) -> None:
    """A re-cache (e.g. a later resync finds a better native translation)
    replaces the old row rather than erroring on the primary key."""
    await repo.cache_description(
        PLATFORM,
        TITLE_ID,
        ACHIEVEMENT_ID,
        description_ru="Win the game",
        description_en="Win the game",
        source="llm",
    )

    await repo.cache_description(
        PLATFORM,
        TITLE_ID,
        ACHIEVEMENT_ID,
        description_ru="Победи в игре",
        description_en="Win the game",
        source="native",
    )

    cached = await repo.get_cached_description(PLATFORM, TITLE_ID, ACHIEVEMENT_ID)
    assert cached is not None
    assert cached.description_ru == "Победи в игре"
    assert cached.source == "native"


async def test_cache_is_scoped_per_platform_and_title(repo: Repo) -> None:
    """The same achievement_id string on a different platform or game is a
    different cache entry — the primary key is the full triple."""
    await repo.cache_description(
        "steam", "570", "A1", description_ru="ru-1", description_en="en-1", source="native"
    )
    await repo.cache_description(
        "psn", "570", "A1", description_ru="ru-2", description_en="en-2", source="native"
    )
    await repo.cache_description(
        "steam", "730", "A1", description_ru="ru-3", description_en="en-3", source="native"
    )

    assert (await repo.get_cached_description("steam", "570", "A1")).description_ru == "ru-1"
    assert (await repo.get_cached_description("psn", "570", "A1")).description_ru == "ru-2"
    assert (await repo.get_cached_description("steam", "730", "A1")).description_ru == "ru-3"
