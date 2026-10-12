"""HLTB entries checked against our versions, and HLTB's DLC put on our DLC
inside the game they belong to (#147; owner, 2026-10-12) — no network."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.services.hltb_match import entry_fits_version, match_dlc_entries
from bot.services.store_collect import link_hltb_entry
from bot.services.stores import StoreDlc, hltb_page, steam_store


def test_a_dlc_entry_never_stands_for_a_base_game() -> None:
    def fits(**kw: object) -> bool:
        args = {
            "game_type": "game",
            "steam_appids": set(),
            "entry_year": 2015,
            "version_store": "xbox",
            "version_product": "X",
            "version_kind": "game",
            "version_year": 2015,
        }
        return entry_fits_version(**{**args, **kw})  # type: ignore[arg-type]

    assert fits()
    assert not fits(game_type="dlc")
    assert not fits(version_store="steam", version_product="1", steam_appids={2})
    assert fits(version_store="steam", version_product="2", steam_appids={2, 3})
    assert not fits(version_year=2005, entry_year=2023)  # the entry is the remake
    assert fits(version_year=2024)  # a port years later is still it


def test_dlc_entries_are_matched_inside_their_game_only() -> None:
    children = [
        (1, "Hearts of Stone", None),
        (2, "The Witcher 3: Wild Hunt - Blood and Wine", 378648),
        (3, "Expansion Pass", None),
        (4, "Expansion Pass", None),
    ]
    dlcs = [
        (10, "steam", "378648", "The Witcher 3: Wild Hunt - Blood and Wine"),
        (11, "xbox", "HOS", "The Witcher 3: Wild Hunt – Hearts of Stone"),
        (12, "xbox", "HOS2", "The Witcher 3: Wild Hunt - Hearts of Stone"),  # another product
        (13, "xbox", "PASS", "Expansion Pass"),  # two entries share the name
        (14, "psn", "HOS-PS", "Hearts of Stone"),
    ]
    found = match_dlc_entries(children, dlcs, ["The Witcher 3: Wild Hunt"])
    assert found == {10: 2, 14: 1}


async def test_a_games_dlc_entries_are_linked_to_its_dlc(repo: Repo) -> None:
    version = steam_store.parse_app(
        {"type": "game", "name": "Cyberpunk 2077", "steam_appid": 1091500}
    )
    vid = await repo.save_version(version, platform=None, title_id=None)
    await repo.save_dlc(vid, StoreDlc(store_id="2138330", name="Cyberpunk 2077: Phantom Liberty"))
    page = {
        "game": [{"game_id": 2127, "game_name": "Cyberpunk 2077", "game_type": "game"}],
        "relationships": [{"game_id": 113203, "game_name": "Phantom Liberty", "game_type": "dlc"}],
    }
    await repo.save_hltb_game(hltb_page.parse_page(page))  # type: ignore[arg-type]
    await repo.save_payload("hltb:2127", "hltb_page", page)
    await repo.link_version_hltb(vid, 2127)
    await link_hltb_entry(repo, 2127)
    cursor = await repo._conn.execute("SELECT hltb_id, source FROM dlc_hltb")
    assert [tuple(r) for r in await cursor.fetchall()] == [(113203, "auto")]
    # The entry turns out to be a DLC's: no base game keeps it.
    await repo._conn.execute("UPDATE hltb_games SET game_type = 'dlc' WHERE hltb_id = 2127")
    await link_hltb_entry(repo, 2127)
    cursor = await repo._conn.execute("SELECT COUNT(*) FROM version_hltb")
    assert (await cursor.fetchone())[0] == 0
