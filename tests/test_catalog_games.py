"""The Mini App shows a game as the catalog has it (owner, 2026-10-30)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bot.db.repo import Repo
from bot.services import game_page
from bot.services.stores import StoreVersion
from bot.web.mini_chat import month_games


async def _game_of_two_lists(repo: Repo) -> int:
    for store, product, console, platform, title_id in (
        ("xbox", "P1", "series", "xbox_modern", "100"),
        ("steam", "200", "steam", "steam", "200"),
    ):
        await repo.save_version(
            StoreVersion(store=store, product_id=product, console=console),
            platform=platform,
            title_id=title_id,
        )
    cursor = await repo._conn.execute(
        "INSERT INTO games (name, name_ru, created_at, updated_at)"
        " VALUES ('The Game', 'Игра', '2026-10-30', '2026-10-30') RETURNING game_id"
    )
    game_id = int((await cursor.fetchone())[0])
    await repo._conn.execute("UPDATE versions SET game_id = ?", (game_id,))
    await repo._conn.commit()
    return game_id


@pytest.mark.asyncio
async def test_a_game_on_two_platforms_is_one_month_game(repo: Repo) -> None:
    game_id = await _game_of_two_lists(repo)
    found = await game_page.games_of_lists(
        repo, [("xbox_modern", "100"), ("steam", "200"), ("psn", "NPWR1")], "ru"
    )
    assert {key: g["game_id"] for key, g in found.items()} == {
        ("xbox_modern", "100"): game_id,
        ("steam", "200"): game_id,
    }  # a list in no game is left to its caller
    assert found[("steam", "200")]["name"] == "Игра"

    rows = [
        SimpleNamespace(platform="xbox_modern", title_id="100", name="List X", count=3, score=30),
        SimpleNamespace(platform="psn", title_id="NPWR1", name="Other", count=1, score=0),
        SimpleNamespace(platform="steam", title_id="200", name="List S", count=2, score=0),
    ]
    games = await month_games(repo, rows, "en")
    assert [(g["game_id"], g["name"], g["unlocked"]) for g in games] == [
        (game_id, "The Game", 5),
        (None, "Other", 1),
    ]
    # Each platform's list keeps its own count: progress is never summed.
    assert games[0]["lists"] == [
        {"platform": "xbox_modern", "title_id": "100", "unlocked": 3},
        {"platform": "steam", "title_id": "200", "unlocked": 2},
    ]


@pytest.mark.asyncio
async def test_a_psn_store_title_and_a_regional_twin_find_their_game(repo: Repo) -> None:
    await repo.save_version(
        StoreVersion(
            store="psn", product_id="10000039", console="ps4",
            store_ids=[("psn_title", "CUSA23080_00"), ("list", "psn:NPWR2")],
        ),
        platform="psn",
        title_id="NPWR1",
    )  # fmt: skip
    cursor = await repo._conn.execute(
        "INSERT INTO games (name, created_at, updated_at) VALUES ('Psn Game', 'x', 'x')"
        " RETURNING game_id"
    )
    game_id = int((await cursor.fetchone())[0])
    await repo._conn.execute("UPDATE versions SET game_id = ?", (game_id,))
    await repo._conn.commit()
    assert await repo.game_of_list("psn", "NPWR1") == game_id
    assert await repo.game_of_list("psn", "NPWR2") == game_id  # a regional twin
    assert await repo.game_of_list("psn", "CUSA23080_00") == game_id  # what presence names
    assert await repo.game_of_list("psn", "CUSA23080") == game_id
    assert await repo.game_of_list("psn", "CUSA99999") is None
    assert await game_page.playing_name(repo, "psn", "CUSA23080_00", "en") == "Psn Game"


@pytest.mark.asyncio
async def test_the_same_game_on_two_platforms_is_linked_by_the_walker(repo: Repo) -> None:
    from bot.poller.stand_in_links import SOURCE, StandInLinks

    # Two lists of one name, each its own game (what a first visit makes).
    for platform, title_id in (("xbox_modern", "1799950478"), ("psn", "NPWR59465_00")):
        await repo._conn.execute(
            "INSERT INTO achievement_list_connectors (platform, title_id, name, name_en,"
            " updated_at) VALUES (?, ?, 'Aniimo', 'Aniimo', '2026-10-30')",
            (platform, title_id),
        )
        (version,) = await repo.ensure_list_version(platform, title_id)
        # As an earlier first visit made them: a game each.
        game = await repo.create_game("Aniimo", None, version)
        await repo._conn.execute(
            "UPDATE versions SET game_id = ? WHERE version_id = ?", (game, version)
        )
    await repo._conn.commit()
    cursor = await repo._conn.execute("SELECT COUNT(DISTINCT game_id) FROM versions")
    assert (await cursor.fetchone())[0] == 2

    await StandInLinks(repo).tick()
    cursor = await repo._conn.execute("SELECT COUNT(DISTINCT game_id) FROM versions")
    assert (await cursor.fetchone())[0] == 1
    assert await repo.stand_in_versions_due(SOURCE, 10) == []  # looked at: rests a week


@pytest.mark.asyncio
async def test_a_game_added_by_hand_survives_a_rebuild_and_joins_the_real_one(repo: Repo) -> None:
    from bot.services.game_link import GameLinker

    game, made = await repo.add_manual_game("Brand New Game", "Совсем Новая Игра")
    assert made
    assert await repo.add_manual_game("brand new game") == (game, False)  # the same game
    assert await repo.drop_empty_games() == 0  # it has its version
    cards = await repo.game_cards([game])
    assert (cards[game]["name"], cards[game]["name_ru"]) == ("Brand New Game", "Совсем Новая Игра")

    # The stores bring the real game: the linker joins them, the old id resolves.
    await repo.save_version(
        StoreVersion(
            store="steam", product_id="999", console="steam", name="Brand New Game", kind="game"
        ),
        platform="steam",
        title_id="999",
        origin="store",
    )
    await GameLinker(repo).link_all()
    assert len({v["game_id"] for v in await repo.versions_of_product("steam", "999")}) == 1
    live = await repo.live_game_id(game)
    mine = await repo._conn.execute(
        "SELECT COUNT(DISTINCT game_id) FROM versions WHERE name = 'Brand New Game'"
    )
    assert (await mine.fetchone())[0] == 1
    assert live is not None


@pytest.mark.asyncio
async def test_the_stores_are_searched_and_a_game_in_both_is_one_row(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bot.services import manual_games

    async def steam(term: str) -> list[dict]:
        return [
            {"type": "app", "id": 555, "name": "Brand New Game", "tiny_image": "https://s/i.jpg"},
            {"type": "dlc", "id": 556, "name": "Brand New Game DLC"},
        ]

    async def xbox(term: str) -> list[dict]:
        return [
            {
                "Type": "Game",
                "ProductId": "9pk8phlcqdf6",
                "Title": "Brand New Game",
                "Icon": "//x/i",
            },
            {"Type": "Consumable", "ProductId": "9NWP9VD2HQL5", "Title": "Brand New Game: Gems"},
            {"Type": "Game", "ProductId": "9ABCDEFGHIJK", "Title": "Another"},
        ]

    monkeypatch.setattr(manual_games.steam_store, "search", steam)
    monkeypatch.setattr(manual_games.xbox_catalog, "search", xbox)
    hits = await manual_games.search_stores("brand")
    assert [h["name"] for h in hits] == ["Brand New Game", "Another"]
    assert hits[0]["stores"] == [
        {"store": "steam", "id": "555"},
        {"store": "xbox", "id": "9PK8PHLCQDF6"},
    ]
    assert hits[0]["image"] == "https://s/i.jpg"  # no poster of now: the banner stands in
    assert manual_games.queue_key("steam", "555") == "product:steam:555"
    assert manual_games.queue_key("xbox", "9pk8phlcqdf6") == "storeid:xbox_product:9PK8PHLCQDF6"
    assert manual_games.queue_key("steam", "x") is None

    # Added by hand with the store page's key: the octopus reaches it by that.
    _game, made = await repo.add_manual_game("Brand New Game", None, "product:steam:555")
    assert made
    cursor = await repo._conn.execute("SELECT key FROM octopus_queue")
    assert [row[0] for row in await cursor.fetchall()] == ["product:steam:555"]


@pytest.mark.asyncio
async def test_a_prize_shows_the_game_its_hand_added_one_became(repo: Repo) -> None:
    from bot.services.game_link import GameLinker
    from bot.web.mini_pass import _cards

    manual, _ = await repo.add_manual_game("Brand New Game", None)
    await repo.save_version(
        StoreVersion(
            store="steam", product_id="777", console="steam", name="Brand New Game",
            kind="game", media={"poster": "https://shared.steamstatic.com/p.jpg"},
        ),
        platform="steam",
        title_id="777",
        origin="store",
    )  # fmt: skip
    await GameLinker(repo).link_all()
    cards = await _cards(repo, [{"game_id": manual}])
    assert cards[manual]["poster"] == "https://shared.steamstatic.com/p.jpg"


@pytest.mark.asyncio
async def test_a_game_the_catalog_has_is_never_added_again(repo: Repo) -> None:
    from bot.services import manual_games

    # The catalog has Aniimo as a stand-in made from an Xbox title id.
    await repo._conn.execute(
        "INSERT INTO achievement_list_connectors (platform, title_id, name, name_en, updated_at)"
        " VALUES ('xbox_modern', '1799950478', 'ANIIMO™', 'ANIIMO™', '2026-10-30')"
    )
    existing = await repo.adopt_list_as_game("xbox_modern", "1799950478")
    assert existing is not None

    # A store's hit under other ids and a plainer spelling is that very game.
    stores = [{"store": "steam", "id": "4126040"}, {"store": "xbox", "id": "9PK8PHLCQDF6"}]
    assert await manual_games.existing_game(repo, "Aniimo", stores) == existing
    assert await repo.add_manual_game("aniimo") == (existing, False)
    cursor = await repo._conn.execute("SELECT COUNT(*) FROM games")
    assert (await cursor.fetchone())[0] == 1

    # A game it lacks is the only one added — and once.
    assert await manual_games.existing_game(repo, "Brand New Game", stores) is None
    new, made = await repo.add_manual_game("Brand New Game")
    assert made and new != existing
    assert await manual_games.existing_game(repo, "Brand  New Game!", []) == new


@pytest.mark.asyncio
async def test_a_list_opened_first_joins_the_game_of_its_name(repo: Repo) -> None:
    """Aniimo on Xbox and on PS5, each opened for the first time: one game."""
    ids = {}
    for platform, title_id in (("xbox_modern", "1799950478"), ("psn", "NPWR59465_00")):
        await repo._conn.execute(
            "INSERT INTO achievement_list_connectors (platform, title_id, name, name_en,"
            " updated_at) VALUES (?, ?, 'Aniimo', 'Aniimo', '2026-10-30')",
            (platform, title_id),
        )
        ids[platform] = await repo.adopt_list_as_game(platform, title_id)
    assert ids["xbox_modern"] == ids["psn"]
    cursor = await repo._conn.execute("SELECT COUNT(*) FROM games")
    assert (await cursor.fetchone())[0] == 1


@pytest.mark.asyncio
async def test_a_dlc_or_an_edition_of_a_game_we_have_is_not_a_new_game(repo: Repo) -> None:
    from bot.services import manual_games

    await repo._conn.execute(
        "INSERT INTO achievement_list_connectors (platform, title_id, name, name_en, updated_at)"
        " VALUES ('steam', '1622910', 'Still Wakes the Deep', 'Still Wakes the Deep', '2026-10-30')"
    )
    game = await repo.adopt_list_as_game("steam", "1622910")
    cursor = await repo._conn.execute("SELECT version_id FROM versions WHERE game_id = ?", (game,))
    version = (await cursor.fetchone())[0]
    await repo._conn.execute(
        "INSERT INTO dlcs (version_id, store_id, name, kind, updated_at)"
        " VALUES (?, '3465690', 'Still Wakes the Deep: Siren’s Rest', 'dlc', '2026-10-30')",
        (version,),
    )
    await repo._conn.execute(
        "INSERT INTO editions (edition_id, store, store_id, name, first_seen_at, last_seen_at)"
        " VALUES (1, 'xbox', '9NZT1H7FW8W5', 'Still Wakes the Deep - The Complete Collection',"
        " '2026-10-30', '2026-10-30')"
    )
    await repo._conn.execute(
        "INSERT INTO edition_items (edition_id, store_id, item_kind, version_id)"
        " VALUES (1, 'x', 'game', ?)",
        (version,),
    )
    for name in (
        "Still Wakes the Deep: Siren's Rest",
        "Still Wakes the Deep - The Complete Collection",
    ):
        assert await manual_games.existing_game(repo, name, []) == game
