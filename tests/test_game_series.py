"""Game series (#147; owner, 2026-10-12): proposals from relations, labels
and franchise names; crossovers in two series without merging them; the
operator's and the advisers' word kept over every rebuild."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.services.game_series import (
    ADVISERS_P,
    PREFIX_P,
    SeriesBuilder,
    SeriesGame,
    answer_series_question,
    evidence,
    franchise_key,
    propose,
    series_name,
    series_questions,
)
from tests.conftest import TEST_SCHEMA


def _games(*rows: tuple) -> dict[int, SeriesGame]:
    return {r[0]: SeriesGame(*r) for r in rows}


def _series(games: dict[int, SeriesGame], relations=(), labels=()) -> dict[str, set[int]]:
    found = propose(games, evidence(games, list(relations), list(labels)))
    return {p.name: set(p.members) for p in found}


def test_a_franchise_is_the_name_before_a_subtitle_or_a_number() -> None:
    assert franchise_key("Halo 3") == "halo"
    assert franchise_key("Halo: Reach") == "halo"
    assert franchise_key("The Elder Scrolls V: Skyrim Special Edition") == "elder scrolls"
    assert franchise_key("Assassin's Creed® II") == "assassins creed"
    assert franchise_key("Gears 5") == "gears"
    assert franchise_key("Sonic Frontiers PS4 & PS5") == "sonic frontiers"
    assert franchise_key("1942") == "1942"


def test_a_shared_franchise_suggests_a_series_only_with_one_studio_or_publisher() -> None:
    games = _games(
        (1, "Halo 3", 2007, "Bungie", "Microsoft"),
        (2, "Halo: Reach", 2010, "Bungie", "Microsoft"),
        (3, "Halo Wars", 2009, "Ensemble", "Microsoft"),
        (4, "Portal", 2007, "Valve", "Valve"),
        (5, "Portal Knights", 2016, "Keen Games", "505 Games"),
    )
    found = propose(games, evidence(games, [], []))
    assert [(p.name, sorted(p.members)) for p in found] == [("Halo", [1, 2, 3])]
    assert {p for p, _ in found[0].members.values()} == {PREFIX_P}


def test_a_remaster_and_a_compilation_are_in_their_originals_series() -> None:
    games = _games(
        (1, "Gears of War", 2006, "Epic", "Microsoft"),
        (2, "Gears of War: Ultimate Edition", 2015, "The Coalition", "Microsoft"),
        (3, "Gears 5", 2019, "The Coalition", "Xbox Game Studios"),
        (4, "Gears of War 2", 2008, "Epic", "Microsoft"),
        (5, "Mass Effect", 2007, "BioWare", "Microsoft"),
        (6, "Mass Effect Legendary Edition", 2021, "BioWare", "EA"),
    )
    series = _series(
        games,
        relations=[(2, 1, "remake_of"), (6, 5, "contains")],
        labels=[(3, 1, "viewer")],
    )
    assert series == {"Gears of War": {1, 2, 3, 4}, "Mass Effect": {5, 6}}


def test_a_crossover_is_in_both_series_and_never_merges_them() -> None:
    games = _games(
        (1, "Street Fighter IV", 2008, "Capcom", "Capcom"),
        (2, "Street Fighter V", 2016, "Capcom", "Capcom"),
        (3, "Street Fighter X Tekken", 2012, "Capcom", "Capcom"),
        (4, "Tekken 6", 2009, "Bandai Namco", "Bandai Namco"),
        (5, "Tekken 7", 2015, "Bandai Namco", "Bandai Namco"),
    )
    series = _series(games, labels=[(3, 5, "viewer")])
    assert series == {"Street Fighter": {1, 2, 3}, "Tekken": {4, 5, 3}}


def test_a_compilation_of_several_series_joins_none_of_them() -> None:
    games = _games(
        (1, "Rare Replay", 2015, "Rare", "Microsoft"),
        (2, "Banjo-Kazooie", 1998, "Rare", "Nintendo"),
        (3, "Banjo-Tooie", 2000, "Rare", "Nintendo"),
        (4, "Perfect Dark", 2000, "Rare", "Nintendo"),
        (5, "Perfect Dark Zero", 2005, "Rare", "Microsoft"),
    )
    series = _series(
        games, relations=[(1, 2, "contains"), (1, 4, "contains")], labels=[(2, 3, "viewer")]
    )
    assert series["Banjo"] == {2, 3, 1}
    assert series["Perfect Dark"] == {4, 5, 1}


def test_a_lone_game_of_another_name_joins_the_series_its_label_names() -> None:
    games = _games(
        (1, "Final Fantasy VII", 1997, "Square", "Square"),
        (2, "Final Fantasy X", 2001, "Square", "Square"),
        (3, "Crisis Core", 2007, "Square Enix", "Square Enix"),
        (4, "Shadow of the Tomb Raider", 2018, "Eidos", "Square Enix"),
        (5, "Tomb Raider", 2013, "Crystal Dynamics", "Square Enix"),
        (6, "Rise of the Tomb Raider", 2015, "Crystal Dynamics", "Square Enix"),
    )
    series = _series(games, labels=[(3, 1, "viewer"), (4, 5, "claude+gemini"), (6, 5, "viewer")])
    assert series == {"Final Fantasy": {1, 2, 3}, "Tomb Raider": {4, 5, 6}}


def test_a_series_is_named_as_its_games_write_their_franchise() -> None:
    def named(*names: str) -> str:
        return series_name([SeriesGame(i, n, 2000 + i) for i, n in enumerate(names)])

    assert named("Gears of War", "Gears of War 2", "Gears 5") == "Gears of War"
    assert named("Sonic Mania", "SONIC GENERATIONS", "Sonic Frontiers") == "Sonic"
    assert named("Cities: Skylines", "Cities: Skylines II") == "Cities: Skylines"
    assert named("The Elder Scrolls V: Skyrim", "The Elder Scrolls IV") == "The Elder Scrolls"
    assert named("resident evil 4", "Resident Evil 5", "Resident Evil 6") == "Resident Evil"


async def _game(repo: Repo, name: str, year: int, developer: str = "Studio") -> int:
    game = await repo.create_game(name, year)
    await repo._conn.execute(
        "UPDATE games SET developer = ?, publisher = ? WHERE game_id = ?",
        (developer, developer, game),
    )
    # A live game has a version.
    cur = await repo._conn.execute(
        "INSERT INTO versions (store, product_id, console, name, updated_at)"
        " VALUES ('steam', ?, 'steam', ?, 'now') RETURNING version_id",
        (f"p{game}", name),
    )
    version = int((await cur.fetchone())[0])
    await repo.write_members({version: (game, "version", None, None)})
    return game


async def _members(repo: Repo) -> dict[str, set[int]]:
    cur = await repo._conn.execute(
        "SELECT s.name, gs.game_id FROM game_series gs JOIN series s USING (series_id)"
        " WHERE gs.member = 1 AND s.merged_into IS NULL"
    )
    found: dict[str, set[int]] = {}
    for name, game in await cur.fetchall():
        found.setdefault(name, set()).add(game)
    return found


async def _series_id(repo: Repo, name: str) -> int:
    cur = await repo._conn.execute(
        "SELECT series_id FROM series WHERE name = ? AND merged_into IS NULL", (name,)
    )
    return int((await cur.fetchone())[0])


async def test_proposals_keep_their_ids_and_the_operators_word(repo: Repo) -> None:
    h3 = await _game(repo, "Halo 3", 2007)
    reach = await _game(repo, "Halo: Reach", 2010)
    odst = await _game(repo, "Halo 3: ODST", 2009)
    builder = SeriesBuilder(repo)
    assert await builder.rebuild() == 1
    halo = await _series_id(repo, "Halo")
    assert await _members(repo) == {"Halo": {h3, reach, odst}}

    # The operator takes ODST out and renames the series: a rebuild keeps both.
    await repo.set_series_member(odst, halo, False)
    await repo.rename_series(halo, "Halo saga", None)
    await builder.rebuild()
    assert await _members(repo) == {"Halo saga": {h3, reach}}
    assert await _series_id(repo, "Halo saga") == halo

    # A new game of the series joins the same series.
    h4 = await _game(repo, "Halo 4", 2012)
    await builder.rebuild()
    assert await _members(repo) == {"Halo saga": {h3, reach, h4}}


async def test_a_merge_by_hand_stands_and_advisers_answer_the_unsure(repo: Repo) -> None:
    fc = await _game(repo, "Far Cry", 2004)
    fc2 = await _game(repo, "Far Cry 2", 2008)
    primal = await _game(repo, "Primal Hunt", 2016)
    primal2 = await _game(repo, "Primal Hunt 2", 2018)
    builder = SeriesBuilder(repo)
    await builder.rebuild()
    far_cry, other = await _series_id(repo, "Far Cry"), await _series_id(repo, "Primal Hunt")
    await repo.merge_series(other, far_cry)
    await builder.rebuild()
    assert await _members(repo) == {"Far Cry": {fc, fc2, primal, primal2}}

    questions = await series_questions(repo)
    assert {(q.game_id, q.series_id) for q in questions} == {
        (g, far_cry) for g in (fc, fc2, primal, primal2)
    }
    assert all(q.p == PREFIX_P and q.others for q in questions)
    await answer_series_question(repo, primal, far_cry, False, "claude+gemini")
    # The advisers' word does not override the operator's.
    await repo.set_series_member(fc, far_cry, True)
    await answer_series_question(repo, fc, far_cry, False, "claude+gemini")
    await builder.rebuild()
    assert await _members(repo) == {"Far Cry": {fc, fc2, primal2}}
    assert {q.game_id for q in await series_questions(repo)} == {fc2, primal2}
    assert ADVISERS_P < 1


async def test_a_label_between_two_games_proposes_their_series(repo: Repo) -> None:
    from bot.services.game_link import GameLinker
    from bot.services.stores import StoreVersion

    async def version(product: str, name: str, developer: str) -> int:
        return await repo.save_version(
            StoreVersion(
                store="steam",
                product_id=product,
                console="steam",
                name=name,
                kind="game",
                developer=developer,
                publisher=developer,
                release_date="2010-01-01",
            ),
            platform=None,
            title_id=None,
        )

    mania = await version("1", "Sonic Mania", "Headcannon")
    gens = await version("2", "Sonic Generations", "Sonic Team")
    await repo.save_decision(mania, gens, "series", features=None, model=None, decided_by="viewer")
    await GameLinker(repo).link_versions([mania, gens])  # the linker proposes the series too
    games = {await repo.linked_game_of(mania), await repo.linked_game_of(gens)}
    assert len(games) == 2
    assert await _members(repo) == {"Sonic": games}


async def test_the_viewer_shows_and_edits_series(repo: Repo, database, tmp_path) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    from scripts.catalog_viewer import build

    h3 = await _game(repo, "Halo 3", 2007)
    reach = await _game(repo, "Halo: Reach", 2010)
    await SeriesBuilder(repo).rebuild()
    halo = await _series_id(repo, "Halo")
    app = build(database._dsn, TEST_SCHEMA, data_dir=tmp_path)
    app.on_startup.clear()
    app.on_cleanup.clear()
    app["repo"] = repo
    async with TestClient(TestServer(app)) as client:
        page = await (await client.get("/series")).text()
        assert "Halo" in page and "1 series, 2 memberships" in page
        page = await (await client.get(f"/series/{halo}")).text()
        assert "Halo: Reach" in page and "name «halo»" in page
        assert "Series" in await (await client.get(f"/game/{h3}")).text()
        await client.post(f"/series/{halo}/member", data={"game_id": str(reach), "member": "0"})
        await client.post(f"/game/{reach}/series", data={"name": "Bungie shooters"})
        await client.post(f"/series/{halo}/rename", data={"name": "Halo saga"})
        await client.post("/series/rebuild")
    assert await _members(repo) == {"Halo saga": {h3}, "Bungie shooters": {reach}}


# ------------------------------------------------- series a rule names (owner, 2026-10-14)


def _with_umbrellas(games: dict[int, SeriesGame]) -> dict[str, set[int]]:
    from bot.services.game_series import umbrellas

    found = propose(games, evidence(games, [], []))
    return {p.name: set(p.members) for p in [*found, *umbrellas(games, found)]}


def test_every_lego_game_is_in_lego_and_in_its_licences_series() -> None:
    games = _games(
        (1, "LEGO Star Wars: The Complete Saga", 2007, "Traveller's Tales", "LucasArts"),
        (2, "LEGO® Marvel's Avengers", 2016, "Traveller's Tales", "Warner Bros."),
        (3, "LEGO Star Wars: The Skywalker Saga", 2022, "Traveller's Tales", "Warner Bros."),
        (4, "Star Wars: Battlefront", 2004, "Pandemic", "LucasArts"),
        (5, "Star Wars Jedi: Fallen Order", 2019, "Respawn", "Electronic Arts"),
    )
    series = _with_umbrellas(games)
    assert series["LEGO"] == {1, 2, 3}
    star_wars = next(
        m for name, m in series.items() if name.lower().startswith("star wars") and 4 in m
    )
    assert {1, 3, 4} <= star_wars  # "LEGO Star Wars" is a Star Wars game too
    assert 2 not in star_wars  # a LEGO game alone says nothing of another licence


def test_a_franchise_has_local_series_two_of_its_games_share() -> None:
    games = _games(
        (1, "Call of Duty 4: Modern Warfare", 2007, "Infinity Ward", "Activision"),
        (2, "Call of Duty: Modern Warfare 2", 2009, "Infinity Ward", "Activision"),
        (3, "Call of Duty: Modern Warfare 3", 2011, "Infinity Ward", "Activision"),
        (4, "Call of Duty: Black Ops", 2010, "Treyarch", "Activision"),
        (5, "Call of Duty: Black Ops II", 2012, "Treyarch", "Activision"),
        (6, "Call of Duty: Ghosts", 2013, "Infinity Ward", "Activision"),
    )
    series = _with_umbrellas(games)
    assert series["Call of Duty"] == {1, 2, 3, 4, 5, 6}
    assert series["Modern Warfare"] == {1, 2, 3}
    assert series["Black Ops"] == {4, 5}
    assert "Ghosts" not in series  # one game is no series


def test_a_longer_franchise_name_two_games_share_is_a_series_inside() -> None:
    games = _games(
        (1, "Star Wars: Battlefront", 2004, "Pandemic", "LucasArts"),
        (2, "Star Wars: Knights of the Old Republic", 2003, "BioWare", "LucasArts"),
        (3, "Star Wars Jedi: Fallen Order", 2019, "Respawn", "Electronic Arts"),
        (4, "Star Wars Jedi: Survivor", 2023, "Respawn", "Electronic Arts"),
        (5, "Star Wars: The Force Unleashed", 2008, "LucasArts", "LucasArts"),
    )
    series = _with_umbrellas(games)
    assert series["Star Wars Jedi"] == {3, 4}
    assert {1, 2, 3, 4, 5} <= series["Star Wars"]


async def test_a_series_a_rule_names_is_kept_by_its_key_and_never_merged(repo: Repo) -> None:
    async def game(name: str, year: int, studio: str = "TT") -> int:
        game_id = await repo.create_game(name, year)
        await repo._conn.execute(
            "UPDATE games SET developer = ?, publisher = ?, kind = 'game' WHERE game_id = ?",
            (studio, studio, game_id),
        )
        await repo._conn.commit()
        return game_id

    a = await game("LEGO Star Wars: The Complete Saga", 2007)
    b = await game("LEGO Batman: The Videogame", 2008)
    c = await game("Star Wars: Battlefront", 2004, "Pandemic")
    for g, v in ((a, 1), (b, 2), (c, 3)):
        await repo._conn.execute(
            "INSERT INTO versions (store, product_id, console, name, kind, updated_at, game_id,"
            " role) VALUES ('steam', ?, 'steam', 'x', 'game', 'x', ?, 'version')",
            (str(v), g),
        )
    await repo._conn.commit()

    await SeriesBuilder(repo).rebuild()
    await SeriesBuilder(repo).rebuild()  # again: the same series, not new ones

    cursor = await repo._conn.execute(
        "SELECT s.name, s.rule_key, s.anchor_game_id, string_agg(gs.game_id::text, ',') FROM"
        " series s"
        " JOIN game_series gs ON gs.series_id = s.series_id WHERE s.rule_key IS NOT NULL"
        " GROUP BY s.series_id"
    )
    rows = [tuple(r) for r in await cursor.fetchall()]
    assert [(r[0], r[1], r[2]) for r in rows] == [("LEGO", "lego", None)]
    assert sorted(rows[0][3].split(",")) == sorted([str(a), str(b)])
    cursor = await repo._conn.execute("SELECT COUNT(*) FROM series WHERE rule_key = 'lego'")
    assert (await cursor.fetchone())[0] == 1


def test_a_lego_game_is_of_its_licence_whoever_made_the_other_games() -> None:
    games = _games(
        (1, "LEGO Star Wars: The Complete Saga", 2007, "Traveller's Tales", "LucasArts"),
        (2, "Star Wars: Battlefront", 2004, "Pandemic", "Activision"),
        (3, "Star Wars Jedi: Fallen Order", 2019, "Respawn", "Electronic Arts"),
        (4, "LEGO Worlds", 2017, "Traveller's Tales", "Warner Bros."),
        (5, "Worlds Adrift", 2018, "Bossa", "Bossa"),
    )
    series = _with_umbrellas(games)
    star_wars = next(m for name, m in series.items() if name.lower() == "star wars")
    assert {1, 2, 3} <= star_wars  # no studio or publisher in common
    # "Worlds" is not "Worlds Adrift": one word is no licence of two.
    assert not any(4 in m and 5 in m for m in series.values())


def test_a_sure_label_between_two_series_never_chains_them() -> None:
    """LEGO Batman 3 and Dark Forces ended in one series (owner, 2026-10-24):
    a label "another of the series" between one game of each of two series
    makes a crossover, never one series of both."""
    games = _games(
        (1, "Halo 3", 2007, "Bungie", "Microsoft"),
        (2, "Halo Reach", 2010, "Bungie", "Microsoft"),
        (3, "Gears of War 2", 2008, "Epic", "Microsoft"),
        (4, "Gears of War 3", 2011, "Epic", "Microsoft"),
    )
    series = _series(games, labels=[(2, 3, "viewer")])
    assert series == {"Halo": {1, 2, 3}, "Gears of War": {3, 4, 2}}


async def test_one_series_answered_in_the_review_says_which(repo: Repo, database, tmp_path) -> None:
    """ "Another of the series" names the series (owner, 2026-10-24): the
    answer is the label, and both games are put in that series by hand — an
    existing one by id, or one typed by name. A label relinks, so the games
    are named here, not counted by id."""
    from aiohttp.test_utils import TestClient, TestServer

    from scripts.catalog_viewer import build

    await _game(repo, "Halo 3", 2007)
    await _game(repo, "Halo: Reach", 2010)
    await _game(repo, "Gears of War", 2006, developer="Epic")
    await SeriesBuilder(repo).rebuild()
    halo = await _series_id(repo, "Halo")

    async def game(name: str) -> str:
        cur = await repo._conn.execute("SELECT game_id FROM games WHERE name = ?", (name,))
        return str((await cur.fetchone())[0])

    app = build(database._dsn, TEST_SCHEMA, data_dir=tmp_path)
    app.on_startup.clear()
    app.on_cleanup.clear()
    app["repo"] = repo
    async with TestClient(TestServer(app)) as client:
        await client.post(
            "/decide-games",
            data={
                "game_id": await game("Halo 3"),
                "other_game": await game("Halo: Reach"),
                "decision": f"series#{halo}",
            },
        )
        await client.post(
            "/decide-games",
            data={
                "game_id": await game("Halo: Reach"),
                "other_game": await game("Gears of War"),
                "decision": "series#new",
                # Several by commas (owner, 2026-10-24); "Halo" is ours.
                "series_name": "Xbox shooters, Halo ,Xbox shooters",
            },
        )
    cur = await repo._conn.execute(
        "SELECT s.name, g.name FROM game_series gs JOIN series s USING (series_id)"
        " JOIN games g ON g.game_id = gs.game_id"
        " WHERE gs.member = 1 AND gs.source <> 'auto' AND s.merged_into IS NULL"
    )
    assert {(r[0], r[1]) for r in await cur.fetchall()} == {
        ("Halo", "Halo 3"),
        ("Halo", "Halo: Reach"),
        ("Xbox shooters", "Halo: Reach"),
        ("Xbox shooters", "Gears of War"),
        ("Halo", "Gears of War"),
    }


def test_a_game_labelled_with_many_of_other_names_joins_none_of_them() -> None:
    """The training audit (2026-10-24): LEGO Harry Potter Collection, labelled
    "of the series" with LEGO games of other licences (meaning LEGO), made a
    "Harry Potter" series of them. A label naming no series, between names of
    different franchises, joins only a lone game with one way in."""
    games = _games(
        (1, "Wizard Collection", 2016, "Studio A", "Pub A"),
        (2, "Space Heroes", 2013, "Studio B", "Pub B"),
        (3, "Bat Gotham", 2014, "Studio C", "Pub C"),
        (4, "Dino World", 2015, "Studio D", "Pub D"),
    )
    labels = [(1, 2, "viewer"), (1, 3, "viewer"), (1, 4, "viewer")]
    assert _series(games, labels=labels) == {}


def test_two_lego_games_of_other_licences_labelled_one_series_are_lego_only() -> None:
    games = _games(
        (1, "LEGO Harry Potter", 2010, "TT", "WB"),
        (2, "LEGO Harry Potter: Years 5-7", 2011, "TT", "WB"),
        (3, "LEGO Harry Potter Collection", 2016, "TT", "WB"),
        (4, "The LEGO Movie 2 Videogame", 2019, "TT", "WB"),
    )
    series = _series(games, relations=[(3, 1, "contains")], labels=[(4, 3, "viewer")])
    assert 4 not in series.get("Harry Potter", set())


def test_a_label_inside_one_name_family_still_joins() -> None:
    games = _games(
        (1, "NBA 2K14", 2013, "Visual Concepts", "2K"),
        (2, "NBA 2K15", 2014, "Visual Concepts", "2K"),
        (3, "NBA 2K16", 2015, "Visual Concepts", "2K"),
        (4, "NBA 2K11", 2010, "Visual Concepts", "2K"),
    )
    labels = [(2, 1, "viewer"), (2, 3, "viewer"), (3, 1, "viewer"), (4, 1, "viewer")]
    assert {1, 2, 3, 4} <= set().union(*_series(games, labels=labels).values())
