"""The Mini App's game page, the games search and favorite games (#147,
stage 5; owner, 2026-10-25)."""

from __future__ import annotations

from datetime import UTC, datetime

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.constants import Platform
from bot.db.repo import AchievementRow, Repo, StoredPatch
from bot.poller.patch_refresh import PatchRefresh
from bot.services import game_page
from bot.services.notifier import carries
from bot.util import utcnow_iso
from bot.web.mini_api import cors_middleware, setup_mini_api

STEAM_ID = "76561198000000001"


async def _player(repo: Repo, tg_id: int = 1, handle: str = "ada", steam_id: str = STEAM_ID) -> int:
    person = await repo.ensure_user(tg_id, handle)
    assert person is not None
    await repo.link_platform_account(person, Platform.STEAM, steam_id, handle)
    await repo.upsert_title("620", "Portal 2", Platform.STEAM)
    await repo.insert_new_achievements_steam(
        person,
        steam_id,
        [
            AchievementRow(
                title_id="620",
                achievement_id="a1",
                name="Wake Up Call",
                description=None,
                icon_url=None,
                unlocked_at=utcnow_iso(),
                gamerscore=0,
                rarity_percent=None,
                platform="steam",
            )
        ],
        is_backfill=False,
    )
    return person


def test_a_search_ranks_the_name_itself_first() -> None:
    names = [
        (1, "Portal 2"),
        (2, "Portal"),
        (3, "Portal Knights"),
        (4, "The Portal Saga"),
        (5, "Teleportal"),
        (6, "Halo"),
        (7, "Ведьмак 3: Дикая Охота"),
    ]
    ranked = sorted(game_page.rank_search(names, "portal"), key=lambda m: (m[1], m[2]))
    assert [game for game, _rank, _length in ranked] == [2, 1, 3, 4, 5]
    # Case and ё do not matter.
    assert [g for g, _r, _l in game_page.rank_search(names, "ВЕДЬМАК")] == [7]
    assert game_page.rank_search(names, "  ") == []


def test_a_games_pictures_come_from_its_stores() -> None:
    versions = [
        {
            "store": "steam",
            "product_id": "620",
            "media": '{"cover": "http://s/h.jpg", "screenshots": ["https://s/1.jpg"]}',
        },
        {
            "store": "xbox",
            "product_id": "X",
            "media": {"poster": "http://x/p", "background": "https://x/b"},
        },
    ]
    art = game_page.art_of(versions)
    # Xbox's box art and hero first; plain http made https.
    assert art == {"poster": "https://x/p", "hero": "https://x/b", "header": "https://s/h.jpg"}
    assert game_page.art_of(versions[:1])["poster"].endswith("/620/library_600x900.jpg")


def test_dlc_are_one_card_across_consoles_by_their_day() -> None:
    dlcs = [
        {"name": "Portal 2 - Peer Review", "console": "one", "release_date": "2011-10-04"},
        {
            "name": "Peer Review",
            "console": "steam",
            "release_date": "2011-10-04",
            "comp_main": 7200,
        },
        {
            "name": "Portal 2 Soundtrack",
            "console": "steam",
            "release_date": "2010-01-01",
            "kind": "soundtrack",
        },
    ]
    cards = game_page.dlcs_of(dlcs, "Portal 2")
    assert [c["name"] for c in cards] == ["Portal 2 Soundtrack", "Portal 2 - Peer Review"]
    assert cards[1]["consoles"] == ["one", "steam"] and cards[1]["hours"] == 2.0


def test_editions_shortest_name_first() -> None:
    editions = [
        {"name": "Game Ultimate Edition"},
        {"name": "Game"},
        {"name": "Game Deluxe"},
        {"name": "game"},
    ]
    assert [e["name"] for e in game_page.editions_of(editions)] == [
        "Game",
        "Game Deluxe",
        "Game Ultimate Edition",
    ]


def test_favorites_only_carries_a_favorites_news() -> None:
    tokens = frozenset({"game_news:favorites"})
    assert carries(tokens, "game_news", {"post": "patch", "favorite": True}, friend=False)
    assert not carries(tokens, "game_news", {"post": "patch", "favorite": False}, friend=False)
    assert carries(frozenset({"game_news:patch"}), "game_news", {"post": "patch"}, friend=False)


