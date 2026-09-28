"""Tests for HowLongToBeat title matcher (services/hltb_match.py, #131).

Pure scoring and heuristics: string normalization, edition/platform tail
stripping, similarity penalties, Steam appid verification, and acceptance
thresholds.
"""

from __future__ import annotations

import pytest

from bot.services.hltb import HltbError, HltbResult
from bot.services.hltb_match import (
    ACCEPT_SCORE,
    CLEAR_MARGIN,
    CORE_DISCOUNT,
    SURE_SCORE,
    WEAK_SCORE,
    GameIdentity,
    _Scored,
    core,
    decide,
    find,
    name_score,
    normalize,
    queries,
    rank,
    score,
    similarity,
    usable_name,
)


def make_result(
    hltb_id: int = 1,
    name: str = "Test Game",
    release_year: int | None = 2020,
    platforms: list[str] | None = None,
    game_type: str | None = None,
    alias: str | None = None,
    popularity: int = 100,
) -> HltbResult:
    return HltbResult(
        hltb_id=hltb_id,
        name=name,
        release_year=release_year,
        main_hours=10.0,
        extra_hours=15.0,
        completionist_hours=25.0,
        platforms=platforms if platforms is not None else ["PC", "Xbox Series X/S"],
        game_url=f"https://howlongtobeat.com/game/{hltb_id}",
        image_url=f"https://howlongtobeat.com/games/{hltb_id}.jpg",
        genre="Action",
        game_type=game_type,
        alias=alias,
        popularity=popularity,
    )


# ------------------------------------------------------------------ normalize


def test_normalize_strips_diacritics_and_trademarks() -> None:
    assert normalize("Pokémon™") == "pokemon"
    assert normalize("HELLDIVERS™ 2") == "helldivers 2"
    assert normalize("Some Game® © ℠") == "some game"


def test_normalize_converts_roman_numerals_to_arabic() -> None:
    assert normalize("Halo II") == "halo 2"
    assert normalize("Final Fantasy VII") == "final fantasy 7"
    assert normalize("Grand Theft Auto V") == "grand theft auto 5"
    assert normalize("Mega Man X") == "mega man 10"


def test_normalize_handles_ampersand_and_apostrophes() -> None:
    assert normalize("Ratchet & Clank") == "ratchet and clank"
    assert normalize("Assassin's Creed") == "assassins creed"
    assert normalize("Gears ’n’ Glory") == "gears n glory"


def test_normalize_drops_leading_article_the() -> None:
    assert normalize("The Witcher 3") == "witcher 3"
    assert normalize("The Last of Us") == "last of us"
    # Single word "The" must not vanish
    assert normalize("The") == "the"


# ----------------------------------------------------------------------- core


def test_core_strips_platform_tails() -> None:
    assert core("Forza Horizon 4 (Windows 10)") == "Forza Horizon 4"
    assert core("Gears 5 (PC)") == "Gears 5"
    assert core("Minecraft - Xbox One Edition") == "Minecraft"
    assert core("Control [PS4]") == "Control"
    assert core("Game - Windows 11") == "Game"


def test_core_strips_edition_and_preview_tails() -> None:
    assert core("Shadow Complex Remastered") == "Shadow Complex"
    assert core("Dead Island Definitive Edition") == "Dead Island"
    assert core("Batman: Arkham City - Game of the Year Edition") == "Batman: Arkham City"
    assert core("Control: Ultimate Edition") == "Control"
    assert core("Deep Rock Galactic (Game Preview)") == "Deep Rock Galactic"
    assert core("Subnautica (Early Access)") == "Subnautica"


def test_core_strips_chained_tails() -> None:
    # Multiple tails cut in sequence
    assert core("Game - Xbox One Edition (Game Preview)") == "Game"


def test_core_preserves_single_word_or_names_without_tail() -> None:
    assert core("Halo Infinite") == "Halo Infinite"
    assert core("The Master Chief Collection") == "The Master Chief Collection"


# ---------------------------------------------------------------- usable_name


def test_usable_name_filters_placeholders_and_non_latin() -> None:
    assert usable_name("Halo Infinite") is True
    assert usable_name("Grand Theft Auto V / ГТА 5") is True
    assert usable_name(None) is False
    assert usable_name("") is False
    assert usable_name("   ") is False
    assert usable_name("?") is False
    assert usable_name("Unknown") is False
    assert usable_name("unknown title") is False
    # Pure Russian name has no Latin letters -> rejected by HLTB matcher
    assert usable_name("Война и мир") is False


# -------------------------------------------------------------------- queries


def test_queries_generates_up_to_three_distinct_spellings() -> None:
    identity = GameIdentity(
        names=("Batman: Arkham City - Game of the Year Edition",),
        platform="xbox_modern",
    )
    qs = queries(identity)
    assert len(qs) <= 3
    # First query should be the core name
    assert qs[0] == "Batman Arkham City"
    # Third query should be subtitle head if long enough
    assert any("Batman" in q for q in qs)


# ----------------------------------------------------------------- similarity


def test_similarity_exact_matches() -> None:
    assert similarity("halo infinite", "halo infinite") == 1.0
    assert similarity("", "halo") == 0.0


def test_similarity_penalizes_differing_numbers() -> None:
    # Halo 2 vs Halo 3: same words, but numbers differ -> heavy penalty (* 0.6)
    score_diff_nums = similarity("halo 2", "halo 3")
    score_same_name = similarity("halo 2", "halo 2")
    assert score_same_name == 1.0
    assert score_diff_nums < 0.6

    # Number vs no number also penalized
    score_numbered = similarity("halo", "halo 2")
    assert score_numbered < 0.6


