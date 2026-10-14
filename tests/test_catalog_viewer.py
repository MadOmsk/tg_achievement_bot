"""The catalog viewer's own helpers (no server is started)."""

from __future__ import annotations

from pathlib import Path

from scripts.catalog_viewer import _agreeing, load_gemini


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
    assert "xbox.com" in link and "↗" in link and "снято с продажи" in link
    stand_in = {"store": "xbox", "product_id": "1", "stand_in": 1, "on_sale": None}
    assert "no store page" in _store_link(stand_in) and "неизвестно" in _store_link(stand_in)  # type: ignore[arg-type]


async def test_every_page_of_the_viewer_answers(tmp_path: Path, settings, monkeypatch) -> None:
    """The menu's pages (and a game's and a version's) open on a database
    with one linked game."""
    from aiohttp.test_utils import TestClient, TestServer

    monkeypatch.setattr("bot.config.get_settings", lambda: settings)

    from bot.db.repo import Database, Repo
    from bot.services.game_link import GameLinker
    from bot.services.stores import StoreVersion
    from scripts.catalog_viewer import PAGES, build

    path = tmp_path / "games.db"
    database = await Database(path).connect()
    try:
        repo = Repo(database)
        version = await repo.save_version(
            StoreVersion(store="xbox", product_id="P1", console="series", name="Control"),
            platform=None,
            title_id=None,
        )
        await GameLinker(repo).link_versions([version])
        game = await repo.linked_game_of(version)
    finally:
        await database.close()

    async with TestClient(TestServer(build(path))) as client:
        for page in (*PAGES, f"/game/{game}", f"/version/{version}"):
            response = await client.get(page)
            assert response.status == 200, page
