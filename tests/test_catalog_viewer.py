"""The catalog viewer's own helpers (no server is started)."""

from __future__ import annotations

from pathlib import Path

from bot.db.repo import Database, Repo
from scripts.catalog_viewer import _agreeing, load_gemini
from tests.catalog_seed import seed_catalog
from tests.conftest import TEST_SCHEMA


def test_gemini_answers_become_the_decisions_the_picker_posts(tmp_path: Path) -> None:
    (tmp_path / "01.txt").write_text(
        "1|same|-|high|One game.\n"
        "3|remaster_of|first|high|A remaster.\n"
        "4|remake_of|second|medium|The other way.\n"
        "5|not_related|-|high|Nothing in common.\n"
        "garbage line\n",
        encoding="utf-8",
    )
    found = load_gemini(tmp_path)
    assert found[1]["decision"] == "same"
    assert found[3]["decision"] == "remaster_of"
    assert found[4] == {
        "decision": "remake_of:flip",
        "confidence": "medium",
        "why": "The other way.",
    }
    assert found[5]["decision"] == "other"
    assert load_gemini(None) == {}


def test_a_button_names_everybody_who_gave_its_answer() -> None:
    opinions = [("Claude", "same"), ("Gemini", "same"), ("the model", "same")]
    assert _agreeing("same", opinions) == "Claude, Gemini and the model"
    opinions = [("Claude", "same"), ("Gemini", "same"), ("the model", "series")]
    assert _agreeing("same", opinions) == "Claude and Gemini"
    assert _agreeing("series", opinions) == "Model"
    opinions = [("Claude", None), ("Gemini", "other"), ("the model", "other")]
    assert _agreeing("other", opinions) == "Gemini and the model"


def test_a_relation_sentence_bolds_the_relation_and_escapes_the_names() -> None:
    from scripts.catalog_viewer import _relation_sentence

    html = _relation_sentence("remake_of:flip", "A<1>", "B & C")
    assert html == "«B &amp; C» is a <b>remake</b> of «A&lt;1&gt;»"
    plain = _relation_sentence("same", "A<1>", "B", html=False)
    assert plain == "«A<1>» and «B» are one game"


def test_the_microsoft_stores_pc_reads_xbox_pc() -> None:
    from bot.services.stores import console_label
    from scripts.catalog_viewer import _console_sql

    assert console_label("xbox", "pc") == "xbox pc"
    assert console_label("gog", "pc") == "gog pc"
    assert console_label("list", "pc") == "pc (store unknown)"
    assert console_label("steam", "steam") == "steam"
    assert console_label("xbox", "series") == "series"
    assert "'xbox pc'" in _console_sql() and "'pc (store unknown)'" in _console_sql()


def test_a_store_link_says_whether_it_is_sold() -> None:
    from scripts.catalog_viewer import _store_link

    row = {"store": "xbox", "product_id": "BV83SM3191S5", "stand_in": 0, "on_sale": 0}
    link = _store_link(row)  # type: ignore[arg-type]
    assert "xbox.com" in link and "↗" in link and "off sale" in link
    stand_in = {"store": "xbox", "product_id": "1", "stand_in": 1, "on_sale": None}
    assert "no store page" in _store_link(stand_in) and "unknown" in _store_link(stand_in)  # type: ignore[arg-type]


async def test_every_page_of_the_viewer_answers(
    database: Database, repo: Repo, tmp_path: Path, settings, monkeypatch
) -> None:
    """The menu's pages (and a game's and a version's) open on a database
    with one linked game."""
    from aiohttp.test_utils import TestClient, TestServer

    monkeypatch.setattr("bot.config.get_settings", lambda: settings)

    from bot.services.game_link import GameLinker
    from bot.services.stores import StoreVersion
    from scripts.catalog_viewer import PAGES, build

    version = await repo.save_version(
        StoreVersion(store="xbox", product_id="P1", console="series", name="Control"),
        platform=None,
        title_id=None,
    )
    await GameLinker(repo).link_versions([version])
    game = await repo.linked_game_of(version)
    await repo._conn.execute(
        "INSERT INTO achievement_list_connectors (platform, title_id, name, updated_at)"
        " VALUES ('xbox_modern', '77', 'Control', '2026-10-15T00:00:00')"
    )
    await repo._conn.commit()
    await repo.ensure_list_version("xbox_modern", "77")

    app = build(database._dsn, TEST_SCHEMA, data_dir=tmp_path)
    async with TestClient(TestServer(app)) as client:
        for page in (
            *PAGES,
            f"/game/{game}",
            f"/version/{version}",
            "/title/xbox_modern/77",
            "/list/xbox_modern/77",
        ):
            response = await client.get(page)
            assert response.status == 200, page


