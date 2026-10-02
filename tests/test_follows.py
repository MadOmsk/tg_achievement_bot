"""Follows, blocks, search and who sees whom (#157, migration 073)."""

from __future__ import annotations

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.db.repo import Repo
from bot.services.people import ACTIVITY_ALL, ACTIVITY_FRIENDS, ACTIVITY_NOBODY, Relation, can_view
from bot.web.mini_api import cors_middleware, setup_mini_api
from tests.test_mini_delete import _signed_init_data


async def _people(repo: Repo) -> tuple[int, int, int]:
    for tg_id, name in ((1, "alice"), (2, "bobby"), (3, "carol")):
        await repo.ensure_user(tg_id, name)
    ids = [await repo.person_id(tg_id) for tg_id in (1, 2, 3)]
    return ids[0], ids[1], ids[2]


def test_the_visibility_rule() -> None:
    stranger = Relation()
    friends = Relation(following=True, followed_by=True)
    one_way = Relation(following=True)
    assert can_view(ACTIVITY_ALL, stranger)
    assert not can_view(ACTIVITY_FRIENDS, stranger)
    assert not can_view(ACTIVITY_FRIENDS, one_way)
    assert can_view(ACTIVITY_FRIENDS, friends)
    assert not can_view(ACTIVITY_NOBODY, friends)
    assert can_view(ACTIVITY_NOBODY, stranger, self_view=True)
    # A block cuts it either way, whatever the setting says.
    assert not can_view(ACTIVITY_ALL, Relation(blocked=True))
    assert not can_view(ACTIVITY_ALL, Relation(blocked_by=True))


async def test_following_needs_no_consent_and_two_follows_make_friends(repo: Repo) -> None:
    alice, bobby, _ = await _people(repo)
    assert await repo.follow(alice, bobby)
    assert not await repo.follow(alice, bobby)  # already
    assert not await repo.follow(alice, alice)
    assert (await repo.relation(alice, bobby)).following
    assert (await repo.relation(bobby, alice)).followed_by
    assert not (await repo.relation(alice, bobby)).friends

    await repo.follow(bobby, alice)
    assert (await repo.relation(alice, bobby)).friends

    await repo.unfollow(alice, bobby)
    assert not (await repo.relation(alice, bobby)).friends
    assert await repo.follow_counts(alice) == (1, 0)


async def test_removing_a_follower_is_not_a_block(repo: Repo) -> None:
    alice, bobby, _ = await _people(repo)
    await repo.follow(bobby, alice)
    await repo.remove_follower(alice, bobby)
    relation = await repo.relation(alice, bobby)
    assert not relation.followed_by and not relation.blocked
    assert await repo.follow(bobby, alice)  # may follow again


async def test_a_block_ends_both_follows_and_hides_each_from_the_other(repo: Repo) -> None:
    alice, bobby, _ = await _people(repo)
    await repo.follow(alice, bobby)
    await repo.follow(bobby, alice)
    await repo.block(alice, bobby)

    assert await repo.follow_counts(alice) == (0, 0)
    assert not await repo.follow(bobby, alice)  # cannot follow someone who blocked you
    assert not await repo.follow(alice, bobby)  # nor someone you blocked
    assert await repo.search_people(alice, "bobby") == []
    assert await repo.search_people(bobby, "alice") == []
    assert not await repo.can_view_activity(bobby, alice)

    await repo.unblock(alice, bobby)
    assert [p.handle for p in await repo.search_people(alice, "bobby")] == ["bobby"]


async def test_search_is_by_nickname_prefix_from_three_characters(repo: Repo) -> None:
    alice, _, _ = await _people(repo)
    assert [p.handle for p in await repo.search_people(alice, "BOB")] == ["bobby"]
    assert await repo.search_people(alice, "bo") == []
    assert await repo.search_people(alice, "ali") == []  # never oneself
    assert await repo.search_people(alice, "bo%") == []
    assert await repo.search_people(alice, "") == []


async def test_search_finds_a_numbered_nickname_by_its_digits(repo: Repo) -> None:
    alice, _, _ = await _people(repo)
    await repo.ensure_user(4, "Bobby")  # taken: gets digits
    other = await repo.person_id(4)
    shown = (await repo.person_row(other)).handle
    assert "#" in shown
    assert [p.id for p in await repo.search_people(alice, shown)] == [other]
    assert len(await repo.search_people(alice, "bobby")) == 2


