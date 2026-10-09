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
    assert "years far apart" in verdict.reasons


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
