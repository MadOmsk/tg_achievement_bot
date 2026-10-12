"""How versions relate (#147; owner, 2026-10-10/11): the model's answers on
the cases the owner named and the false friends the review listed, and the
linker building games from labels and the model."""

from __future__ import annotations

import pytest

from bot.db.repo import Repo
from bot.services.game_link import GameLinker
from bot.services.game_match import Candidate, compare, features, kind_of
from bot.services.stores import StoreVersion

WITCHER = frozenset(f"witcher {i}" for i in range(50))


def _c(version_id: int, name: str, **kw: object) -> Candidate:
    return Candidate(
        version_id=version_id,
        store=str(kw.pop("store", "xbox")),
        product_id=str(kw.pop("product_id", version_id)),
        console=str(kw.pop("console", "one")),
        names=(name,),
        **kw,  # type: ignore[arg-type]
    )


def _list(prefix: str, n: int) -> frozenset[str]:
    return frozenset(f"{prefix} {i}" for i in range(n))


def _linked(a: Candidate, b: Candidate, relation: str) -> bool:
    v = compare(a, b)
    return v.state == "linked" and v.relation == relation


# ------------------------------------------------------------------ one game


def test_the_same_game_on_two_stores_is_one_game() -> None:
    xbox = _c(
        1, "The Witcher 3: Wild Hunt", year=2015, developer="CD PROJEKT RED", achievements=WITCHER
    )
    steam = _c(
        2,
        "The Witcher 3: Wild Hunt - Complete Edition",
        store="steam",
        console="steam",
        year=2015,
        developer="CD PROJEKT RED",
        achievements=WITCHER,
    )
    assert _linked(xbox, steam, "same"), compare(xbox, steam).reasons
    assert kind_of(steam) == "edition"


def test_one_achievement_list_is_one_game() -> None:
    """Smart Delivery and Play Anywhere share one list (owner, 2026-10-09)."""
    one = _c(1, "Forza Horizon 4", console="one", list_key=("xbox_modern", "1"))
    pc = _c(2, "Forza Horizon 4 for Windows 10", console="pc", list_key=("xbox_modern", "1"))
    assert _linked(one, pc, "same")


def test_ps4_and_ps5_released_together_are_one_game() -> None:
    """Owner, 2026-10-11: even with two trophy lists."""
    ps4 = _c(
        1,
        "Marvel's Spider-Man: Miles Morales",
        store="psn",
        console="ps4",
        year=2020,
        list_key=("psn", "A"),
        achievements=_list("mm", 40),
    )
    ps5 = _c(
        2,
        "Marvel's Spider-Man: Miles Morales",
        store="psn",
        console="ps5",
        year=2020,
        list_key=("psn", "B"),
        achievements=_list("mm", 40),
    )
    assert _linked(ps4, ps5, "same"), compare(ps4, ps5).reasons


def test_the_stores_own_group_holds_an_edition_but_not_a_sequel() -> None:
    a = _c(1, "Forza Horizon 3", store_group="g1", year=2016)
    b = _c(2, "Forza Horizon 3 Ultimate Edition", store_group="g1", year=2016)
    assert _linked(a, b, "same")
    c = _c(3, "Forza Horizon 4", store_group="g1", year=2018)
    assert compare(a, c).relation == "other"


def test_a_cross_gen_set_is_a_strong_sign_of_one_game() -> None:
    a = _c(1, "Game", console="one", year=2020, cross_gen_set="SET")
    b = _c(2, "Game: Next", console="series", year=2020, cross_gen_set="SET")
    assert "cross_gen_set" in compare(a, b).features


def test_a_demo_and_a_tool_join_their_game() -> None:
    re2 = _c(1, "RESIDENT EVIL 2", year=2019)
    assert _linked(re2, _c(2, "RESIDENT EVIL 2 1-Shot Demo", year=2019), "same")
    fallout = _c(
        3, "Fallout 4", store="steam", console="steam", year=2015, developer="Bethesda Game Studios"
    )
    kit = _c(
        4,
        "Fallout 4: Creation Kit",
        store="steam",
        console="steam",
        year=2022,
        developer="Bethesda Game Studios",
    )
    assert kind_of(kit) == "tool"
    assert _linked(fallout, kit, "same")
    assert "tool_of" in compare(fallout, kit).features


def test_a_demo_is_its_own_games_not_a_namesakes() -> None:
    re1 = _c(3, "Resident Evil", year=2015)
    assert compare(re1, _c(4, "Resident Evil 4 Chainsaw Demo", year=2023)).state != "linked"
    gears = _c(5, "Gears of War", year=2006)
    assert (
        compare(gears, _c(6, "Gears of War: E-Day Multiplayer Beta", year=2026)).relation != "same"
    )


