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


def test_a_later_product_on_a_new_console_with_its_own_list_is_an_edition() -> None:
    """Ghost of Tsushima Director's Cut on PS5 (owner, 2026-10-11): a
    remaster then; the game with more of it, an enhanced edition, since
    that is a class of its own (owner, 2026-10-27)."""
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
    assert (v.subject, v.relation) == (2, "enhanced_of"), v.reasons


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
        "SELECT role, of_version_id FROM versions WHERE version_id = ?", (demo,)
    )
    assert tuple(await cur.fetchone()) == ("demo", game_series)


async def test_the_linker_scores_with_the_active_weights_in_the_database(repo: Repo) -> None:
    from bot.services.game_match import WEIGHTS, model_name, use_weights

    a = await _version(repo, "A", "Cyberpunk 2077", "2020")
    b = await _version(repo, "B", "Cyberpunk 2077", "2020", store="steam", console="steam")
    linker = GameLinker(repo)
    try:
        # A fit that never says "one game": the pair falls apart.
        apart = {c: dict(w) for c, w in WEIGHTS.items()}
        apart["same"] = {"bias": -40.0}
        kept = await repo.add_match_weights(
            apart, gate_before=0.5, gate_after=0.6, labels=10, activate=True
        )
        await linker.link_versions([a, b])
        assert model_name().endswith(f"/w{kept}")
        assert await repo.linked_game_of(a) != await repo.linked_game_of(b)
        # Back to the hand weights: one game again.
        await repo.activate_match_weights(None)
        await linker.link_versions([a, b])
        assert await repo.linked_game_of(a) == await repo.linked_game_of(b)
        assert [r["active"] for r in await repo.match_weights_list()] == [0]
    finally:
        use_weights(None)


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
        "SELECT role, of_version_id FROM versions WHERE version_id = ?", (zombies,)
    )
    assert tuple(await cur.fetchone()) == ("mode", game)


# ------------------------------------------------------------------ kinds (2026-10-12)


def test_a_soundtrack_or_artbook_is_a_part_of_the_game_it_names() -> None:
    """Owner, 2026-10-14: a soundtrack or an artbook belongs to its game, as
    a demo does — the game its name names whole, never a shorter one; an
    Insider build is a beta; an app of no game stays apart."""
    from bot.services.game_match import extra_game_name, is_extra, kind_of

    doom = _c(1, "DOOM: The Dark Ages", console="series", year=2025)
    book = _c(2, "DOOM: The Dark Ages Digital Artbook and Soundtrack", console="series")
    ost = _c(3, "The Alters: Original Soundtrack", console="pc", kind="app")
    insider = _c(4, "Sea of Thieves Insider", console="one", year=2018)
    assert is_extra(book) and is_extra(ost) and not is_extra(insider)
    assert kind_of(insider) == "demo"
    assert not is_extra(doom) and not is_extra(_c(5, "Comic Jumper"))
    assert extra_game_name(book) == "doom the dark ages"
    assert extra_game_name(ost) == "alters"
    v = compare(doom, book)
    assert v.state == "linked" and v.relation == "same" and "extra_of" in v.features
    # Not the series' first game, whose name only opens the artbook's.
    old = _c(6, "DOOM", console="steam", year=2016)
    v = compare(old, book)
    assert v.state == "apart" and "extra_pair" in v.features
    # An app is no part of a game.
    app = _c(7, "Xbox Console Companion", console="pc", kind="app")
    assert compare(app, doom).state == "apart"


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

    # The artbook is a part of its game: the game stays a game.
    assert await repo.linked_game_of(book) == await repo.linked_game_of(game)
    cur = await repo._conn.execute(
        "SELECT role, of_version_id FROM versions WHERE version_id = ?", (book,)
    )
    assert tuple(await cur.fetchone()) == ("extra", game)
    assert await kind(game) == ("game", "auto")
    app = await _version(repo, "APP", "Xbox Console Companion", "2018")
    await repo._conn.execute("UPDATE versions SET kind = 'app' WHERE version_id = ?", (app,))
    await linker.link_versions([app])
    assert await kind(app) == ("extra", "auto")
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
    from bot.services.stores import UNKNOWN_STORE
    from bot.services.stores import store_of as _store_of

    assert _store_of("xbox_modern", '["Win32"]') == UNKNOWN_STORE
    assert _store_of("xbox_modern", '["PC", "XboxOne"]') == "xbox"
    ps4 = await _version(repo, "HR4", "HEAVY RAIN™", "2016", store="psn", console="ps4")
    steam = await _version(repo, "960910", "Heavy Rain", "2019", store="steam", console="steam")
    seen = await _version(repo, "1743969133", "Heavy Rain", "", store=UNKNOWN_STORE, console="pc")
    await GameLinker(repo).link_versions([ps4, steam, seen])
    game = await repo.linked_game_of(steam)
    assert await repo.linked_game_of(seen) == game
    assert await repo.linked_game_of(ps4) == game
    # A known-store PC version (Steam) covers it (owner, 2026-10-12).
    cur = await repo._conn.execute("SELECT role FROM versions WHERE version_id = ?", (seen,))
    assert (await cur.fetchone())[0] == "covered"


