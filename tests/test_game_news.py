"""Game news (owner, 2026-10-05): the developers' posts about the games one's
circle plays, in the Mini App's «Новости»."""

from __future__ import annotations

from datetime import UTC, datetime

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.constants import Platform
from bot.db.repo import AchievementRow, Repo, StoredPatch
from bot.util import utcnow_iso
from bot.web.mini_api import cors_middleware, setup_mini_api

STEAM_ID = "76561198000000001"


def _post(gid: str, date: str, kind: str = "news", title: str | None = None) -> StoredPatch:
    return StoredPatch(
        gid=gid,
        title=title or f"Post {gid}",
        published_at=date,
        text_en="We fixed [the thing](https://example.com).\nhttps://youtu.be/x\nMore words.",
        title_ru=None,
        text_ru=None,
        kind=kind,
        image_url="https://clan.akamai.steamstatic.com/images/1/a.png",
    )


async def _player(repo: Repo) -> int:
    person = await repo.ensure_user(1, "ada")
    assert person is not None
    await repo.link_platform_account(person, Platform.STEAM, STEAM_ID, "Ada")
    await repo.upsert_title("620", "Portal 2", Platform.STEAM)
    await repo.insert_new_achievements_steam(
        person,
        STEAM_ID,
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


async def test_news_are_the_played_games_posts_of_the_month(repo: Repo) -> None:
    person = await _player(repo)
    today = datetime.now(UTC).date().isoformat()
    month = today[:7]
    await repo.save_game_patches(
        620,
        [
            _post("n1", today),
            _post("p1", f"{month}-01", kind="patch", title="Update 1.2"),
            _post("old", "2020-01-05"),
        ],
    )
    # A game nobody here plays brings nothing.
    await repo.save_game_patches(999, [_post("x", today)])

    rows = await repo.games_news(
        [person], played_since="2000-01-01", since=f"{month}-01", until="2999-01-01", limit=50
    )
    # Newest first; on the same day, by the post's id.
    assert [row.gid for row in rows] == ["n1", "p1"]
    assert {row.gid: row.kind for row in rows} == {"n1": "news", "p1": "patch"}
    assert rows[0].game == "Portal 2"

    # The game page's «Новости» tab has both, newest first, each with its kind.
    assert [(p.gid, p.kind) for p in await repo.game_patches(620, 10)] == [
        ("n1", "news"),
        ("p1", "patch"),
        ("old", "news"),
    ]


async def test_the_news_route_reads_the_viewers_circle(repo: Repo, settings) -> None:
    person = await _player(repo)
    today = datetime.now(UTC).date().isoformat()
    await repo.save_game_patches(620, [_post("n1", today)])
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        client.session.cookie_jar.update_cookies(
            {"ab_session": await repo.create_session(person, "t")}
        )
        assert (await client.get("/api/mini/club/news")).status == 400
        body = await (await client.get("/api/mini/club/news?scope=following")).json()
        [item] = body["items"]
        assert item["game"]["name"] == "Portal 2"
        assert item["game"]["title_id"] == "620"
        # Links keep their words; a line that is only an address goes.
        assert item["excerpt"] == "We fixed the thing. More words."
        assert item["url"].endswith("/news/app/620/view/n1")
        assert body["month"] == today[:7]
    finally:
        await client.close()


async def test_an_excluded_person_hears_no_game_news(repo: Repo) -> None:
    """An excluded person is told nothing (#171 review)."""
    person = await _player(repo)
    assert [row[0] for row in await repo.game_news_readers(620, played_since="2000-01-01")] == [
        person
    ]
    await repo.set_excluded(person, True, None)
    assert await repo.game_news_readers(620, played_since="2000-01-01") == []