# ------------------------------------------------------------- other games


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (_c(1, "STAR WARS Battlefront", year=2015), _c(2, "STAR WARS Battlefront II", year=2017)),
        (_c(1, "Halo 3", year=2007), _c(2, "Halo 4", year=2012)),
        (_c(1, "Battlefield 1942", year=2002), _c(2, "Battlefield 2042", year=2021)),
        (
            _c(1, "Gears of War", console="360", achievements=_list("g", 50)),
            _c(2, "Gears of War: Judgment", console="360", year=2013, achievements=_list("j", 50)),
        ),
        (
            _c(1, "Mass Effect Legendary Edition", year=2021),
            _c(2, "Mass Effect: Andromeda Deluxe Edition", store="steam", year=2020),
        ),
        (
            _c(
                1,
                "FINAL FANTASY VII REMAKE INTERGRADE",
                console="series",
                year=2026,
                store_group="ff7",
            ),
            _c(2, "FINAL FANTASY VII REBIRTH", console="series", year=2026, store_group="ff7"),
        ),
    ],
)
def test_other_games_are_never_one_game(a: Candidate, b: Candidate) -> None:
    v = compare(a, b)
    assert not (v.state == "linked" and v.relation == "same"), v.reasons


def test_a_namesake_by_another_studio_is_another_game() -> None:
    """Battlefront II 2005 (Pandemic) and 2017 (DICE): one name, two games."""
    old = _c(
        1,
        "STAR WARS Battlefront II (Classic, 2005)",
        store="steam",
        console="steam",
        year=2005,
        developer="Pandemic Studios",
        achievements=_list("old", 30),
    )
    new = _c(
        2, "STAR WARS Battlefront II", year=2017, developer="DICE", achievements=_list("new", 40)
    )
    v = compare(old, new)
    assert v.relation != "same" and not (v.state == "linked" and v.relation == "remake_of")


# --------------------------------------------------------- related games


def test_a_remaster_with_a_list_partly_its_originals() -> None:
    """Gears of War → Ultimate Edition: no "remaster" in the name, 40% shared."""
    shared = _list("g", 20)
    gears = _c(
        1,
        "Gears of War",
        console="360",
        developer="Epic Games",
        publisher="Microsoft Game Studios",
        achievements=shared,
        list_key=("xbox_360", "1"),
    )
    ue = _c(
        2,
        "Gears of War: Ultimate Edition",
        console="one",
        year=2015,
        developer="The Coalition",
        publisher="Microsoft Studios",
        achievements=frozenset(list(shared)[:8]) | _list("ue", 12),
        list_key=("xbox_modern", "2"),
    )
    v = compare(gears, ue)
    assert (v.subject, v.relation) == (2, "remaster_of"), v.reasons


def test_a_later_product_on_a_new_console_with_its_own_list_is_a_remaster() -> None:
    """Ghost of Tsushima Director's Cut on PS5 (owner, 2026-10-11)."""
    ps4 = _c(
        1,
        "Ghost of Tsushima",
        store="psn",
        console="ps4",
        year=2020,
        developer="Sucker Punch",
        list_key=("psn", "A"),
        achievements=_list("got", 50),
    )
    ps5 = _c(
        2,
        "Ghost of Tsushima Director's Cut",
        store="psn",
        console="ps5",
        year=2021,
        developer="Sucker Punch",
        list_key=("psn", "B"),
        achievements=_list("got", 50) | _list("iki", 16),
    )
    v = compare(ps4, ps5)
    assert (v.subject, v.relation) == (2, "remaster_of"), v.reasons


def test_a_remake_by_the_same_studio() -> None:
    old = _c(
        1,
        "Resident Evil 4 (2005)",
        store="steam",
        console="steam",
        year=2005,
        developer="CAPCOM",
        publisher="CAPCOM",
        achievements=_list("re4", 40),
    )
    new = _c(
        2,
        "Resident Evil 4",
        store="steam",
        console="steam",
        year=2023,
        developer="CAPCOM",
        publisher="CAPCOM",
        achievements=_list("re4r", 40),
    )
    v = compare(old, new)
    assert (v.subject, v.relation) == (2, "remake_of"), v.reasons
    assert v.state in ("linked", "review")


def test_a_vr_version() -> None:
    skyrim = _c(
        1,
        "The Elder Scrolls V: Skyrim Special Edition",
        store="steam",
        console="steam",
        year=2016,
        developer="Bethesda Game Studios",
    )
    vr = _c(
        2,
        "The Elder Scrolls V: Skyrim VR",
        store="steam",
        console="steam",
        year=2018,
        developer="Bethesda Game Studios",
    )
    v = compare(skyrim, vr)
    assert (v.subject, v.relation) == (2, "vr_of"), v.reasons


def test_a_compilation_holds_its_parts() -> None:
    halo3 = _c(
        1,
        "Halo 3",
        console="360",
        year=2007,
        developer="Bungie",
        publisher="Microsoft Game Studios",
        achievements=_list("h3", 49),
    )
    mcc = _c(
        2,
        "Halo: The Master Chief Collection",
        year=2014,
        developer="343 Industries",
        publisher="Microsoft Game Studios",
        achievements=_list("h3", 49) | _list("h2", 60) | _list("ce", 40),
    )
    v = compare(halo3, mcc)
    assert (v.subject, v.relation) == (2, "contains"), v.reasons