async def test_a_lone_unknown_store_pc_version_is_shown(repo: Repo) -> None:
    """With no PC version of a known store, "pc (store unknown)" is the game's PC."""
    from bot.services.stores import UNKNOWN_STORE

    ps4 = await _version(repo, "HR4", "HEAVY RAIN™", "2016", store="psn", console="ps4")
    seen = await _version(repo, "1743969133", "Heavy Rain", "", store=UNKNOWN_STORE, console="pc")
    await GameLinker(repo).link_versions([ps4, seen])
    cur = await repo._conn.execute("SELECT role FROM versions WHERE version_id = ?", (seen,))
    assert (await cur.fetchone())[0] == "version"


def _migration(name: str) -> str:
    from bot.db.repo import MIGRATIONS_DIR

    return (MIGRATIONS_DIR / name).read_text(encoding="utf-8")


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


# ------------------------------------------------------------- stores' texts


def test_a_remaster_s_description_and_the_other_game_it_names_are_signs() -> None:
    old = _c(1, "Dark Souls: Prepare to Die Edition", year=2012, blurb="A dark fantasy action RPG.")
    new = _c(
        2,
        "DARK SOULS: REMASTERED",
        year=2018,
        blurb="Re-experience Dark Souls, beautifully remastered in high definition at 60fps.",
    )
    f = features(old, new)
    assert f["text_remaster"] == 1.0
    assert "text_remake" not in f


def test_two_descriptions_saying_the_same_and_genres_that_differ() -> None:
    text = "Hunt monsters across a vast open world as a witcher for hire."
    a = _c(1, "Witcher 3", year=2015, blurb=text, genres=frozenset({"rpg"}))
    b = _c(2, "Witcher 3", year=2015, store="steam", blurb=text, genres=frozenset({"racing"}))
    f = features(a, b)
    assert f["text_same"] == 1.0
    assert f["genres_differ"] == 1.0


def test_text_signs_change_nothing_until_weights_are_fitted() -> None:
    a = _c(1, "Halo", year=2001, blurb="The original classic, remastered in HD.")
    b = _c(2, "Halo", year=2001, store="steam", blurb="A sci-fi shooter.")
    plain = _c(1, "Halo", year=2001)
    other = _c(2, "Halo", year=2001, store="steam")
    assert compare(a, b).probs == compare(plain, other).probs


# ------------------------------------------------ a version holds its game (108)


async def test_linking_writes_the_game_on_the_version_and_keeps_when_it_got_there(
    repo: Repo,
) -> None:
    game = await _version(repo, "G", "Control", "2019")
    demo = await _version(repo, "D", "Control Demo", "2019", kind="demo")
    await GameLinker(repo).link_versions([game, demo])
    cursor = await repo._conn.execute(
        "SELECT game_id, role, of_version_id, linked_at FROM versions WHERE version_id = ?",
        (demo,),
    )
    first = tuple(await cursor.fetchone())
    assert first[1:3] == ("demo", game) and first[0] == await repo.linked_game_of(game)

    await GameLinker(repo).link_versions([game, demo])
    cursor = await repo._conn.execute(
        "SELECT linked_at FROM versions WHERE version_id = ?", (demo,)
    )
    assert (await cursor.fetchone())[0] == first[3]
    lonely = await _version(repo, "L", "Some Other Game", "2001")
    assert await repo.linked_game_of(lonely) is None