async def test_the_pages_show_what_hltb_says_of_a_game_a_version_and_a_dlc(
    database: Database, repo: Repo, tmp_path: Path, settings, monkeypatch
) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    from bot.services.stores import StoreDlc, StoreVersion, hltb_page
    from scripts.catalog_viewer import build

    monkeypatch.setattr("bot.config.get_settings", lambda: settings)
    game = await repo.create_game("Control", 2019)
    version = await repo.save_version(
        StoreVersion(store="xbox", product_id="P1", console="series", name="Control"),
        platform=None,
        title_id=None,
    )
    await repo._conn.execute(
        "UPDATE versions SET game_id = ?, role = 'version' WHERE version_id = ?",
        (game, version),
    )
    await repo.save_dlc(version, StoreDlc(store_id="D1", name="The Foundation"))
    cursor = await repo._conn.execute("SELECT dlc_id FROM dlcs WHERE version_id = ?", (version,))
    dlc = int((await cursor.fetchone())[0])
    main = {
        "game": [{"game_id": 10, "game_name": "Control", "game_type": "game", "comp_main": 36000}],
        "platformData": [{"platform": "Xbox Series X/S", "comp_main": 30600, "count_comp": 9}],
    }
    add_on = {
        "game": [
            {
                "game_id": 20,
                "game_name": "Control: The Foundation",
                "game_type": "dlc",
                "game_parent": 10,
                "comp_main": 3600,
            }
        ],
        "platformData": [{"platform": "Xbox Series X/S", "comp_main": 3300, "count_comp": 4}],
    }
    for page in (main, add_on):
        await repo.save_hltb_page(hltb_page.parse_page(page))  # type: ignore[arg-type]
    await repo.link_version_hltb(version, 10, "auto", 0.9)
    await repo.link_dlc_hltb(dlc, 20)

    app = build(database._dsn, TEST_SCHEMA, data_dir=tmp_path)
    async with TestClient(TestServer(app)) as client:
        for page, needle in (
            (f"/game/{game}", "Xbox Series X/S"),
            (f"/version/{version}", "<b>Xbox Series X/S</b>: main 8.5h"),
            (f"/dlc/{dlc}", "<b>Xbox Series X/S</b>: main 0.9h"),
            ("/", "HowLongToBeat (the mirror)"),
            ("/hltb", "Control: The Foundation"),
            ("/hltb?q=foundation&type=dlc&read=yes", "Control: The Foundation"),
            ("/hltb/10", "By platform (HLTB's own row)"),
            ("/hltb/20", "Control"),
        ):
            response = await client.get(page)
            assert response.status == 200, page
            assert needle in await response.text(), page