# ------------------------------------------------------------------ helpers


def test_an_edition_tail_never_takes_the_games_own_subtitle() -> None:
    from bot.services.game_match import game_core

    assert game_core("Mass Effect: Andromeda Deluxe Edition") == "mass effect andromeda"
    assert game_core("Mass Effect Legendary Edition") == "mass effect"
    assert game_core("Star Wars: Battlefront 2 (Classic, 2005)") == "star wars battlefront 2"


def test_game_facts_take_the_earliest_version() -> None:
    from bot.services.game_match import game_facts, version_year

    assert version_year("STAR WARS Battlefront II (Classic, 2005)", "2009-07-08") == 2005
    assert version_year("Halo (PC)", "2003-09-30", 2001) == 2001
    facts = game_facts(
        [
            {
                "name": "The Witcher 3: Wild Hunt",
                "release_date": "2015-05-19",
                "developer": "CD PROJEKT RED",
                "publisher": None,
                "kind": "version",
            },
            {
                "name": "The Witcher 3: Wild Hunt GOTY",
                "release_date": "2016-08-30",
                "developer": "CD PROJEKT RED Team",
                "publisher": "CD PROJEKT",
                "kind": "edition",
            },
            {"name": "A demo", "release_date": "2014-01-01", "developer": "X", "kind": "demo"},
        ]
    )
    assert (facts.year, facts.developer, facts.publisher) == (2015, "CD PROJEKT RED", "CD PROJEKT")


def test_game_facts_spread_over_versions() -> None:
    from bot.services.game_match import company_key, game_facts

    assert company_key("CD PROJEKT S.A.") == company_key("CD Projekt")
    assert company_key("BioWare™") == company_key("BioWare")
    facts = game_facts(
        [
            {
                "name": "Gears of War",
                "release_date": None,
                "stand_in": 1,
                "hltb_year": 2006,
                "developer": "Epic Games",
                "publisher": "Microsoft Game Studios",
                "kind": "version",
            },
            {
                "name": "Gears of War for Windows",
                "release_date": "2007-11-06",
                "developer": "Epic Games, People Can Fly",
                "publisher": "Microsoft Studios",
                "kind": "version",
            },
        ]
    )
    assert (facts.year, facts.last_year) == (2006, 2007)
    assert facts.more_publishers


def test_one_year_for_the_matcher_and_the_facts() -> None:
    from bot.services.game_match import candidate_year

    classic = {"name": "STAR WARS Battlefront II (Classic, 2005)", "release_date": "2009-07-08"}
    assert candidate_year(classic) == 2005
    assert candidate_year({"name": "Halo", "release_date": "2011-11-15", "hltb_year": 2001}) == 2011
    assert candidate_year({"name": "Halo", "stand_in": 1, "hltb_year": 2001}) == 2001


def test_studios_compare_as_companies() -> None:
    from bot.services.game_match import _same

    assert _same("CD PROJEKT S.A.", "CD Projekt")
    assert _same("BioWare™", "BioWare")
    assert not _same("DICE", "Pandemic Studios")


# ------------------------------------------------------------------- linker


async def _version(repo: Repo, product: str, name: str, year: str, **kw: object) -> int:
    version = StoreVersion(
        store=str(kw.pop("store", "xbox")),
        product_id=product,
        console=str(kw.pop("console", "one")),
        name=name,
        kind=str(kw.pop("kind", "game")),
        developer=str(kw.pop("developer", "CD PROJEKT RED")),
        release_date=f"{year}-05-19" if year else None,
    )
    return await repo.save_version(version, platform=None, title_id=None)


async def test_versions_become_one_game_and_a_label_keeps_one_out(repo: Repo) -> None:
    xbox = await _version(repo, "BR765873CQJD", "The Witcher 3: Wild Hunt", "2015")
    steam = await _version(
        repo, "292030", "The Witcher 3: Wild Hunt", "2015", store="steam", console="steam"
    )
    linker = GameLinker(repo)
    report = await linker.link_versions([xbox, steam])
    [(game, members)] = report.games.items()
    assert sorted(members) == sorted([xbox, steam])

    # The operator says the Steam one is not this game: every rebuild keeps it out.
    await repo.save_decision(steam, xbox, "other", features=None, model=None, decided_by="t")
    await linker.link_versions([xbox, steam])
    assert await repo.linked_game_of(xbox) == game
    assert await repo.linked_game_of(steam) not in (None, game)
    await linker.link_all()
    assert await repo.linked_game_of(steam) != await repo.linked_game_of(xbox)