# --------------------------------------------- the word "Remake" marks a remake (2026-10-14)


def test_the_word_remake_marks_a_remake_and_intergrade_does_not() -> None:
    ff7 = _c(1, "FINAL FANTASY VII", console="ps4", year=1997)
    remake = _c(2, "FINAL FANTASY VII REMAKE", console="ps4", year=2020)
    intergrade = _c(3, "FINAL FANTASY VII REMAKE INTERGRADE", console="ps5", year=2021)
    director = _c(4, "Ghost of Tsushima Director's Cut", console="ps5", year=2021)
    base = _c(5, "Ghost of Tsushima", console="ps4", year=2020)

    assert features(remake, ff7)["remake_word"] == 1.0
    # Both say it: nothing in the words tells the two apart (the operator did).
    assert "remake_word" not in features(intergrade, remake)
    # "Intergrade", "Director's Cut" alone mark nothing of a remake.
    assert "remake_word" not in features(director, base)
    assert "remake_word" not in features(_c(6, "Final Fantasy VII Intergrade", year=2021), ff7)


async def test_a_version_keeps_how_it_was_first_found(repo: Repo) -> None:
    from bot.services.stores import StoreVersion

    version = StoreVersion(store="steam", product_id="10", console="steam", name="A Game")
    first = await repo.save_version(
        version, platform=None, title_id=None, origin="store", found=("hltb", "hltb:42")
    )
    again = await repo.save_version(
        version, platform=None, title_id=None, origin="store", found=("search", "name:a game")
    )
    row = await repo.version_row(first)
    assert again == first
    assert (row["found_how"], row["found_via"]) == ("hltb", "hltb:42")
    assert row["found_at"]


async def test_a_stand_ins_name_follows_its_lists(repo: Repo) -> None:
    await repo._conn.execute(
        "INSERT INTO achievement_list_connectors (platform, title_id, name, updated_at)"
        " VALUES ('xbox_360', '9', 'Old Name', '2026-10-15T00:00:00')"
    )
    await repo._conn.commit()
    (version,) = await repo.ensure_list_version("xbox_360", "9")
    await repo._conn.execute(
        "UPDATE achievement_list_connectors SET name = 'New Name', name_ru = 'Новое'"
        " WHERE title_id = '9'"
    )
    await repo._conn.commit()
    row = await repo.version_row(version)
    assert (row["name"], row["name_ru"]) == ("New Name", "Новое")


async def test_steam_is_the_main_games_and_xbox_and_psn_keep_their_own(
    repo: Repo,
) -> None:
    from bot.constants import achievement_group
    from bot.services.xbox.models import xbox_group

    assert achievement_group("steam", None) == "main_game"
    assert achievement_group("xbox_modern", None) is None  # not known yet
    assert achievement_group("xbox_modern", "base") == "base"
    assert (xbox_group(["0"]), xbox_group([]), xbox_group(None)) == ("base", "non_base", None)
    assert achievement_group("psn", None) is None  # not fetched with its groups yet
    assert achievement_group("psn", "001") == "001"


async def test_a_psn_groups_become_dlc_of_every_version_of_its_list(repo: Repo) -> None:
    await repo._conn.execute(
        "INSERT INTO achievement_list_connectors (platform, title_id, name, updated_at)"
        " VALUES ('psn', 'NPWR1_00', 'A Game', '2026-10-15T00:00:00')"
    )
    await repo._conn.commit()
    (version,) = await repo.ensure_list_version("psn", "NPWR1_00")  # a stand-in
    await repo.save_title_groups(
        "NPWR1_00",
        [("default", "A Game", 10, None, None), ("001", "The DLC", 5, "Допы", "The DLC")],
    )
    cursor = await repo._conn.execute(
        "SELECT trophy_group_id, name FROM dlcs WHERE version_id = ?", (version,)
    )
    assert [tuple(r) for r in await cursor.fetchall()] == [("001", "The DLC")]


