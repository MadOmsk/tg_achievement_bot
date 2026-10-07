"""The Mini App names people by their own id (#156): somebody with no Telegram —
signed in by email — is somebody like anybody else in the feed, the ranking,
the face and the page."""

from __future__ import annotations

from datetime import timedelta

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.db.repo import AchievementRow, Repo
from bot.services import custom_avatars
from bot.util import utcnow
from bot.web.mini_api import cors_middleware, setup_mini_api

STEAM_ID = "76561190000000099"


def _row(achievement_id: str) -> AchievementRow:
    return AchievementRow(
        title_id="440",
        achievement_id=achievement_id,
        name=f"Achievement {achievement_id}",
        description="desc",
        icon_url=None,
        unlocked_at=(utcnow() - timedelta(hours=1)).isoformat(timespec="seconds"),
        gamerscore=0,
        rarity_percent=12.0,
        platform="steam",
        title_name="TF2",
    )


async def _email_player(repo: Repo) -> int:
    """A person who came by email, holds a Steam account and earned two things."""
    person = await repo.create_email_person("ada@example.com")
    await repo.give_handle(person)
    await repo.link_platform_account(person, "steam", STEAM_ID, "AdaSteam")
    await repo.insert_new_achievements_steam(
        person, STEAM_ID, [_row("a1"), _row("a2")], is_backfill=False
    )
    return person


async def _client(repo: Repo, settings) -> TestClient:
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


async def _sign_in_as(client: TestClient, repo: Repo, person: int) -> None:
    token = await repo.create_session(person, "test")
    client.session.cookie_jar.update_cookies({"ab_session": token})


async def test_somebody_without_telegram_is_in_a_followers_scope(repo: Repo) -> None:
    ada = await _email_player(repo)
    viewer = await repo.ensure_user(10, "viewer")
    assert viewer is not None
    await repo.follow(viewer, ada)

    members = await repo.following_members(viewer)
    assert set(members) == {viewer, ada}

    stats = await repo.chat_member_stats(0, utcnow() - timedelta(days=1), 10.0, members=members)
    by_person = {row.person_id: row.count for row in stats}
    assert by_person[ada] == 2
    assert by_person[viewer] == 0

    recent = await repo.chat_recent(0, 10, members=members)
    assert {row.person_id for row in recent} == {ada}
    assert all(row.tg_id is None for row in recent)

    games = await repo.users_games_achievements(
        [ada], utcnow() - timedelta(days=1), rare_threshold=10.0
    )
    assert [(game.title_id, game.count) for game in games] == [("440", 2)]


async def test_the_feed_names_people_by_person_id(repo: Repo, settings) -> None:
    ada = await _email_player(repo)
    client = await _client(repo, settings)
    try:
        await _sign_in_as(client, repo, ada)
        feed = await (await client.get("/api/mini/club/feed?scope=following")).json()
        assert {item["person_id"] for item in feed["items"]} == {ada}
        me = await (await client.get("/api/mini/me")).json()
        assert (me["person_id"], me["tg_id"]) == (ada, None)
    finally:
        await client.close()


async def test_a_face_is_served_by_person_id(repo: Repo, settings, tmp_path) -> None:
    from PIL import Image

    ada = await _email_player(repo)
    viewer = await repo.ensure_user(10, "viewer")
    assert viewer is not None
    picture = tmp_path / "in.png"
    Image.new("RGB", (64, 64), "red").save(picture)
    assert await custom_avatars.store(repo, ada, picture.read_bytes())

    client = await _client(repo, settings)
    try:
        await _sign_in_as(client, repo, viewer)
        face = await client.get(f"/api/mini/avatar/p/{ada}")
        assert face.status == 200
        assert face.headers["Content-Type"] == "image/jpeg"
        # Nobody there: nothing to show, not an error page.
        assert (await client.get("/api/mini/avatar/p/99999")).status == 404
    finally:
        await client.close()


async def test_a_persons_page_needs_no_chat_but_keeps_privacy(repo: Repo, settings) -> None:
    ada = await _email_player(repo)
    stranger = await repo.ensure_user(20, "stranger")
    friend = await repo.ensure_user(30, "friend")
    assert stranger is not None and friend is not None
    await repo.follow(friend, ada)

    client = await _client(repo, settings)
    try:
        # One's own page, with no chat at all.
        await _sign_in_as(client, repo, ada)
        own = await (await client.get(f"/api/mini/club/people?person={ada}")).json()
        assert own["person_id"] == ada
        assert own["month"]["count"] == 2

        # Somebody who neither follows nor shares a chat sees the name only.
        client.session.cookie_jar.clear()
        await _sign_in_as(client, repo, stranger)
        hidden = await (await client.get(f"/api/mini/club/people?person={ada}")).json()
        assert hidden["hidden"] is True

        # A follower sees the play.
        client.session.cookie_jar.clear()
        await _sign_in_as(client, repo, friend)
        seen = await (await client.get(f"/api/mini/club/people?person={ada}")).json()
        assert seen.get("hidden") is not True
        assert [game["title_id"] for game in seen["games"]] == ["440"]
    finally:
        await client.close()


async def test_the_admin_manages_somebody_without_telegram(repo: Repo, settings) -> None:
    ada = await _email_player(repo)
    admin = await repo.ensure_user(500, "boss")
    assert admin is not None
    settings.superadmin_tg_ids = [500]
    client = await _client(repo, settings)
    try:
        await _sign_in_as(client, repo, admin)
        users = (await (await client.get("/api/mini/admin/users")).json())["users"]
        [row] = [u for u in users if u["person_id"] == ada]
        assert row["tg_id"] is None and row["month"] == 2

        card = await (await client.get(f"/api/mini/admin/users/p{ada}")).json()
        assert (card["person_id"], card["email"]) == (ada, "ada@example.com")
        excluded = await client.patch(f"/api/mini/admin/users/p{ada}", json={"excluded": True})
        assert (await excluded.json())["is_excluded"] is True

        assert (await client.delete(f"/api/mini/admin/users/p{ada}")).status == 200
        assert await repo.get_user(ada) is None
    finally:
        await client.close()


async def test_an_old_link_to_a_game_names_whose_progress_it_shows(repo: Repo, settings) -> None:
    player = await repo.ensure_user(30, "player")
    viewer = await repo.ensure_user(40, "viewer")
    assert player and viewer
    await repo.link_platform_account(player, "steam", STEAM_ID, "PlayerSteam")
    await repo.insert_new_achievements_steam(player, STEAM_ID, [_row("a1")], is_backfill=False)
    await repo.follow(viewer, player)
    client = await _client(repo, settings)
    try:
        await _sign_in_as(client, repo, viewer)
        # A post's button from before person ids carries a Telegram id.
        old = await (await client.get("/api/mini/games/steam/440?tg_id=30")).json()
        assert old["viewed"]["person_id"] == player
        assert old["viewed"]["name"] == "player"
        new = await (await client.get(f"/api/mini/games/steam/440?person={player}")).json()
        assert new["viewed"]["person_id"] == player
        own = await (await client.get("/api/mini/games/steam/440")).json()
        assert own["viewed"] is None
    finally:
        await client.close()