async def test_a_label_makes_a_relation_and_survives_rebuilds(repo: Repo) -> None:
    old = await _version(repo, "RE4", "resident evil 4", "2005", developer="Capcom")
    new = await _version(repo, "RE4R", "Resident Evil 4", "2023", developer="Capcom")
    linker = GameLinker(repo)
    await linker.link_versions([old, new])
    await repo.save_decision(new, old, "remake_of", features=None, model=None, decided_by="t")
    await linker.link_versions([old, new])
    g_old, g_new = await repo.linked_game_of(old), await repo.linked_game_of(new)
    assert g_old != g_new
    cur = await repo._conn.execute("SELECT game_id, related_id, kind, source FROM game_relations")
    assert [tuple(r) for r in await cur.fetchall()] == [(g_new, g_old, "remake_of", "manual")]
    await linker.link_all()
    assert (await repo.linked_game_of(old), await repo.linked_game_of(new)) == (g_old, g_new)


async def test_chains_do_not_drag_other_games_in(repo: Repo) -> None:
    """A~B and B~C used to put A and C in one game even when A and C are
    sure to differ; a veto now keeps them apart."""
    a = await _version(repo, "A", "Gears of War", "2006")
    b = await _version(repo, "B", "Gears of War", "2006", store="steam", console="steam")
    c = await _version(repo, "C", "Gears of War 2", "2008")
    await repo.save_decision(b, c, "same", features=None, model=None, decided_by="t")
    await GameLinker(repo).link_versions([a, b, c])
    # b joins c by the label; a is sure to differ from c, so it stays apart.
    assert await repo.linked_game_of(b) == await repo.linked_game_of(c)
    assert await repo.linked_game_of(a) != await repo.linked_game_of(c)


async def test_a_demo_is_of_the_version_on_its_console(repo: Repo) -> None:
    game_one = await _version(repo, "RE2", "RESIDENT EVIL 2", "2019", console="one")
    game_series = await _version(repo, "RE2", "RESIDENT EVIL 2", "2019", console="series")
    demo = await _version(repo, "DEMO", "RESIDENT EVIL 2 1-Shot Demo", "2019", console="series")
    await GameLinker(repo).link_versions([game_one, game_series, demo])
    cur = await repo._conn.execute(
        "SELECT role, of_version_id FROM game_versions WHERE version_id = ?", (demo,)
    )
    assert tuple(await cur.fetchone()) == ("demo", game_series)


async def test_a_game_keeps_its_id_through_a_rebuild(repo: Repo) -> None:
    a = await _version(repo, "A", "Cyberpunk 2077", "2020")
    b = await _version(repo, "B", "Cyberpunk 2077", "2020", store="steam", console="steam")
    linker = GameLinker(repo)
    await linker.link_versions([a, b])
    game = await repo.linked_game_of(a)
    await repo.rename_game(game, "Киберпанк", None, "manual")
    await linker.link_all()
    await linker.link_versions([b])
    assert await repo.linked_game_of(a) == await repo.linked_game_of(b) == game
    cur = await repo._conn.execute("SELECT name FROM games WHERE game_id = ?", (game,))
    assert (await cur.fetchone())[0] == "Киберпанк"


async def test_a_stand_in_becomes_its_product_and_keeps_its_labels(repo: Repo) -> None:
    stand_in = StoreVersion(
        store="xbox", product_id="123", console="one", name="Game", stand_in=True
    )
    sid = await repo.save_version(stand_in, platform="xbox_modern", title_id="123")
    other = await _version(repo, "OTHER", "Other Game", "2015")
    await repo.save_decision(sid, other, "other", features=None, model=None, decided_by="t")
    product = StoreVersion(store="xbox", product_id="BIGID", console="one", name="Game")
    pid = await repo.save_version(product, platform="xbox_modern", title_id="123")
    assert pid == sid
    assert await repo.decisions_among([sid])


# ------------------------------------------- owner's second look (2026-10-11)


def test_a_namesake_far_apart_is_always_the_operators() -> None:
    """RE5 2009 and its 2016 release, CoD: Modern Warfare 2007 and 2019: one
    name years apart may be a port, a remake or another game."""
    re5 = _c(
        1,
        "RESIDENT EVIL 5",
        console="360",
        year=2009,
        developer="CAPCOM",
        list_key=("xbox_360", "1"),
        achievements=_list("re5", 50),
    )
    re5_one = _c(
        2,
        "Resident Evil 5",
        console="one",
        year=2016,
        developer="CAPCOM",
        list_key=("xbox_modern", "2"),
        achievements=_list("re5", 50),
    )
    assert compare(re5, re5_one).state == "review"
    mw = _c(
        3,
        "Call of Duty 4: Modern Warfare",
        store="steam",
        console="steam",
        year=2007,
        developer="Infinity Ward",
    )
    mw19 = _c(
        4,
        "Call of Duty: Modern Warfare",
        store="steam",
        console="steam",
        year=2019,
        developer="Infinity Ward",
    )
    cod = _c(5, "Call of Duty: Modern Warfare", console="one", year=2019, developer="Infinity Ward")
    assert compare(mw19, cod).relation == "same"
    assert compare(mw, mw19).relation != "same" or compare(mw, mw19).state == "review"