async def test_a_360_list_takes_the_product_its_fission_mark_names(repo: Repo, monkeypatch) -> None:
    from bot.services.store_collect import StoreCollector
    from bot.services.stores import xbox_catalog

    await repo._conn.execute(
        "INSERT INTO achievement_list_connectors (platform, title_id, name, updated_at)"
        " VALUES ('xbox_360', '1297287122', 'Kameo®', '2026-10-15T00:00:00')"
    )
    await repo._conn.commit()
    (stand_in,) = await repo.ensure_list_version("xbox_360", "1297287122")
    asked: list[str] = []

    async def search(name):
        asked.append(name)
        return [{"ProductId": "BV83", "Type": "Game"}, {"ProductId": "OTHER", "Type": "Game"}]

    def product(big_id, group):
        return {
            "ProductId": big_id,
            "ProductType": "Game",
            "Properties": {"ProductGroupName": group},
            "LocalizedProperties": [{"ProductTitle": "Kameo"}],
            "DisplaySkuAvailabilities": [
                {"Sku": {}, "Availabilities": [{"Actions": ["Purchase"]}]}
            ],
        }

    async def products(ids):
        # 1297287122 is 4D5307D2: the mark names our list; the other names none.
        return [product("BV83", "[Fission] Kameo (4D5307D2)"), product("OTHER", "Another")]

    monkeypatch.setattr(xbox_catalog, "search", search)
    monkeypatch.setattr(xbox_catalog, "products", products)
    assert await StoreCollector(repo).x360_by_name("1297287122", force=True)
    assert asked == ["Kameo"]  # the name without its mark
    row = await repo.version_row(stand_in)
    assert (row["product_id"], row["stand_in"], row["console"]) == ("BV83", 0, "360")
    assert await repo.stand_in_lists("xbox_360") == []


async def test_an_xbox_list_read_whole_gives_the_earned_rows_their_group(repo: Repo) -> None:
    await repo._conn.execute("SET session_replication_role = replica")  # no account needed
    await repo._conn.execute(
        "INSERT INTO seen_achievements (xuid, title_id, achievement_id, name, platform,"
        " is_backfill, created_at) VALUES ('x1', '77', '5', 'A', 'xbox_modern', 0, 'now')"
    )
    await repo._conn.commit()
    from bot.db.repo import TitleAchievementRow

    await repo.upsert_title_achievements(
        [
            TitleAchievementRow(
                platform="xbox_modern",
                title_id="77",
                achievement_id="5",
                name_en="A",
                trophy_group_id="non_base",
            )
        ],
        complete=True,
    )
    cursor = await repo._conn.execute("SELECT trophy_group_id FROM seen_achievements")
    assert (await cursor.fetchone())[0] == "non_base"


def test_a_360_list_is_base_up_to_its_release_gamerscore() -> None:
    from bot.services.xbox.models import is_x360_arcade, x360_groups

    # A retail game: 1000 G by id order, then two DLC achievements.
    retail = [("2", 500), ("1", 500), ("10", 25), ("3", 0), ("11", 25)]
    assert x360_groups("1297287449", retail) == {
        "1": "base",
        "2": "base",
        "3": "base",  # 0 G keeps it within the release's 1000
        "10": "non_base",
        "11": "non_base",
    }
    # An Arcade game ("XA…" title id): 200 G.
    assert is_x360_arcade(str(0x584108FB)) and not is_x360_arcade("1297287449")
    arcade = [("1", 100), ("2", 100), ("3", 50)]
    assert x360_groups(str(0x584108FB), arcade) == {"1": "base", "2": "base", "3": "non_base"}
    # Stopping at 200 on the way to 400 is a coincidence: 400.
    both = [("1", 100), ("2", 100), ("3", 200), ("4", 50)]
    assert x360_groups(str(0x584108FB), both)["3"] == "base"
    # A later Arcade game: 400 G, never stopping at 200 on the way.
    later = [("1", 150), ("2", 100), ("3", 150), ("4", 50)]
    assert x360_groups(str(0x584108FB), later) == {
        "1": "base",
        "2": "base",
        "3": "base",
        "4": "non_base",
    }
    # Worth less than its limit: all base.
    assert set(x360_groups("1297287449", [("1", 300), ("2", 200)]).values()) == {"base"}


