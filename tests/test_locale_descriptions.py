"""An achievement's description renders in the chat's language (#48).

The bilingual cache has been filled by all three platform clients since
2026-09-09, but nothing read it: the published message used
`seen_achievements.description`, the single-language snapshot taken when
that one person unlocked the achievement. These tests cover the switch to
reading the cache, and the two cases where the snapshot is still the right
answer.
"""

from __future__ import annotations

from datetime import timedelta

from bot.db.repo import AchievementRow, Repo
from bot.services.descriptions_view import localize_descriptions
from bot.util import utcnow

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


async def test_a_half_filled_cache_entry_falls_back_to_the_other_language(repo: Repo) -> None:
    """The translation genuinely never arrived (no Anthropic key, say), so
    the cache holds one language only. Showing that one untranslated is what
    the owner asked for (2026-09-13) — the platform itself would have shown
    the reader the same text."""
    await _cache(repo, "a1", "Сжечь всех врагов", None)
    [row] = await localize_descriptions(repo, [_row()], "en")
    assert row.description == "Сжечь всех врагов"


async def test_a_blank_cached_translation_is_treated_as_missing(repo: Repo) -> None:
    """Blank on one side, nothing on the other: there is nothing to show from
    the cache at all, so the row's own snapshot stands."""
    await _cache(repo, "a1", None, "   ")
    [row] = await localize_descriptions(repo, [_row()], "en")
    assert row.description == "снимок"


async def test_a_blank_side_falls_back_to_the_filled_one(repo: Repo) -> None:
    await _cache(repo, "a1", "Сжечь всех врагов", "   ")
    [row] = await localize_descriptions(repo, [_row()], "en")
    assert row.description == "Сжечь всех врагов"


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


# ------------------------------------------- the achievement's own name (#61)


async def test_the_name_follows_the_chats_language(repo: Repo) -> None:
    """Xbox and PSN store English names (their main call is en-US), Steam
    stores Russian ones (its main call is l=russian) — so before this a
    Russian chat showed Steam in Russian and the rest in English, whatever the
    chat had chosen."""
    await repo.cache_names(PLATFORM, TITLE_ID, {"a1": ("Сжечь всех врагов", "Burn every enemy")})

    [ru] = await localize_descriptions(repo, [_row()], "ru")
    [en] = await localize_descriptions(repo, [_row()], "en")

    assert ru.name == "Сжечь всех врагов"
    assert en.name == "Burn every enemy"


async def test_a_name_missing_in_one_language_falls_back_to_the_other(repo: Repo) -> None:
    """Never a blank line, and never a translated name: where the platform
    has only one, that one is shown."""
    await repo.cache_names(PLATFORM, TITLE_ID, {"a1": (None, "Burn every enemy")})

    [ru] = await localize_descriptions(repo, [_row()], "ru")

    assert ru.name == "Burn every enemy"


async def test_an_uncached_name_keeps_whatever_was_stored(repo: Repo) -> None:
    [row] = await localize_descriptions(repo, [_row()], "ru")

    assert row.name == _row().name


async def test_a_psn_game_title_follows_the_chats_language(repo: Repo) -> None:
    """The owner's own counterexample: presence showed "Marvel's Росомаха"
    while the trophies arrived from "Marvel's Wolverine". Verified live —
    Sony answers the same once-per-game call with "Marvel's Wolverine" in
    English and "Marvel: Росомаха" in Russian (#61). Xbox and Steam return
    one title for both locales, which is why only this one is localized."""
    await repo.upsert_title("NPWR57054_00", "Marvel's Wolverine", "psn")
    await repo.set_title_names("NPWR57054_00", "Marvel: Росомаха", "Marvel's Wolverine")
    row = _row()
    row.title_id = "NPWR57054_00"
    row.platform = "psn"

    [ru] = await localize_descriptions(repo, [row], "ru")
    [en] = await localize_descriptions(repo, [row], "en")

    assert ru.title_name == "Marvel: Росомаха"
    assert en.title_name == "Marvel's Wolverine"


async def test_a_title_with_no_localized_name_is_left_alone(repo: Repo) -> None:
    await repo.upsert_title(TITLE_ID, "Left 4 Dead 2", PLATFORM)

    [row] = await localize_descriptions(repo, [_row()], "ru")

    assert row.title_name is None  # whatever the caller had; nothing invented


# ------------------------------------------------ the lists beside them (#61)


async def test_recent_and_the_game_lists_follow_the_chats_language(repo: Repo) -> None:
    """A notification was localized while the list right under it was not:
    /recent, /stats' games and the month's top games all render straight from
    SQL, so they showed whatever language the platform had answered in."""
    await repo.ensure_user(1, "igor")
    await repo.link_xbox_account(1, "xuid-1", "Someone", 0)
    await repo.upsert_chat(-100500, "Chat", 1)
    await repo.subscribe(-100500, 1)
    await repo.upsert_title("t-halo", "Halo: The Master Chief Collection", "xbox_modern")
    await repo.set_title_names(
        "t-halo", "Halo: Коллекция Мастер Чифа", "Halo: The Master Chief Collection"
    )
    await repo.cache_names(
        "xbox_modern", "t-halo", {"a1": ("Да мы только начали", "Just Getting Started")}
    )
    await repo.insert_new_achievements(
        "xuid-1",
        [
            AchievementRow(
                title_id="t-halo",
                achievement_id="a1",
                name="Just Getting Started",
                description=None,
                icon_url=None,
                unlocked_at=utcnow().isoformat(timespec="seconds"),
                gamerscore=10,
                rarity_percent=None,
                platform="xbox_modern",
                title_name="Halo: The Master Chief Collection",
            )
        ],
        is_backfill=False,
    )

    [ru] = await repo.chat_recent(-100500, 5, locale="ru")
    [en] = await repo.chat_recent(-100500, 5, locale="en")
    assert (ru.name, ru.game) == ("Да мы только начали", "Halo: Коллекция Мастер Чифа")
    assert (en.name, en.game) == ("Just Getting Started", "Halo: The Master Chief Collection")

    since = utcnow() - timedelta(days=30)
    [game_ru] = await repo.recent_games("xuid-1", since, locale="ru")
    assert game_ru.name == "Halo: Коллекция Мастер Чифа"

    [top_ru] = await repo.chat_top_games(-100500, since, locale="ru")
    assert top_ru.name == "Halo: Коллекция Мастер Чифа"