def test_two_subtitles_of_one_name_are_two_games() -> None:
    rebirth = _c(1, "FINAL FANTASY VII REBIRTH", store="steam", console="steam", year=2025)
    revelation = _c(2, "FINAL FANTASY VII REVELATION", store="steam", console="steam", year=2027)
    assert compare(rebirth, revelation).relation != "same"


def test_a_later_list_in_the_same_store_is_a_remaster() -> None:
    """Skyrim (2011) and Special Edition (2016): two Steam apps, two lists."""
    skyrim = _c(
        1,
        "The Elder Scrolls V: Skyrim",
        store="steam",
        console="steam",
        year=2011,
        developer="Bethesda Game Studios",
        list_key=("steam", "72850"),
        achievements=_list("sk", 75),
    )
    se = _c(
        2,
        "The Elder Scrolls V: Skyrim Special Edition",
        store="steam",
        console="steam",
        year=2016,
        developer="Bethesda Game Studios",
        list_key=("steam", "489830"),
        achievements=_list("sk", 75),
    )
    v = compare(skyrim, se)
    assert (v.subject, v.relation) == (2, "remaster_of"), v.reasons


async def test_not_related_takes_every_link_between_two_games_away(repo: Repo) -> None:
    """Owner, 2026-10-11: game ↔ game is its own question; "not related"
    between the two games clears the model's relation and its review row."""
    old = await _version(repo, "DS", "Dark Souls", "2011", developer="FromSoftware")
    old_pc = await _version(
        repo, "DSPC", "Dark Souls", "2011", store="steam", console="steam", developer="FromSoftware"
    )
    new = await _version(repo, "DSR", "Dark Souls Remastered", "2018", developer="FromSoftware")
    linker = GameLinker(repo)
    await linker.link_versions([old, old_pc, new])
    assert await repo.linked_game_of(new) != await repo.linked_game_of(old)
    await repo.save_decision(new, old, "other", features=None, model=None, decided_by="t")
    await linker.link_all()
    cur = await repo._conn.execute("SELECT COUNT(*) FROM game_relations")
    assert (await cur.fetchone())[0] == 0
    cur = await repo._conn.execute(
        "SELECT COUNT(*) FROM match_pairs WHERE ? IN (version_id, other_id)", (new,)
    )
    assert (await cur.fetchone())[0] == 0


# ------------------------------------------------ the full run's lessons


def test_a_lost_name_says_nothing() -> None:
    """Production's PSN lists named "?": "?" and "?" are not one name."""
    a = _c(1, "?", store="psn", console="ps4", year=2014)
    b = _c(2, "?", store="psn", console="ps4", year=2017)
    assert compare(a, b).relation != "same"


def test_a_lego_game_is_not_its_namesake() -> None:
    lego = _c(1, "LEGO Marvel's Avengers", year=2016)
    game = _c(2, "Marvel's Avengers", year=2020)
    v = compare(lego, game)
    assert not (v.state == "linked" and v.relation != "other"), v.reasons


def test_an_ampersand_is_no_compilation() -> None:
    two = _c(1, "Coffee Talk Episode 2: Hibiscus & Butterfly", year=2023)
    one = _c(2, "Coffee Talk", year=2020)
    assert "compilation_word" not in compare(two, one).features


def test_the_same_name_a_few_years_later_on_a_newer_console_is_a_port() -> None:
    """Terraria 360 (2011) and One (2014): no release word, not a remaster."""
    old = _c(
        1,
        "Terraria",
        console="360",
        year=2011,
        list_key=("xbox_360", "1"),
        achievements=_list("t", 40),
    )
    new = _c(
        2,
        "Terraria",
        console="one",
        year=2014,
        list_key=("xbox_modern", "2"),
        achievements=_list("t", 60),
    )
    assert compare(old, new).relation != "remaster_of"


def test_a_game_name_keeps_the_games_own_words() -> None:
    from bot.services.game_match import game_name

    se = _c(1, "The Elder Scrolls V: Skyrim Special Edition", store="steam", console="steam")
    assert game_name([se]) == "The Elder Scrolls V: Skyrim Special Edition"
    assert game_name([_c(2, "Gears of War 4")]) == "Gears of War 4"


def test_two_games_of_one_pack_released_together_are_two_games() -> None:
    """Return to Arkham (owner, 2026-10-12): its Asylum on One and its City on
    Series came out the same year in one bundle — still two games."""
    common = {"store": "xbox", "year": 2016, "developer": "Rocksteady", "store_group": "RTA"}
    asylum = _c(
        1,
        "Batman: Return to Arkham - Arkham Asylum",
        console="one",
        list_key=("xbox_modern", "A"),
        achievements=_list("asylum", 47),
        **common,
    )
    city = _c(
        2,
        "Batman: Return to Arkham - Arkham City",
        console="series",
        list_key=("xbox_modern", "C"),
        achievements=_list("city", 70),
        **common,
    )
    assert "cross_gen_pair" not in features(asylum, city)
    assert not _linked(asylum, city, "same"), compare(asylum, city).reasons