async def test_a_derived_group_is_marked_so_and_the_platforms_replaces_it(repo: Repo) -> None:
    from bot.db.repo import TitleAchievementRow

    await repo.upsert_title_achievements(
        [
            TitleAchievementRow(
                platform="xbox_360", title_id="1297287449", achievement_id=i, gamerscore=g
            )
            for i, g in (("1", 1000), ("2", 50))
        ],
        complete=True,
    )
    cursor = await repo._conn.execute(
        "SELECT achievement_id, trophy_group_id, group_source FROM title_achievements"
        " ORDER BY achievement_id"
    )
    assert [tuple(r) for r in await cursor.fetchall()] == [
        ("1", "base", "derived"),
        ("2", "non_base", "derived"),
    ]
    # Should Microsoft say it one day, its word replaces ours, and stays.
    await repo.set_achievement_groups("xbox_360", "1297287449", {"2": "base"})
    await repo.derive_x360_groups("1297287449")
    cursor = await repo._conn.execute(
        "SELECT trophy_group_id, group_source FROM title_achievements WHERE achievement_id = '2'"
    )
    assert tuple(await cursor.fetchone()) == ("base", "platform")


async def test_the_last_base_unlock_is_the_mythic_and_the_last_of_all_completes(
    repo: Repo,
) -> None:
    from bot.db.repo import TitleAchievementRow

    await repo._conn.execute("SET session_replication_role = replica")
    await repo.upsert_title_achievements(
        [
            TitleAchievementRow(
                platform="xbox_modern", title_id="9", achievement_id=a, trophy_group_id=g
            )
            for a, g in (("1", "base"), ("2", "base"), ("3", "non_base"))
        ],
        complete=True,
    )

    async def earn(achievement_id: str, at: str) -> None:
        await repo._conn.execute(
            "INSERT INTO seen_achievements (xuid, title_id, achievement_id, name, platform,"
            " is_backfill, unlocked_at, created_at) VALUES ('x', '9', ?, 'A', 'xbox_modern', 0,"
            " ?, ?)",
            (achievement_id, at, at),
        )
        await repo._conn.commit()
        await repo.mark_xbox_completions("xbox_modern", "x", "9")

    async def marks() -> list[tuple]:
        cursor = await repo._conn.execute(
            "SELECT achievement_id, mythic, completes FROM seen_achievements ORDER BY 1"
        )
        return [tuple(r) for r in await cursor.fetchall()]

    await earn("2", "2026-01-01")
    await earn("3", "2026-01-02")
    assert await marks() == [("2", 0, 0), ("3", 0, 0)]
    await earn("1", "2026-01-03")  # the base list is whole, and so is the game
    assert await marks() == [("1", 1, 1), ("2", 0, 0), ("3", 0, 0)]
    await repo.mark_xbox_completions("xbox_modern", "x", "9")  # marked once
    assert await marks() == [("1", 1, 1), ("2", 0, 0), ("3", 0, 0)]
    # A DLC adds an achievement: no longer complete; the Mythic stays.
    await repo.upsert_title_achievements(
        [
            TitleAchievementRow(
                platform="xbox_modern", title_id="9", achievement_id="4", trophy_group_id="non_base"
            )
        ],
        complete=True,
    )
    assert await marks() == [("1", 1, 0), ("2", 0, 0), ("3", 0, 0)]
    await earn("4", "2026-02-01")
    assert await marks() == [("1", 1, 0), ("2", 0, 0), ("3", 0, 0), ("4", 0, 1)]


