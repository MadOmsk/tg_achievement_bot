"""An HLTB page read into entries (#147): a game's page, a DLC's page, and
which of them may say what about whom — no network."""

from __future__ import annotations

import json

from bot.db.repo import Repo
from bot.services.stores import hltb_page


def _page(game_id: int, name: str, kind: str, parent: int = 0, related=(), main=36000) -> dict:
    return {
        "game": [
            {
                "game_id": game_id,
                "game_name": name,
                "game_type": kind,
                "game_parent": parent,
                "comp_main": main,
                "comp_main_avg": main,
            }
        ],
        "relationships": [
            {"game_id": i, "game_name": n, "game_type": t, "comp_main": 7200} for i, n, t in related
        ],
    }


GAME = _page(2127, "Cyberpunk 2077", "game", related=[(113203, "Phantom Liberty", "dlc")])
DLC = _page(
    113203,
    "Cyberpunk 2077: Phantom Liberty",
    "dlc",
    parent=2127,
    related=[(2127, "Cyberpunk 2077", "game")],
    main=72000,
)


def test_a_dlc_pages_own_game_is_its_parent_not_its_child() -> None:
    entry = hltb_page.parse_page(DLC)
    assert entry is not None
    assert entry.parent_hltb_id == 2127
    assert entry.parent is not None and entry.parent.hltb_id == 2127
    assert entry.children == []
    game = hltb_page.parse_page(GAME)
    assert game is not None and [c.hltb_id for c in game.children] == [113203]
    assert game.children[0].parent_hltb_id == 2127


async def _row(repo: Repo, hltb_id: int) -> dict:
    cursor = await repo._conn.execute(
        "SELECT game_type, parent_hltb_id, times, page_read_at FROM hltb_games WHERE hltb_id = ?",
        (hltb_id,),
    )
    return dict(await cursor.fetchone())


async def test_a_games_own_times_are_never_another_pages_averages(repo: Repo) -> None:
    await repo.save_hltb_game(hltb_page.parse_page(GAME))  # type: ignore[arg-type]
    own = await _row(repo, 2127)
    await repo.save_hltb_game(hltb_page.parse_page(DLC))  # type: ignore[arg-type]
    game, dlc = await _row(repo, 2127), await _row(repo, 113203)
    assert game["times"] == own["times"] and game["parent_hltb_id"] is None
    assert game["game_type"] == "game"
    assert (dlc["game_type"], dlc["parent_hltb_id"]) == ("dlc", 2127)
    assert dlc["page_read_at"] is not None
    assert json.loads(dlc["times"])  # its own page's times, not the game page's averages


async def test_a_game_once_taken_for_its_dlcs_child_is_put_right(repo: Repo) -> None:
    """The old reading stored Cyberpunk 2077 as Phantom Liberty's child;
    reading the DLC's page again (its own page never read) undoes it."""
    await repo._conn.execute(
        "INSERT INTO hltb_games (hltb_id, name, game_type, parent_hltb_id, times, checked_at)"
        " VALUES (2127, 'Cyberpunk 2077', 'game', 113203, '{}', '2026-10-01')"
    )
    await repo.save_hltb_game(hltb_page.parse_page(DLC))  # type: ignore[arg-type]
    assert (await _row(repo, 2127))["parent_hltb_id"] is None