async def test_a_beta_stays_with_its_game_ported_years_later(repo: Repo) -> None:
    """Battlefield V: its beta and the One version in 2018, Steam in 2020 — the
    beta is far from the Steam release, and that keeps it out of nothing."""
    one = await _version(repo, "BFV1", "Battlefield V", "2018", developer="DICE")
    steam = await _version(
        repo, "1238810", "Battlefield V", "2020", store="steam", console="steam", developer="DICE"
    )
    beta = await _version(repo, "BFVB", "Battlefield V Open Beta", "2018", developer="DICE")
    await GameLinker(repo).link_versions([one, steam, beta])
    game = await repo.linked_game_of(one)
    assert await repo.linked_game_of(steam) == game
    assert await repo.linked_game_of(beta) == game


async def test_a_remaster_of_a_remake_points_at_the_remake(repo: Repo) -> None:
    """Gears of War (owner, 2026-10-12): Ultimate Edition is a remake of the
    2006 game, Reloaded a remaster of Ultimate Edition — not of the 2006 one."""
    gow = await _version(repo, "GOW", "Gears of War", "2006", developer="Epic Games")
    ue = await _version(
        repo, "UE", "Gears of War: Ultimate Edition", "2015", developer="The Coalition"
    )
    reloaded = await _version(
        repo, "RL", "Gears of War: Reloaded", "2025", developer="The Coalition"
    )
    await repo.save_decision(ue, gow, "remake_of", features=None, model=None, decided_by="t")
    await repo.save_decision(reloaded, ue, "remaster_of", features=None, model=None, decided_by="t")
    await GameLinker(repo).link_versions([gow, ue, reloaded])
    g_gow, g_ue, g_rl = [await repo.linked_game_of(v) for v in (gow, ue, reloaded)]
    assert len({g_gow, g_ue, g_rl}) == 3
    cur = await repo._conn.execute("SELECT game_id, related_id, kind FROM game_relations")
    assert sorted(tuple(r) for r in await cur.fetchall()) == sorted(
        [(g_ue, g_gow, "remake_of"), (g_rl, g_ue, "remaster_of")]
    )


# ------------------------------------------------------------------ modes (2026-10-12)

BO2 = frozenset(f"bo2 {i}" for i in range(90))


def test_a_steam_mode_launcher_is_a_part_of_its_game() -> None:
    """Black Ops II on Steam: campaign (202970) and a Zombies launcher (212910,
    type "advertising") whose 50 achievements are part of the 360 list's 90."""
    zombies = _c(
        3,
        "Call of Duty: Black Ops II - Zombies",
        store="steam",
        console="steam",
        kind="advertising",
        achievements=frozenset(list(BO2)[:50]),
    )
    campaign = _c(4, "Call of Duty: Black Ops II", store="steam", console="steam", year=2012)
    x360 = _c(5, "COD: Black Ops II", console="360", achievements=BO2, list_key=("x", "1"))
    assert kind_of(zombies) == "mode"
    for game in (campaign, x360):
        f = compare(game, zombies).features
        assert "mode_of" in f and "list_subset" not in f
        assert _linked(game, zombies, "same"), compare(game, zombies).reasons
    # Another series' game is not its game, whatever its type.
    assert "mode_of" not in features(_c(6, "Call of Duty: Ghosts", year=2013), zombies)


def test_cod_reads_as_call_of_duty() -> None:
    """Microsoft names the 360 list "COD: Black Ops II"."""
    x360 = _c(1, "COD: Black Ops II", console="360", year=2012)
    steam = _c(2, "Call of Duty: Black Ops II", store="steam", console="steam", year=2012)
    assert "full_name" in features(x360, steam)
    assert _linked(x360, steam, "same"), compare(x360, steam).reasons
    from bot.services.game_match import game_name, name_key

    assert name_key("COD: MW Bundle") == name_key("Call of Duty: MW Bundle")
    assert name_key("Cod Fishing") == "cod fishing"  # only Microsoft's capitals
    assert game_name([x360]) == "Call of Duty: Black Ops II"


async def test_a_mode_is_recorded_as_a_mode_of_its_game(repo: Repo) -> None:
    game = await _version(
        repo, "202970", "Call of Duty: Black Ops II", "2012", store="steam", console="steam"
    )
    zombies = await _version(
        repo,
        "212910",
        "Call of Duty: Black Ops II - Zombies",
        "",
        store="steam",
        console="steam",
        kind="advertising",
    )
    await GameLinker(repo).link_versions([game, zombies])
    assert await repo.linked_game_of(zombies) == await repo.linked_game_of(game)
    cur = await repo._conn.execute(
        "SELECT role, of_version_id FROM game_versions WHERE version_id = ?", (zombies,)
    )
    assert tuple(await cur.fetchone()) == ("mode", game)