async def test_a_games_hltb_entry_reaches_its_other_releases(repo: Repo) -> None:
    from bot.services.game_link import spread_hltb
    from bot.services.stores import StoreVersion, hltb_page

    await repo.save_hltb_page(
        hltb_page.parse_page(
            {
                "game": [
                    {
                        "game_id": 5,
                        "game_name": "Motorfest",
                        "game_type": "game",
                        "profile_platform": "PC, PlayStation 4, PlayStation 5",
                    }
                ]
            }
        )  # type: ignore[arg-type]
    )
    ids = [
        await repo.save_version(
            StoreVersion(store=s, product_id=p, console=c, name="Motorfest"),
            platform=None,
            title_id=None,
        )
        for s, p, c in (
            ("steam", "1", "steam"),
            ("psn", "2", "ps4"),
            ("psn", "3", "ps5"),
            ("xbox", "4", "series"),
        )
    ]
    game = await repo.create_game("Motorfest", 2023, ids[0])
    await repo.write_members({v: (game, "version", None, None) for v in ids})
    await repo.link_version_hltb(ids[0], 5, score=1.0)
    assert await spread_hltb(repo, [game]) == 2  # PS4 and PS5; HLTB lists no Series
    linked = {r["version_id"] for r in await repo.versions_of_hltb(5)}
    assert linked == {ids[0], ids[1], ids[2]}
    # Spread because they are one game: never read back as a sign they are.
    hltb = {r["version_id"]: r["hltb_ids"] for r in await repo.match_rows()}
    assert hltb[ids[0]] == "5" and hltb[ids[1]] is None and hltb[ids[2]] is None


def test_a_game_is_not_called_by_an_id_when_a_release_has_a_name() -> None:
    from bot.services.game_match import game_name

    named = Candidate(
        version_id=2, store="psn", product_id="1", console="ps4", names=["DAYS GONE"], year=2019
    )
    unnamed = Candidate(
        version_id=1,
        store="unknown",
        product_id="1881441063",
        console="pc",
        names=["1881441063"],
        year=2018,
    )
    assert game_name([unnamed, named]).lower() == "days gone"


def test_a_name_never_learned_says_nothing_about_a_pair() -> None:
    """An id-named stand-in (the training audit, 2026-10-24): no name signs,
    `name_unknown` instead — never a name 0.8 below the floor."""
    from bot.services.game_link import _candidate

    row = {
        "version_id": 1,
        "store": "unknown",
        "product_id": "1881441063",
        "title_id": "1881441063",
        "console": "pc",
        "platform": "xbox_modern",
        "name": "1881441063",
        "list_name": "1881441063",
        "list_name_en": None,
        "kind": None,
        "developer": None,
        "publisher": None,
        "release_date": None,
        "store_group": None,
        "stand_in": 1,
        "hltb_ids": None,
    }
    unnamed = _candidate(row)
    assert unnamed.names == ()
    f = features(unnamed, _c(2, "Days Gone 2", console="ps4", year=2019))
    assert f.get("name_unknown") == 1.0
    assert not {"name", "numbers_differ", "subtitle"} & set(f)


def test_a_placeholder_date_is_no_year() -> None:
    """Microsoft's 2799-12-31 is no date (2026-10-24: «Marvel vs. Capcom 3
    (2799)»)."""
    from bot.services.game_match import candidate_year

    assert candidate_year({"name": "Marvel vs. Capcom 3", "release_date": "2799-12-31"}) is None
    assert candidate_year({"name": "Halo", "release_date": "2021-11-15"}) == 2021