async def test_a_list_in_no_game_opens_as_a_game_of_its_own(repo: Repo) -> None:
    await _player(repo)
    assert await repo.game_of_list("steam", "620") is None
    game = await repo.adopt_list_as_game("steam", "620")
    assert game is not None
    assert await repo.game_of_list("steam", "620") == game
    # A merged game's id leads to the game it went into.
    other = await repo.create_game("Portal 2 (merged)", None)
    await repo.merge_game_into(other, game)
    assert await repo.live_game_id(other) == game


async def test_favorites_and_their_news(repo: Repo, settings) -> None:
    from bot.services.crypto import TokenCipher
    from bot.services.notifier import Notifier

    player = await _player(repo)
    fan = await repo.ensure_user(2, "bob")
    assert fan is not None
    game = await repo.adopt_list_as_game("steam", "620")
    assert game is not None

    await repo.set_favorite(fan, game, True)
    await repo.set_favorite(fan, game, True)
    assert await repo.favorite_game_ids(fan) == [game]
    assert await repo.favorite_count(game) == 1
    assert await repo.favorite_steam_apps() == [620]
    assert await repo.favoriters_of_app(620) == [(fan, game, "Portal 2")]

    # Read every hour: a favorite's app is due before any other.
    calls: list[int] = []

    class Extras:
        async def refresh_patches(self, appid: int) -> None:
            calls.append(appid)

    await PatchRefresh(repo, Extras()).tick()  # type: ignore[arg-type]
    assert calls == [620]

    # Its news reach the fan, who never played it, as a favorite's.
    today = datetime.now(UTC).isoformat(timespec="seconds")
    post = StoredPatch(
        gid="p1",
        title="Update",
        published_at=today,
        text_en="",
        title_ru=None,
        text_ru=None,
        kind="patch",
        image_url=None,
    )
    notifier = Notifier(repo, TokenCipher(settings.fernet_key.get_secret_value()))
    await notifier.tell_about_game_news(620, [post])
    [told] = await repo.notifications_of(fan)
    assert told.data["favorite"] is True and told.data["title_id"] == "620"
    [played] = await repo.notifications_of(player)
    assert played.data["favorite"] is False

    await repo.set_favorite(fan, game, False)
    assert await repo.favorite_game_ids(fan) == []


async def test_a_favorite_whose_id_is_gone_is_found_by_its_anchor(repo: Repo) -> None:
    await _player(repo)
    game = await repo.adopt_list_as_game("steam", "620")
    assert game is not None
    person = await repo.ensure_user(3, "cat")
    assert person is not None
    await repo.set_favorite(person, game, True)
    # A catalog carried over gives the same game another id.
    await repo._conn.execute("UPDATE versions SET game_id = NULL WHERE game_id = ?", (game,))
    await repo._conn.execute("DELETE FROM games WHERE game_id = ?", (game,))
    await repo._conn.commit()
    # The old id now names another game.
    assert await repo.create_game("Some Other Game", None) == game
    again = await repo.adopt_list_as_game("steam", "620")
    assert again is not None and again != game
    assert await repo.favorite_game_ids(person) == [again]


async def test_the_page_search_and_favorite_routes(repo: Repo, settings) -> None:
    person = await _player(repo)
    stranger = await repo.ensure_user(9, "zed")
    assert stranger is not None
    # Its Steam news were read already: the page asks Steam nothing.
    await repo.save_game_patches(620, [])
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        client.session.cookie_jar.update_cookies(
            {"ab_session": await repo.create_session(person, "t")}
        )
        body = await (await client.get("/api/mini/game?platform=steam&title_id=620")).json()
        game = body["game"]["game_id"]
        assert body["game"]["name"] == "Portal 2"
        assert body["progress"]["person_id"] == person and body["progress"]["count"] == 1
        assert body["viewed_is_me"] is True and body["favorite"] is False

        assert (await client.put(f"/api/mini/game/{game}/favorite")).status == 200
        body = await (await client.get(f"/api/mini/game?game_id={game}")).json()
        assert body["favorite"] is True and body["favorites"] == 1

        found = await (await client.get("/api/mini/game-search?q=port")).json()
        assert [g["game_id"] for g in found["games"]] == [game]
        assert (await client.get("/api/mini/game-search?q=p")).status == 400

        mine = await (await client.get("/api/mini/game-favorites")).json()
        assert [g["game_id"] for g in mine["games"]] == [game]
        # Somebody who does not know them sees none of it.
        assert (await client.get(f"/api/mini/game-favorites?person={stranger}")).status == 403

        assert (await client.delete(f"/api/mini/game/{game}/favorite")).status == 200
        mine = await (await client.get("/api/mini/game-favorites")).json()
        assert mine["games"] == []
    finally:
        await client.close()