def test_similarity_keeps_same_numbers_without_penalty() -> None:
    # Final Fantasy 7 vs Final Fantasy 7 Remake
    sim = similarity("final fantasy 7", "final fantasy 7 remake")
    assert sim > 0.7


# ----------------------------------------------------------------- name_score


def test_name_score_uses_core_discount() -> None:
    identity = GameIdentity(
        names=("Shadow Complex Remastered",),
        platform="xbox_modern",
    )
    exact_res = make_result(name="Shadow Complex Remastered")
    core_res = make_result(name="Shadow Complex")

    score_exact = name_score(identity, exact_res)
    score_core = name_score(identity, core_res)

    # Exact name wins over cored name due to CORE_DISCOUNT
    assert score_exact == 1.0
    assert score_core == pytest.approx(1.0 * CORE_DISCOUNT)


# ---------------------------------------------------------------------- score


def test_score_applies_type_factor_to_dlc_and_mods() -> None:
    identity = GameIdentity(names=("Some Game Expansion",), platform="xbox_modern")
    base_res = make_result(name="Some Game", game_type=None)
    dlc_res = make_result(name="Some Game", game_type="dlc")

    s_base = score(identity, base_res)
    s_dlc = score(identity, dlc_res)
    assert s_dlc < s_base


def test_score_penalizes_off_platform() -> None:
    identity = GameIdentity(
        names=("Exclusive Game",),
        platform="psn",
        platforms=("PS5",),
    )
    pc_only = make_result(name="Exclusive Game", platforms=["PC"])
    ps_res = make_result(name="Exclusive Game", platforms=["PlayStation 5"])

    assert score(identity, ps_res) > score(identity, pc_only)


def test_score_penalizes_entries_released_after_played_year() -> None:
    identity = GameIdentity(
        names=("Prey",),
        platform="xbox_modern",
        first_played_year=2008,
    )
    old_game = make_result(hltb_id=1, name="Prey", release_year=2006)
    new_remake = make_result(hltb_id=2, name="Prey", release_year=2017)

    assert score(identity, old_game) > score(identity, new_remake)


# ------------------------------------------------------------- rank & decide


def test_decide_accepts_strong_match_above_threshold() -> None:
    r1 = make_result(hltb_id=1, name="Game A")
    r2 = make_result(hltb_id=2, name="Game B")
    ranked = [_Scored(r1, 0.92), _Scored(r2, 0.50)]
    winner = decide(ranked)
    assert winner is not None
    assert winner.result.hltb_id == 1


def test_decide_accepts_weak_match_only_with_clear_margin() -> None:
    r1 = make_result(hltb_id=1, name="Game A")
    r2 = make_result(hltb_id=2, name="Game B")

    # Score in weak range (0.74..0.86), margin >= CLEAR_MARGIN (0.12) -> accepted
    clear_winner = decide([_Scored(r1, 0.80), _Scored(r2, 0.65)])
    assert clear_winner is not None
    assert clear_winner.result.hltb_id == 1

    # Score in weak range, margin too small (0.05 < 0.12) -> rejected (None)
    ambiguous = decide([_Scored(r1, 0.80), _Scored(r2, 0.75)])
    assert ambiguous is None


def test_decide_rejects_scores_below_weak_threshold() -> None:
    r1 = make_result(hltb_id=1, name="Vaguely Similar")
    assert decide([_Scored(r1, 0.70)]) is None
    assert decide([]) is None


# ----------------------------------------------------------------------- find


@pytest.mark.asyncio
async def test_find_settles_steam_game_by_matching_appid() -> None:
    identity = GameIdentity(
        names=("Portal 2",),
        platform="steam",
        steam_appid=620,
    )
    r1 = make_result(hltb_id=101, name="Portal 2")
    r2 = make_result(hltb_id=102, name="Portal 2 - Sixense Edition")

    async def mock_search(q: str) -> list[HltbResult]:
        return [r1, r2]

    async def mock_steam_ids(res: HltbResult) -> set[int] | None:
        if res.hltb_id == 101:
            return {620}
        return {99999}

    match = await find(identity, mock_search, steam_ids=mock_steam_ids)
    assert match is not None
    assert match.hltb_id == 101
    assert match.score == 1.0


@pytest.mark.asyncio
async def test_find_rules_out_steam_candidate_with_different_appid() -> None:
    identity = GameIdentity(
        names=("Some Game",),
        platform="steam",
        steam_appid=500,
    )
    wrong_steam = make_result(hltb_id=10, name="Some Game")

    async def mock_search(q: str) -> list[HltbResult]:
        return [wrong_steam]

    async def mock_steam_ids(res: HltbResult) -> set[int] | None:
        return {99999}  # lists another game's appid

    match = await find(identity, mock_search, steam_ids=mock_steam_ids)
    assert match is None


@pytest.mark.asyncio
async def test_find_raises_hltb_error_if_all_searches_fail() -> None:
    identity = GameIdentity(
        names=("Gears 5",),
        platform="xbox_modern",
    )

    async def failing_search(q: str) -> list[HltbResult]:
        raise HltbError("network down")

    with pytest.raises(HltbError, match="HLTB could not be searched"):
        await find(identity, failing_search)