def test_a_veto_needs_a_sign_the_two_differ() -> None:
    """Only a shared name and a near year, and the model says "other"
    (2026-10-24: Fortnite and Save the World): no veto, so the pairs that
    join them still do. With a sign they differ (a sequel's number), or the
    model's own answer a relation (a remaster), it holds."""
    from bot.services.game_link import _cluster
    from bot.services.game_match import Verdict

    members = [_c(1, "Fortnite"), _c(2, "Fortnite"), _c(3, "Fortnite: Save the World")]

    def verdict(a: int, b: int, p_same: float, signs: set[str]) -> Verdict:
        return Verdict(
            a,
            b,
            "same",
            p_same,
            {"same": p_same, "other": 1 - p_same},
            "linked",
            dict.fromkeys(signs, 1.0),
        )

    def groups(far_signs: set[str], remaster: float = 0.0) -> list[set[int]]:
        far = verdict(1, 3, 0.02, far_signs)
        far.probs = {"same": 0.02, "remaster_of": remaster, "other": 0.98 - remaster}
        verdicts = {
            (1, 2): verdict(1, 2, 0.99, {"name"}),
            (2, 3): verdict(2, 3, 0.95, {"name", "same_hltb"}),
            (1, 3): far,
        }
        return sorted(_cluster(members, verdicts, []), key=min)

    assert groups({"name", "years_near"}) == [{1, 2, 3}]
    # The model sure it is a remaster: another game, whatever the signs.
    assert groups({"name", "years_near"}, remaster=0.9) == [{1, 2}, {3}]
    assert groups({"name", "numbers_differ"}) == [{1, 2}, {3}]


def test_an_enhanced_edition_is_marked_in_its_game() -> None:
    """Owner, 2026-10-24: GOTY, Definitive, a Director's Cut — the game made
    more of — stay in the game, marked `enhanced`, of the plain version; a
    label says so where the name does not."""
    from bot.services.game_link import _roles

    plain = _c(1, "Fallout 3", year=2008)
    goty = _c(2, "Fallout 3: Game of the Year Edition", year=2009)
    port = _c(3, "Fallout 3", console="ps3", year=2008)
    cut = _c(4, "Sonic Adventure", year=2011)
    roles = _roles([plain, goty, port], [])
    assert roles[2] == ("enhanced", 1)
    assert roles[1] == roles[3] == ("version", None)
    told = _roles([plain, cut], [{"version_id": 4, "other_id": 1, "relation": "enhanced_of"}])
    assert told[4] == ("enhanced", 1)


def test_the_models_enhanced_edition_joins_its_game() -> None:
    """Enhanced is a class of the model's own (owner, 2026-10-27): its sure
    answer keeps the two in one game, and marks the edition of the other."""
    from bot.services.game_link import _cluster, _roles
    from bot.services.game_match import Verdict

    plain = _c(1, "Sonic Adventure", year=1999)
    cut = _c(2, "Sonic Adventure DX", year=2003)
    probs = {"same": 0.02, "enhanced_of": 0.97, "other": 0.01}
    v = Verdict(2, 1, "enhanced_of", 0.97, probs, "linked", {"name": 0.9})
    assert v.p_join == 0.99
    assert _cluster([plain, cut], {(1, 2): v}, []) == [{1, 2}]
    assert _roles([plain, cut], [], {(1, 2): v})[2] == ("enhanced", 1)
    # A label says otherwise: the label stands.
    said = [{"version_id": 2, "other_id": 1, "relation": "same"}]
    assert _roles([plain, cut], said, {(1, 2): v})[2] == ("version", None)


def test_a_friends_pass_is_a_part_of_its_game() -> None:
    """A friend's pass (owner, 2026-10-25): a free copy to play the whole
    game with its owner — not a demo, a role in the game all the same."""
    from bot.services.game_link import _roles

    game = _c(1, "It Takes Two", console="ps4", store="psn", year=2021)
    pass_ = _c(2, "It Takes Two - Friend's Pass", console="ps4", store="psn", year=2021)
    assert kind_of(pass_) == "pass"
    assert _linked(game, pass_, "same"), compare(game, pass_).reasons
    assert _roles([game, pass_], [])[2] == ("pass", 1)
    told = _roles([game, pass_], [{"version_id": 2, "other_id": 1, "relation": "pass_of"}])
    assert told[2] == ("pass", 1)