async def test_suggestions_are_people_from_shared_chats_not_yet_followed(repo: Repo) -> None:
    alice, bobby, carol = await _people(repo)
    await repo.upsert_chat(-100, "Chat", 1)
    await repo.subscribe(-100, 1)
    await repo.subscribe(-100, 2)
    assert [p.handle for p in await repo.suggested_people(alice)] == ["bobby"]
    await repo.follow(alice, bobby)
    assert await repo.suggested_people(alice) == []
    assert carol  # in no chat with alice


async def test_the_activity_setting_decides_who_sees(repo: Repo) -> None:
    alice, bobby, _ = await _people(repo)
    assert await repo.can_view_activity(bobby, alice)
    await repo.set_activity_visible(alice, ACTIVITY_FRIENDS)
    assert not await repo.can_view_activity(bobby, alice)
    await repo.follow(bobby, alice)
    await repo.follow(alice, bobby)
    assert await repo.can_view_activity(bobby, alice)
    await repo.set_activity_visible(alice, ACTIVITY_NOBODY)
    assert not await repo.can_view_activity(bobby, alice)
    assert await repo.can_view_activity(alice, alice)


async def test_mini_api_people_flow(repo: Repo, settings) -> None:
    app = web.Application(middlewares=[cors_middleware()])
    sent: list[tuple[int, str]] = []

    class _Bot:
        async def send_message(self, chat_id: int, text: str) -> None:
            sent.append((chat_id, text))

    setup_mini_api(app, settings, repo, bot=_Bot())
    token = settings.bot_token.get_secret_value()
    mine = {"X-Telegram-Init-Data": _signed_init_data(token, 42)}
    await repo.ensure_user(7, "friend7")
    other = await repo.person_id(7)

    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        found = await (await client.get("/api/mini/people/search?q=friend", headers=mine)).json()
        assert [p["id"] for p in found["people"]] == [other]

        followed = await client.post(f"/api/mini/people/{other}/follow", headers=mine)
        assert (await followed.json())["relation"]["following"] is True
        assert len(sent) == 1 and sent[0][0] == 7 and "test" in sent[0][1]

        profile = await (await client.get(f"/api/mini/people/{other}", headers=mine)).json()
        assert profile["followers"] == 1 and profile["can_view"] is True

        listed = await (await client.get("/api/mini/me/following", headers=mine)).json()
        assert [p["id"] for p in listed["people"]] == [other]

        privacy = await client.put(
            "/api/mini/me/privacy", json={"activity_visible": "friends"}, headers=mine
        )
        assert (await privacy.json())["activity_visible"] == "friends"
        bad = await client.put(
            "/api/mini/me/privacy", json={"activity_visible": "everyone"}, headers=mine
        )
        assert bad.status == 400

        await client.post(f"/api/mini/people/{other}/block", headers=mine)
        gone = await (await client.get("/api/mini/me/following", headers=mine)).json()
        assert gone["people"] == []
    finally:
        await client.close()


async def test_the_following_scope_feeds_and_ranks_only_followed_people(
    repo: Repo, settings
) -> None:
    from datetime import UTC, datetime

    from bot.db.repo import AchievementRow

    def row(achievement_id: str) -> AchievementRow:
        return AchievementRow(
            title_id="1",
            achievement_id=achievement_id,
            name=achievement_id,
            description=None,
            icon_url=None,
            unlocked_at=datetime.now(UTC).isoformat(timespec="seconds"),
            gamerscore=10,
            rarity_percent=50.0,
            platform="xbox_modern",
        )

    for tg_id, xuid in ((42, "x42"), (7, "x7"), (8, "x8")):
        await repo.ensure_user(tg_id, f"user{tg_id}")
        await repo.link_xbox_account(tg_id, xuid, f"Tag{tg_id}", 0)
        await repo.insert_new_achievements(xuid, [row(f"a{tg_id}")], is_backfill=False)
    me = await repo.person_id(42)
    followed = await repo.person_id(7)
    stranger = await repo.person_id(8)
    await repo.follow(me, followed)

    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)
    headers = {"X-Telegram-Init-Data": _signed_init_data(settings.bot_token.get_secret_value(), 42)}
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        feed = await (
            await client.get("/api/mini/club/feed?scope=following", headers=headers)
        ).json()
        assert sorted(item["name"] for item in feed["items"]) == ["a42", "a7"]

        summary = await (
            await client.get("/api/mini/club/summary?scope=following", headers=headers)
        ).json()
        assert len(summary["month"]) == 2
        assert stranger  # followed by nobody, so absent from both

        # A followed person who hides their activity drops out.
        await repo.set_activity_visible(followed, "nobody")
        feed = await (
            await client.get("/api/mini/club/feed?scope=following", headers=headers)
        ).json()
        assert [item["name"] for item in feed["items"]] == ["a42"]
    finally:
        await client.close()