async def test_every_query_of_the_viewer_runs_on_a_full_catalog(
    database: Database, repo: Repo, tmp_path: Path, settings, monkeypatch
) -> None:
    """A row of every kind, so that no page's query is skipped for want of
    data; what SQLite did by itself (a search ignoring case, NULLs sorted,
    a rounded number) is checked on the way."""
    import json

    from aiohttp.test_utils import TestClient, TestServer

    from scripts.catalog_viewer import PAGES, build

    monkeypatch.setattr("bot.config.get_settings", lambda: settings)
    await seed_catalog(repo._conn)
    proposals = tmp_path / "proposals.json"
    proposals.write_text(
        json.dumps(
            [
                {
                    "game_a": 4,
                    "game_b": 2,
                    "answer": "confirm",
                    "model": "remaster_of",
                    "p": 0.6,
                    "confidence": "high",
                    "why": "because",
                },
                {
                    "game_a": 3,
                    "game_b": 2,
                    "answer": "same",
                    "model": "contains",
                    "p": 0.5,
                    "confidence": "low",
                    "why": "because",
                },
            ]
        ),
        "utf-8",
    )
    advised = tmp_path / "advised.json"
    claude = {"relation": "same", "direction": None, "confidence": "high", "why": "w"}
    advised.write_text(
        json.dumps(
            [
                {"type": "games", "why": "conflict", "game_a": 1, "game_b": 2, "claude": claude},
                {
                    "type": "games",
                    "why": "overruled",
                    "game_a": 1,
                    "game_b": 1,
                    "label": [10, 11, "same"],
                    "first": "f",
                    "second": "s",
                    "claude": claude,
                },
                {
                    "type": "versions",
                    "why": "conflict",
                    "version_id": 12,
                    "game_id": 1,
                    "first": "f",
                    "second": "s",
                    "gemini": claude,
                },
                {"type": "hltb", "why": "conflict", "hltb_id": 100, "first": "f", "second": "s"},
            ]
        ),
        "utf-8",
    )
    trial = tmp_path / "trial"
    (trial / "answers").mkdir(parents=True)
    (trial / "trial.txt").write_text("x\nQUESTIONS (1):\nid: R:1:2\nFIRST\n", "utf-8")
    for name, relation in (("a", "same"), ("b", "series")):
        (trial / "answers" / f"trial_{name}.jsonl").write_text(
            json.dumps({"id": "R:1:2", "relation": relation, "confidence": "high", "why": "w"}),
            "utf-8",
        )
    app = build(database._dsn, TEST_SCHEMA, proposals, None, advised, trial, tmp_path)
    async with TestClient(TestServer(app)) as client:
        pages = [
            *PAGES,
            *(f"/game/{g}" for g in (1, 2, 3, 4, 999)),
            *(f"/version/{v}" for v in (10, 11, 12, 13, 14, 15, 999)),
            "/title/xbox_modern/77",
            "/title/steam/110",
            "/title/nothing/0",
            "/list/xbox_modern/77",
            "/titles?q=control",
            "/versions?q=control",
            "/games?q=control",
            "/dlcs?q=foundation",
            "/dlc/20",
            "/dlc/22",
            "/dlc/23",
            "/dlc/999",
            "/hltb?q=ctrl&type=game&read=yes",
            "/hltb?read=no&page=1",
            "/hltb/100",
            "/hltb/101",
            "/hltb/999",
            "/series?q=control",
            "/series/40",
            "/series/41",
            "/series/999",
            "/review?tab=versions",
            "/review?tab=games",
            "/review?tab=label",
            "/decisions?by=operator",
            "/decisions?by=advisers",
            "/payload?subject=hltb:100&source=hltb_page",
            "/payload?subject=none&source=none",
            "/steam-schema/110",
            "/steam-schema/0",
            "/proposals",
            "/advised",
            "/trial",
        ]
        for page in pages:
            response = await client.get(page)
            assert response.status == 200, page

        async def text(page: str) -> str:
            return await (await client.get(page)).text()

        assert "advisers disagree" in await text("/review?tab=advisers")
        # A search ignores case, as SQLite's LIKE did.
        for page in ("/titles?q=CONTROL", "/versions?q=CONTROL", "/games?q=CONTROL"):
            assert "Control" in await text(page), page
        assert "Control" in await text("/series?q=cONTROL")
        assert "Control: The Foundation" in await text("/dlcs?q=FOUNDATION")
        assert "/hltb/100" in await text("/hltb?q=CTRL")
        # A date nobody knows sorts first, as in SQLite.
        page = await text("/game/1")
        assert page.index('href="/version/11"') < page.index('href="/version/10"')
        # Rounded as a number, not as "0.88000".
        assert "<td>0.88</td>" in page
        # The aggregates read as GROUP_CONCAT's did.
        assert "contains 1,contains 2" in await text("/games")
        assert "PC, Xbox" in page
        assert "Control [game]; The Foundation [dlc]" in page

        # The steps before an action typed by id, and the forms that read first.
        for path, form in (
            ("/game/1/merge", {"into": "2"}),
            ("/game/1/relate", {"related": "2", "kind": "remaster_of"}),
            ("/series/40/merge", {"into": "42"}),
            ("/series/40/member", {"game_id": "2", "ask": "1"}),
            ("/game/1/series", {"series_id": "42"}),
            ("/decide-games", {"game_id": "1", "other_game": "2", "decision": "skip"}),
            ("/decide", {"version_id": "10", "other_id": "11", "decision": "skip"}),
        ):
            response = await client.post(path, data=form)
            assert response.status == 200, path
        assert (
            "was merged into"
            in await (await client.post("/game/2/merge", data={"into": "4"})).text()
        )
        assert (await client.post("/dlc/999/read")).status == 200
        response = await client.post("/game/2/detach", data={"version_id": "12"})
        assert response.status == 200
        response = await client.post("/game/1/detach", data={"version_id": "13"})
        assert response.status == 200