# ------------------------------------------------------------------ kinds (2026-10-12)


def test_an_extra_is_never_one_game_with_its_game_nor_related() -> None:
    from bot.services.game_match import is_extra

    doom = _c(1, "DOOM: The Dark Ages", console="series", year=2025)
    book = _c(2, "DOOM: The Dark Ages Digital Artbook and Soundtrack", console="series", year=2025)
    ost = _c(3, "The Alters: Original Soundtrack", console="pc", kind="app")
    insider = _c(4, "Sea of Thieves Insider", console="one", year=2018)
    assert all(is_extra(c) for c in (book, ost, insider))
    assert not is_extra(doom) and not is_extra(_c(5, "Comic Jumper"))
    v = compare(doom, book)
    assert v.state == "apart" and "extra_pair" in v.features
    assert compare(_c(6, "Sea of Thieves", console="one", year=2018), insider).state == "apart"
    # One extra on two consoles is still one extra.
    insider_series = _c(7, "Sea of Thieves Insider", console="series", year=2018)
    assert _linked(insider, insider_series, "same")


def test_a_compilation_is_never_one_game_with_one_of_its_games() -> None:
    mcc = _c(1, "Halo: The Master Chief Collection", year=2014, developer="343 Industries")
    halo = _c(2, "Halo: Combat Evolved", year=2014, developer="343 Industries")
    assert compare(mcc, halo).relation != "same"
    # HLTB filing it as a compilation says so too.
    hltb = _c(3, "Uncharted: Legacy of Thieves", hltb_types=frozenset({"compil"}), year=2022)
    plain = _c(4, "Uncharted 4: A Thief's End", year=2016)
    assert "compilation_word" in features(hltb, plain)


async def test_games_get_their_kind_and_the_operators_stands(repo: Repo) -> None:
    game = await _version(repo, "DOOM", "DOOM: The Dark Ages", "2025")
    book = await _version(
        repo, "BOOK", "DOOM: The Dark Ages Digital Artbook and Soundtrack", "2025"
    )
    coll = await _version(repo, "COLL", "BioShock: The Collection", "2016")
    linker = GameLinker(repo)
    await linker.link_versions([game, book, coll])

    async def kind(version: int) -> tuple[str, str]:
        cur = await repo._conn.execute(
            "SELECT kind, kind_source FROM games WHERE game_id = ?",
            (await repo.linked_game_of(version),),
        )
        return tuple(await cur.fetchone())  # type: ignore[return-value]

    assert await repo.linked_game_of(book) != await repo.linked_game_of(game)
    assert await kind(game) == ("game", "auto")
    assert await kind(book) == ("extra", "auto")
    assert await kind(coll) == ("compilation", "auto")
    await repo.set_game_kind_manual(await repo.linked_game_of(coll), "game")  # type: ignore[arg-type]
    await linker.link_all()
    assert await kind(coll) == ("game", "manual")


# ------------------------------------------------------------------ names (2026-10-12)


def test_a_game_keeps_the_release_words_all_its_versions_share() -> None:
    """Every version "… Ultimate Edition": the game is the Ultimate Edition,
    the platform tail cut — not "Control"."""
    from bot.services.game_match import game_name, release_tail

    xbox = _c(1, "CONTROL Ultimate Edition", console="one", year=2020)
    series = _c(2, "Control Ultimate Edition - Xbox Series X|S", console="series", year=2021)
    assert release_tail("CONTROL Ultimate Edition") == ("ultimate",)
    assert game_name([xbox, series]) == "CONTROL Ultimate Edition"
    assert game_name([_c(3, "Dark Souls: Remastered (PC)", store="steam")]) == (
        "Dark Souls: Remastered"
    )
    goty = _c(4, "Batman: Arkham City - Game of the Year Edition", store="steam")
    goty2 = _c(5, "Batman: Arkham City GOTY", console="360")
    # GOTY and "Game of the Year Edition" are one tail; the earliest names it.
    assert game_name([goty, goty2]) == "Batman: Arkham City GOTY"


def test_versions_that_differ_in_their_tails_give_the_common_core() -> None:
    from bot.services.game_match import game_name, release_name

    base = _c(1, "Control", store="steam", console="steam", year=2019)
    ultimate = _c(2, "CONTROL Ultimate Edition", console="one", year=2020)
    assert game_name([ultimate, base]) == "Control"
    # A standard edition or a platform's edition is no release of its own.
    assert game_name([_c(3, "Forza Horizon 4 Standard Edition")]) == "Forza Horizon 4"
    assert release_name("Minecraft: Windows 10 Edition") == "Minecraft"
    # A demo says nothing about the name.
    demo = _c(4, "Control Demo", store="steam", console="steam", kind="demo", year=2019)
    assert game_name([base, demo]) == "Control"


