"""Which versions are one game (#147, stage 3): the matcher's decisions on the
cases the owner named, and the linker keeping a manual decision."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.services.game_link import GameLinker
from bot.services.game_match import Candidate, compare, kind_of
from bot.services.stores import StoreVersion

WITCHER_ACHIEVEMENTS = frozenset(f"achievement {i}" for i in range(50))


def _c(version_id: int, name: str, **kw: object) -> Candidate:
    return Candidate(
        version_id=version_id,
        store=str(kw.pop("store", "xbox")),
        product_id=str(kw.pop("product_id", version_id)),
        console=str(kw.pop("console", "one")),
        names=(name,),
        **kw,  # type: ignore[arg-type]
    )


def test_the_same_game_on_two_platforms_is_linked() -> None:
    xbox = _c(
        1,
        "The Witcher 3: Wild Hunt",
        year=2015,
        developer="CD PROJEKT RED",
        achievements=WITCHER_ACHIEVEMENTS,
    )
    steam = _c(
        2,
        "The Witcher 3: Wild Hunt - Complete Edition",
        store="steam",
        console="steam",
        year=2015,
        developer="CD PROJEKT RED",
        achievements=WITCHER_ACHIEVEMENTS,
    )
    verdict = compare(xbox, steam)
    assert verdict.state == "linked", verdict.reasons
    assert kind_of(steam) == "edition"


def test_a_sequel_is_never_the_same_game() -> None:
    assert (
        compare(
            _c(1, "STAR WARS Battlefront", year=2015), _c(2, "STAR WARS Battlefront II", year=2017)
        ).state
        == "apart"
    )
    assert compare(_c(1, "Halo 3", year=2007), _c(2, "Halo 4", year=2012)).state == "apart"


def test_the_same_name_years_apart_goes_to_review() -> None:
    old = _c(
        1, "Star Wars: Battlefront 2 (Classic, 2005)", store="steam", console="steam", year=2005
    )
    new = _c(2, "STAR WARS Battlefront II", year=2017)
    verdict = compare(old, new)
    assert verdict.state == "review"
    assert any(r.startswith("years_far") for r in verdict.reasons)


def test_the_stores_own_group_links_editions() -> None:
    a = _c(1, "Forza Horizon 3", store_group="g1")
    b = _c(2, "Forza Horizon 3 Ultimate Edition", store_group="g1")
    assert compare(a, b).state == "linked"
    # …but never across a number.
    c = _c(3, "Forza Horizon 4", store_group="g1")
    assert compare(a, c).state == "apart"


def test_a_demo_and_a_remaster_are_told_by_their_names() -> None:
    assert kind_of(_c(1, "RESIDENT EVIL 2 1-Shot Demo")) == "demo"
    assert kind_of(_c(2, "Call of Duty: Modern Warfare Remastered")) == "remaster"
    assert kind_of(_c(3, "Resident Evil 2")) == "version"


async def _version(repo: Repo, product: str, name: str, year: str, **kw: object) -> int:
    version = StoreVersion(
        store=str(kw.pop("store", "xbox")),
        product_id=product,
        console=str(kw.pop("console", "one")),
        name=name,
        kind="game",
        developer="CD PROJEKT RED",
        release_date=f"{year}-05-19",
    )
    return await repo.save_version(version, platform=None, title_id=None)


async def test_versions_become_one_game_and_a_manual_rejection_stays(repo: Repo) -> None:
    xbox = await _version(repo, "BR765873CQJD", "The Witcher 3: Wild Hunt", "2015")
    steam = await _version(
        repo, "292030", "The Witcher 3: Wild Hunt", "2015", store="steam", console="steam"
    )
    linker = GameLinker(repo)

    report = await linker.link_versions([xbox, steam])
    [(game, members)] = report.games.items()
    assert sorted(members) == sorted([xbox, steam])

    # The operator says the Steam one is not this game: a re-run keeps it out.
    await repo.set_link(steam, game, kind="version", state="rejected", source="manual")
    await linker.link_versions([xbox, steam])
    assert await repo.linked_game_of(xbox) == game
    assert await repo.linked_game_of(steam) not in (None, game)


async def test_a_manual_link_is_never_moved(repo: Repo) -> None:
    a = await _version(repo, "A", "Gears of War", "2006")
    b = await _version(repo, "B", "Gears of War: Ultimate Edition", "2015")
    linker = GameLinker(repo)
    report = await linker.link_versions([a, b])
    # Nine years apart: the operator decides.
    assert report.review
    version_id, game_id, _why = report.review[0]
    await repo.set_link(version_id, game_id, kind="remaster", state="linked", source="manual")
    await repo.drop_auto_links(version_id, game_id, "linked")
    await linker.link_versions([a, b])
    assert await repo.linked_game_of(version_id) == game_id


def test_a_demo_is_its_own_games_not_a_namesakes() -> None:
    re2 = _c(1, "RESIDENT EVIL 2", year=2019)
    assert compare(re2, _c(2, "RESIDENT EVIL 2 1-Shot Demo", year=2019)).state == "linked"
    # "Resident Evil" opens "Resident Evil 4 Chainsaw Demo", but 4 is another game.
    re1 = _c(3, "Resident Evil", year=2015)
    assert compare(re1, _c(4, "Resident Evil 4 Chainsaw Demo", year=2023)).state != "linked"
    # Years apart: not this game's beta.
    gears = _c(5, "Gears of War", year=2006)
    assert (
        compare(gears, _c(6, "Gears of War: E-Day Multiplayer Beta", year=2026)).state != "linked"
    )


def test_one_achievement_list_is_one_game() -> None:
    """Smart Delivery and Play Anywhere share one list (owner, 2026-10-09)."""
    one = _c(1, "Forza Horizon 4", console="one", list_key=("xbox_modern", "1"))
    pc = _c(2, "Forza Horizon 4 for Windows 10", console="pc", list_key=("xbox_modern", "1"))
    assert compare(one, pc).state == "linked"


def test_a_subtitle_after_the_name_is_another_game() -> None:
    gears = _c(1, "Gears of War", console="360")
    assert compare(gears, _c(2, "Gears of War: Judgment", console="360")).state == "apart"
    # A franchise said before the name is the same game.
    mw2 = _c(3, "Modern Warfare 2", console="360", year=2009)
    full = _c(4, "Call of Duty: Modern Warfare 2", store="steam", console="steam", year=2009)
    assert compare(mw2, full).state != "apart"


def test_an_edition_with_a_list_of_its_own_is_a_remaster() -> None:
    from bot.services.game_link import _kinds

    shared = frozenset(f"a{i}" for i in range(20))
    base = _c(1, "Gears of War", year=2006, achievements=shared, list_key=("xbox_360", "1"))
    ue = _c(
        2,
        "Gears of War: Ultimate Edition",
        year=2015,
        achievements=frozenset(list(shared)[:8]) | frozenset(f"b{i}" for i in range(12)),
        list_key=("xbox_modern", "2"),
    )
    assert _kinds([base, ue])[2] == "remaster"


async def test_a_demo_is_linked_to_the_version_on_its_console(repo: Repo) -> None:
    game_one = await _version(repo, "RE2", "RESIDENT EVIL 2", "2019", console="one")
    game_series = await _version(repo, "RE2", "RESIDENT EVIL 2", "2019", console="series")
    demo = await _version(repo, "DEMO", "RESIDENT EVIL 2 1-Shot Demo", "2019", console="series")
    await GameLinker(repo).link_versions([game_one, game_series, demo])
    cursor = await repo._conn.execute(
        "SELECT of_version_id FROM version_links WHERE version_id = ? AND kind = 'demo_of'", (demo,)
    )
    assert (await cursor.fetchone())["of_version_id"] == game_series


def test_a_remasters_release_word_keeps_others_demos_off() -> None:
    reloaded = _c(1, "Gears of War: Reloaded", store="steam", console="steam", year=2025)
    beta = _c(2, "Gears of War: E-Day Multiplayer Beta", console="series", year=2026)
    assert compare(reloaded, beta).state != "linked"
    eday = _c(3, "Gears of War: E-Day", store="steam", console="steam", year=2026)
    assert compare(eday, beta).state == "linked"


def test_a_subtitled_name_is_the_same_game_only_by_its_achievements() -> None:
    shared = frozenset(f"a{i}" for i in range(20))
    gears = _c(1, "Gears of War", console="360", achievements=shared)
    reloaded = _c(2, "Gears of War: Reloaded", console="series", year=2025, achievements=shared)
    assert compare(gears, reloaded).state == "linked"
    judgment = _c(
        3,
        "Gears of War: Judgment",
        console="360",
        achievements=frozenset(f"j{i}" for i in range(20)),
    )
    assert compare(gears, judgment).state == "apart"