async def test_a_confirmation_names_the_game_behind_an_id(repo: Repo, database: Database) -> None:
    """A merge typed by id asks first, naming what each id is (owner,
    2026-10-24); an id merged away names the game it went into."""
    from bot.db import tools
    from scripts.catalog_viewer import _game_said

    now = "2026-10-24T00:00:00"
    await repo._conn.execute(
        "INSERT INTO games (game_id, name, year, last_year, merged_into, created_at, updated_at)"
        " VALUES (1, 'LEGO Harry Potter <Collection>', 2016, 2018, NULL, ?, ?),"
        " (2, 'Old', 2010, NULL, 1, ?, ?)",
        (now, now, now, now),
    )
    await repo._conn.execute(
        "INSERT INTO versions (version_id, game_id, store, product_id, console, updated_at)"
        " VALUES (1, 1, 'psn', 'a', 'ps4', ?), (2, 1, 'xbox', 'b', 'one', ?)",
        (now, now),
    )
    with tools.connect(database._dsn, schema=TEST_SCHEMA, readonly=True) as conn:
        said = _game_said(conn, 1)
        assert "LEGO Harry Potter &lt;Collection&gt;" in said
        assert "(2016–2018)" in said and "2 versions: one, ps4" in said
        assert "game 2 was merged into" in _game_said(conn, 2)
        assert "no such game" in _game_said(conn, 99)


def test_the_label_queue_offers_every_rare_relation_in_one_tap() -> None:
    from scripts.catalog_viewer import RARE_RELATIONS, _label_picker

    html = _label_picker(1, 2, "/review?tab=label")
    for relation in RARE_RELATIONS:
        assert f'value="{relation}"' in html


def test_another_game_of_the_series_is_one_tap_naming_it() -> None:
    """Owner, 2026-10-24: a frequent answer — a button per series, and a
    field to name one when the games are in none."""
    from scripts.catalog_viewer import _decision_picker, _label_picker

    html = _label_picker(1, 2, "/review?tab=label", [(7, "Hello Neighbor")])
    assert 'value="series#7"' in html and "(<b>Hello Neighbor</b>)" in html
    assert 'value="series#new"' in html and "another?" in html
    bare = _decision_picker(1, 2, "/review")
    assert "series#" in bare and "which?" in bare and 'value="series"' not in bare


def test_the_label_queue_can_say_a_demo() -> None:
    from scripts.catalog_viewer import _label_picker

    html = _label_picker(1, 2, "/review?tab=label")
    for key in ("demo_of", "demo_of:flip", "tool_of", "mode_of", "extra_of"):
        assert f'value="{key}"' in html


async def test_pairs_asked_for_by_hand_come_first_until_answered(
    repo: Repo, database: Database
) -> None:
    from bot.db import tools
    from scripts.catalog_viewer import ASKED, label_queue

    now = "2026-10-24T00:00:00"
    for version in (3, 4, 5, 6):
        await repo._conn.execute(
            "INSERT INTO versions (version_id, store, product_id, console, updated_at)"
            " VALUES (?, 'steam', ?, 'steam', ?)",
            (version, str(version), now),
        )
    await repo._conn.execute(
        "INSERT INTO match_pairs (version_id, other_id, relation, p, probs, features, model,"
        " scored_at) VALUES (5, 6, 'remake_of', 0.5, '{\"remake_of\": 0.5}', '{}', 'm', ?)",
        (now,),
    )
    await repo._conn.execute(
        "INSERT INTO match_decisions (version_id, other_id, relation, decided_by, decided_at)"
        " VALUES (4, 3, 'same', 'viewer', ?)",
        (now,),
    )
    row = {"relation": "same", "p": 0.9, "probs": "{}", "features": "{}"}
    requested = [
        {**row, "subject": 1, "other": 2},
        {**row, "subject": 2, "other": 1},  # the same pair again
        {**row, "subject": 3, "other": 4},  # answered already
    ]
    with tools.connect(database._dsn, schema=TEST_SCHEMA, readonly=True) as conn:
        queue, _, _ = label_queue(conn, frozenset(), requested)
    assert [(r["subject"], kind) for r, kind in queue] == [(1, ASKED), (5, "remake_of")]