async def test_a_remaster_is_named_by_its_own_release(repo: Repo) -> None:
    """A remaster whose versions differ in their tails still keeps its own
    words: it is told apart from its original."""
    old = await _version(repo, "DS1", "Dark Souls: Prepare to Die Edition", "2012")
    new = await _version(repo, "DSR", "Dark Souls: Remastered", "2018", console="series")
    await repo.save_decision(new, old, "remaster_of", features=None, model=None, decided_by="t")
    await GameLinker(repo).link_versions([old, new])
    names = await repo.game_names(
        [await repo.linked_game_of(old), await repo.linked_game_of(new)]  # type: ignore[list-item]
    )
    assert sorted(n for n, _ in names.values()) == [
        "Dark Souls: Prepare to Die Edition",
        "Dark Souls: Remastered",
    ]


# ------------------------------------------------------------------ PC stores (2026-10-12)


def test_a_win32_list_is_a_pc_version_of_an_unknown_store() -> None:
    from bot.services.stores import UNKNOWN_STORE, pc_of_unknown_store

    assert pc_of_unknown_store("xbox_modern", '["Win32"]')
    assert not pc_of_unknown_store("xbox_modern", '["PC"]')  # Microsoft's own PC
    assert not pc_of_unknown_store("xbox_modern", '["Win32", "XboxOne"]')
    assert not pc_of_unknown_store("steam", '["Win32"]')
    seen = _c(1, "Heavy Rain", store=UNKNOWN_STORE, console="pc", stand_in=True, year=2019)
    steam = _c(2, "Heavy Rain", store="steam", console="steam", year=2019)
    ps4 = _c(3, "HEAVY RAIN™", store="psn", console="ps4", year=2010)
    for other in (steam, ps4):
        v = compare(seen, other)
        assert "unknown_pc_namesake" in v.features
        assert _linked(seen, other, "same"), v.reasons
    # Another name is no namesake: the sign needs the very same release.
    assert "unknown_pc_namesake" not in features(seen, _c(4, "Heavy Rain 2", store="steam"))


async def test_a_win32_list_joins_its_namesakes_game(repo: Repo) -> None:
    from bot.services.store_collect import _store_of
    from bot.services.stores import UNKNOWN_STORE

    assert _store_of("xbox_modern", '["Win32"]') == UNKNOWN_STORE
    assert _store_of("xbox_modern", '["PC", "XboxOne"]') == "xbox"
    ps4 = await _version(repo, "HR4", "HEAVY RAIN™", "2016", store="psn", console="ps4")
    steam = await _version(repo, "960910", "Heavy Rain", "2019", store="steam", console="steam")
    seen = await _version(repo, "1743969133", "Heavy Rain", "", store=UNKNOWN_STORE, console="pc")
    await GameLinker(repo).link_versions([ps4, steam, seen])
    game = await repo.linked_game_of(steam)
    assert await repo.linked_game_of(seen) == game
    assert await repo.linked_game_of(ps4) == game


def _migration(name: str) -> str:
    from bot.db.repo import MIGRATIONS_DIR

    return (MIGRATIONS_DIR / name).read_text(encoding="utf-8")


async def test_migration_104_moves_win32_stand_ins_to_the_unknown_store(repo: Repo) -> None:
    conn = repo._conn
    for title_id, platforms in (("1", '["Win32"]'), ("2", '["PC"]')):
        await conn.execute(
            "INSERT INTO titles (platform, title_id, name, platforms, updated_at)"
            " VALUES (?, ?, ?, ?, 'now')",
            ("xbox_modern", title_id, f"Game {title_id}", platforms),
        )
        await conn.execute(
            "INSERT INTO versions (store, product_id, console, platform, title_id, name,"
            " updated_at, stand_in) VALUES ('xbox', ?, 'pc', 'xbox_modern', ?, ?, 'now', 1)",
            (title_id, title_id, f"Game {title_id}"),
        )
    await conn.execute(_migration("104_pc_unknown_store.sql"))  # one statement
    cur = await conn.execute("SELECT product_id, store FROM versions ORDER BY product_id")
    assert [tuple(r) for r in await cur.fetchall()] == [("1", "unknown"), ("2", "xbox")]


async def test_a_label_outlives_its_version(repo: Repo) -> None:
    """A store re-parse deleting a version must not delete the operator's
    answer about it (migration 106): the label stays, with which product each
    side was."""
    xbox = await _version(repo, "BR765873CQJD", "The Witcher 3: Wild Hunt", "2015")
    steam = await _version(
        repo, "292030", "The Witcher 3: Wild Hunt", "2015", store="steam", console="steam"
    )
    await repo.save_decision(steam, xbox, "other", features=None, model=None, decided_by="t")
    await repo.delete_version(steam)
    cur = await repo._conn.execute(
        "SELECT version_id, other_id, relation, subject_key, other_key FROM match_decisions"
    )
    assert [tuple(r) for r in await cur.fetchall()] == [
        (steam, xbox, "other", "steam:292030:steam", "xbox:BR765873CQJD:one")
    ]
    await GameLinker(repo).link_all()  # a label whose version is gone is simply not read
