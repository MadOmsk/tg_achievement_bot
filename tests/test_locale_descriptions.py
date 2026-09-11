"""An achievement's description renders in the chat's language (#48).

The bilingual cache has been filled by all three platform clients since
2026-09-09, but nothing read it: the published message used
`seen_achievements.description`, the single-language snapshot taken when
that one person unlocked the achievement. These tests cover the switch to
reading the cache, and the two cases where the snapshot is still the right
answer.
"""

from __future__ import annotations

from bot.db.repo import AchievementRow, Repo
from bot.services.descriptions_view import localize_descriptions

PLATFORM = "xbox_modern"
TITLE_ID = "t1"


def _row(achievement_id: str = "a1", description: str | None = "снимок") -> AchievementRow:
    return AchievementRow(
        title_id=TITLE_ID,
        achievement_id=achievement_id,
        name="Ashes to Ashes",
        description=description,
        icon_url=None,
        unlocked_at="2026-09-02T10:00:00+00:00",
        gamerscore=10,
        rarity_percent=None,
        platform=PLATFORM,
    )


async def _cache(repo: Repo, achievement_id: str, ru: str | None, en: str | None) -> None:
    await repo.cache_description(
        PLATFORM, TITLE_ID, achievement_id, description_ru=ru, description_en=en, source="native"
    )


async def test_english_description_comes_from_the_cache(repo: Repo) -> None:
    await _cache(repo, "a1", "Сжечь всех врагов", "Burn every enemy")
    [row] = await localize_descriptions(repo, [_row()], "en")
    assert row.description == "Burn every enemy"


async def test_russian_description_comes_from_the_cache_too(repo: Repo) -> None:
    # Not only the non-default locale: a row whose platform only ever
    # returned English has a stored snapshot that is not Russian either.
    await _cache(repo, "a1", "Сжечь всех врагов", "Burn every enemy")
    [row] = await localize_descriptions(repo, [_row(description="Burn every enemy")], "ru")
    assert row.description == "Сжечь всех врагов"


async def test_an_uncached_achievement_keeps_its_stored_snapshot(repo: Repo) -> None:
    # Unlocked before the cache existed — the snapshot is all there is.
    [row] = await localize_descriptions(repo, [_row()], "en")
    assert row.description == "снимок"


async def test_a_half_filled_cache_entry_keeps_the_snapshot(repo: Repo) -> None:
    # The translation genuinely never arrived (no Anthropic key, say);
    # falling through to the snapshot beats rendering an empty description.
    await _cache(repo, "a1", "Сжечь всех врагов", None)
    [row] = await localize_descriptions(repo, [_row()], "en")
    assert row.description == "снимок"


async def test_a_blank_cached_translation_is_treated_as_missing(repo: Repo) -> None:
    await _cache(repo, "a1", "Сжечь всех врагов", "   ")
    [row] = await localize_descriptions(repo, [_row()], "en")
    assert row.description == "снимок"


async def test_the_original_rows_are_never_mutated(repo: Repo) -> None:
    """The publisher renders the same list once per chat, and two chats can
    be in two languages — localizing for one must not alter the other's."""
    await _cache(repo, "a1", "Сжечь всех врагов", "Burn every enemy")
    rows = [_row()]

    english = await localize_descriptions(repo, rows, "en")
    russian = await localize_descriptions(repo, rows, "ru")

    assert english[0].description == "Burn every enemy"
    assert russian[0].description == "Сжечь всех врагов"
    assert rows[0].description == "снимок"  # untouched


async def test_a_mixed_batch_is_resolved_in_one_query(repo: Repo) -> None:
    """The anti-flood digest can carry several games across platforms, which
    is why the lookup is keyed by the full triple rather than one title."""
    await _cache(repo, "a1", "Первое", "First")
    await _cache(repo, "a2", "Второе", "Second")
    rows = [_row("a1"), _row("a2"), _row("a3")]

    localized = await localize_descriptions(repo, rows, "en")

    assert [row.description for row in localized] == ["First", "Second", "снимок"]


async def test_cached_descriptions_returns_nothing_for_no_keys(repo: Repo) -> None:
    assert await repo.cached_descriptions([]) == {}


# ------------------------------------------------- the one-time backfill gap


async def test_uncached_descriptions_lists_only_what_is_missing(repo: Repo) -> None:
    """scripts/backfill_descriptions.py's whole input (#48)."""
    await repo.ensure_user(1)
    await repo.link_xbox_account(1, "xuid-1", "Mad Omsk", None)
    await repo.insert_new_achievements(
        "xuid-1",
        [_row("a1", "есть описание"), _row("a2", "тоже есть")],
        is_backfill=True,
    )
    await _cache(repo, "a1", "Первое", "First")

    gap = await repo.uncached_descriptions()

    assert [(p, t, a) for p, t, a, _tg, _x in gap] == [(PLATFORM, TITLE_ID, "a2")]


async def test_uncached_descriptions_ignores_rows_with_no_description(repo: Repo) -> None:
    # Nothing to translate, so not a gap — this is what keeps the backfill's
    # own count honest against `seen_achievements`' raw row count.
    await repo.ensure_user(1)
    await repo.link_xbox_account(1, "xuid-1", "Mad Omsk", None)
    await repo.insert_new_achievements(
        "xuid-1", [_row("a1", None), _row("a2", "")], is_backfill=True
    )

    assert await repo.uncached_descriptions() == []


async def test_uncached_descriptions_carries_the_owner(repo: Repo) -> None:
    """Xbox needs a token-bearing owner to ask on behalf of; the row has to
    say who that can be."""
    await repo.ensure_user(42)
    await repo.link_xbox_account(42, "xuid-42", "Mad Omsk", None)
    await repo.insert_new_achievements("xuid-42", [_row("a1", "описание")], is_backfill=True)

    [(_platform, _title, _achievement, tg_id, external_id)] = await repo.uncached_descriptions()

    assert (tg_id, external_id) == (42, "xuid-42")