async def test_an_enhanced_edition_sold_beside_the_plain_game_is_a_game_of_its_own(
    repo: Repo,
) -> None:
    """Owner, 2026-10-25: where a store sells both the plain game and its
    enhanced edition, the edition is a game of its own, related to it."""
    plain = await _version(repo, "XBPLAIN", "The Witcher 3: Wild Hunt", "2015")
    goty = await _version(
        repo, "XBGOTY", "The Witcher 3: Wild Hunt - Game of the Year Edition", "2016"
    )
    await repo.save_decision(goty, plain, "enhanced_of", features=None, model=None, decided_by="t")
    await GameLinker(repo).link_versions([plain, goty])
    g_plain, g_goty = await repo.linked_game_of(plain), await repo.linked_game_of(goty)
    assert g_plain != g_goty
    cur = await repo._conn.execute("SELECT game_id, related_id, kind FROM game_relations")
    assert [tuple(r) for r in await cur.fetchall()] == [(g_goty, g_plain, "enhanced_of")]


async def test_an_enhanced_edition_no_store_sells_beside_the_plain_game_stays(
    repo: Repo,
) -> None:
    """Steam sells only the Complete Edition: there it is the game."""
    ps4 = await _version(repo, "PSPLAIN", "Horizon Zero Dawn", "2017", store="psn", console="ps4")
    steam = await _version(
        repo,
        "1151640",
        "Horizon Zero Dawn Complete Edition",
        "2020",
        store="steam",
        console="steam",
    )
    await repo.save_decision(steam, ps4, "enhanced_of", features=None, model=None, decided_by="t")
    await GameLinker(repo).link_versions([ps4, steam])
    assert await repo.linked_game_of(ps4) == await repo.linked_game_of(steam)


def test_a_relation_is_read_from_both_sides() -> None:
    """`subject_of` guesses which side a relation points from; a remaster it
    guessed the wrong way round was read without its word (#218 step 2)."""
    from bot.services.game_match import both_ways, subject_of

    remaster = _c(1, "Foo Remastered", console="ps4", store="psn", year=2018)
    port = _c(2, "Foo", console="ps5", store="psn", year=2021)
    assert subject_of(remaster, port)[0] is port
    weights = {"remaster_of": {"remaster_word": 6.0, "bias": -2.0}, "same": {"bias": -2.0}}
    f = features(port, remaster, ordered=True)
    r = features(remaster, port, ordered=True)
    assert "remaster_word" not in f and "remaster_word" in r
    probs, turned = both_ways(f, r, weights)
    assert turned and max(probs, key=probs.__getitem__) == "remaster_of"
    assert abs(sum(probs.values()) - 1.0) < 1e-9
    verdict = compare(port, remaster, weights)
    assert (verdict.relation, verdict.subject) == ("remaster_of", 1)


def test_numbers_conflict_or_go_missing() -> None:
    """Two numbers that disagree are two games; one on one side only is a
    weaker sign; a platform's number is no number of the game's (#218)."""
    two, three = _c(1, "Halo 2"), _c(2, "Halo 3")
    assert "numbers_differ" in features(two, three)
    assert "number_missing" in features(_c(3, "Halo"), two)
    ps4 = _c(4, "Foo Bar PlayStation 4 Edition", store="psn", console="ps4")
    f = features(ps4, _c(5, "Foo Bar"))
    assert not {"numbers_differ", "number_missing"} & set(f)


def test_the_shape_of_a_pair() -> None:
    """Whose list is known, the words a name adds, the edition's kind and
    what the stores tell apart (#218)."""
    base = _c(1, "Foo Bar", achievements=_list("a", 20), hltb_ids=frozenset({1}))
    goty = _c(
        2,
        "Foo Bar Game of the Year Edition",
        achievements=_list("a", 10),
        hltb_ids=frozenset({2}),
        list_key=("xbox_modern", "2"),
    )
    f = features(goty, base, ordered=True)
    assert f["overlap"] == 1.0 and f["count_ratio"] == 0.5
    assert "word_goty" in f and "hltb_differs" in f
    assert "words_none_added" in f
    heist = _c(3, "Foo Bar: The Heist")
    assert "list_none" in features(heist, _c(4, "Foo Bar"))
    assert "words_added" in features(heist, _c(4, "Foo Bar"), ordered=True)
    assert "no_shared_word" in features(_c(5, "Quux"), _c(6, "Zork"))
