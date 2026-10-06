"""Follows, blocks, search and who sees whom (#157, migration 073)."""

from __future__ import annotations

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.db.repo import FollowTooSoon, Repo
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


async def test_friends_of_friends_are_suggested_by_how_many_lead_to_them(repo: Repo) -> None:
    alice, bobby, carol = await _people(repo)
    await repo.follow(alice, bobby)
    await repo.follow(bobby, carol)
    await repo.follow(bobby, alice)  # alice herself is never suggested

    rows = await repo.people_you_may_know(alice)
    assert [(row.id, mutual) for row, mutual in rows] == [(carol, 1)]

    await repo.follow(alice, carol)  # followed: no longer a suggestion
    assert await repo.people_you_may_know(alice) == []


async def test_friends_of_friends_never_reveal_a_hidden_persons_follows(repo: Repo) -> None:
    """Whom somebody follows is their activity: a person whose activity the
    viewer may not see leads to no suggestion."""
    alice, bobby, carol = await _people(repo)
    await repo.follow(alice, bobby)
    await repo.follow(bobby, carol)
    await repo.set_activity_visible(bobby, ACTIVITY_NOBODY)
    assert await repo.people_you_may_know(alice) == []
    await repo.set_activity_visible(bobby, ACTIVITY_FRIENDS)
    assert await repo.people_you_may_know(alice) == []
    await repo.follow(bobby, alice)  # now friends: alice may see bobby's follows
    assert [row.id for row, _ in await repo.people_you_may_know(alice)] == [carol]


async def test_another_persons_follows_carry_the_viewers_relation(repo: Repo) -> None:
    alice, bobby, carol = await _people(repo)
    await repo.follow(bobby, carol)
    await repo.follow(alice, carol)
    await repo.follow(carol, bobby)

    following = await repo.following_of_person(alice, bobby)
    assert [row.id for row in following] == [carol]
    assert following[0].relation.following  # alice follows carol
    assert [row.id for row in await repo.followers_of_person(alice, bobby)] == [carol]

    await repo.block(carol, alice)
    assert await repo.following_of_person(alice, bobby) == []


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
    await repo.subscribe(-100, await repo.person_id(1))
    await repo.subscribe(-100, await repo.person_id(2))
    assert [p.handle for p in await repo.suggested_people(alice)] == ["bobby"]
    await repo.follow(alice, bobby)
    assert await repo.suggested_people(alice) == []
    assert carol  # in no chat with alice


async def test_the_activity_setting_decides_who_sees(repo: Repo) -> None:
    alice, bobby, _ = await _people(repo)
    await repo.upsert_chat(-100, "Chat", 1)
    await repo.subscribe(-100, await repo.person_id(1))
    await repo.subscribe(-100, await repo.person_id(2))
    assert await repo.can_view_activity(bobby, alice)
    await repo.set_activity_visible(alice, ACTIVITY_FRIENDS)
    assert not await repo.can_view_activity(bobby, alice)
    await repo.follow(bobby, alice)
    await repo.follow(alice, bobby)
    assert await repo.can_view_activity(bobby, alice)
    await repo.set_activity_visible(alice, ACTIVITY_NOBODY)
    assert not await repo.can_view_activity(bobby, alice)
    assert await repo.can_view_activity(alice, alice)


async def test_everyone_means_people_who_know_you_not_any_stranger(repo: Repo) -> None:
    """ "Everyone" still needs a shared active chat or a follow: a nickname found
    by search is not enough to see somebody's play (owner, 2026-10-03)."""
    alice, bobby, carol = await _people(repo)
    assert not await repo.can_view_activity(carol, alice)
    await repo.follow(carol, alice)
    assert await repo.can_view_activity(carol, alice)
    await repo.upsert_chat(-100, "Chat", 1)
    await repo.subscribe(-100, await repo.person_id(1))
    await repo.subscribe(-100, await repo.person_id(2))
    assert await repo.can_view_activity(bobby, alice)
    await repo.deactivate_chat(-100)
    assert not await repo.can_view_activity(bobby, alice)


async def test_a_follow_notice_goes_out_at_most_once_a_day_per_pair(repo: Repo) -> None:
    alice, bobby, carol = await _people(repo)
    assert await repo.claim_follow_notice(alice, bobby)
    assert not await repo.claim_follow_notice(alice, bobby)
    assert await repo.claim_follow_notice(carol, bobby)
    await repo._conn.execute("UPDATE follow_log SET notified_at = '2000-01-01T00:00:00+00:00'")
    assert await repo.claim_follow_notice(alice, bobby)


async def test_following_again_right_after_an_unfollow_waits(repo: Repo) -> None:
    alice, bobby, carol = await _people(repo)
    await repo.unfollow(alice, bobby)  # changed nothing: no cooldown
    assert await repo.follow(alice, bobby)
    await repo.unfollow(alice, bobby)
    with pytest.raises(FollowTooSoon):
        await repo.follow(alice, bobby)
    assert await repo.follow(alice, carol)  # other people are not affected
    await repo._conn.execute("UPDATE follow_log SET unfollowed_at = '2000-01-01T00:00:00+00:00'")
    assert await repo.follow(alice, bobby)


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
        # A stranger's Telegram id is not handed out by search.
        assert found["people"][0]["tg_id"] is None

        followed = await client.post(f"/api/mini/people/{other}/follow", headers=mine)
        assert (await followed.json())["relation"]["following"] is True
        assert len(sent) == 1 and sent[0][0] == 7 and "test" in sent[0][1]
        # Unfollow and follow again: refused for ten minutes, and after that no
        # second DM the same day.
        await client.delete(f"/api/mini/people/{other}/follow", headers=mine)
        again = await client.post(f"/api/mini/people/{other}/follow", headers=mine)
        assert (again.status, (await again.json())["error"]) == (429, "too_soon")
        await repo._conn.execute(
            "UPDATE follow_log SET unfollowed_at = '2000-01-01T00:00:00+00:00'"
        )
        again = await client.post(f"/api/mini/people/{other}/follow", headers=mine)
        assert (await again.json())["relation"]["following"] is True
        assert len(sent) == 1

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
        await repo.link_xbox_account(await repo.person_id(tg_id), xuid, f"Tag{tg_id}", 0)
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


async def test_a_private_profile_shows_only_the_name(repo: Repo, settings) -> None:
    await repo.ensure_user(42, "viewer")
    await repo.ensure_user(7, "secretive")
    await repo.upsert_chat(-100, "Chat", 42)
    await repo.subscribe(-100, await repo.person_id(42))
    await repo.subscribe(-100, await repo.person_id(7))
    target = await repo.person_id(7)

    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)
    headers = {"X-Telegram-Init-Data": _signed_init_data(settings.bot_token.get_secret_value(), 42)}
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        url = "/api/mini/club/people?chat_id=-100&tg_id=7"
        assert "hidden" not in await (await client.get(url, headers=headers)).json()

        await repo.set_activity_visible(target, "friends")
        body = await (await client.get(url, headers=headers)).json()
        assert body["hidden"] is True
        assert body["name"] == "secretive"
        assert body["feed"] == [] and body["games"] == []
    finally:
        await client.close()


async def test_online_in_the_following_scope_lists_only_followed_people(
    repo: Repo, settings
) -> None:
    for tg_id in (42, 7, 8):
        await repo.ensure_user(tg_id, f"user{tg_id}")
        await repo.link_xbox_account(await repo.person_id(tg_id), f"x{tg_id}", f"Tag{tg_id}", 0)
    await repo.follow(await repo.person_id(42), await repo.person_id(7))

    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)
    headers = {"X-Telegram-Init-Data": _signed_init_data(settings.bot_token.get_secret_value(), 42)}
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        body = await (
            await client.get("/api/mini/club/online?scope=following", headers=headers)
        ).json()
        assert sorted(m["tg_id"] for m in body["members"]) == [7, 42]
    finally:
        await client.close()


async def test_the_person_card_carries_their_play_when_visible(repo: Repo, settings) -> None:
    await repo.ensure_user(42, "viewer")
    await repo.ensure_user(7, "player7")
    await repo.link_xbox_account(await repo.person_id(7), "x7", "Tag7", 1500)
    other = await repo.person_id(7)
    await repo.upsert_chat(-100, "Chat", 42)
    await repo.subscribe(-100, await repo.person_id(42))
    await repo.subscribe(-100, await repo.person_id(7))
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)
    headers = {"X-Telegram-Init-Data": _signed_init_data(settings.bot_token.get_secret_value(), 42)}
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        body = await (await client.get(f"/api/mini/people/{other}", headers=headers)).json()
        assert body["tg_id"] == 7
        xbox = body["activity"]["platforms"][0]
        assert xbox["gamerscore"] == 1500
        assert (xbox["games"], xbox["rare"], xbox["last_at"]) == (0, 0, None)
        assert body["activity"]["games"] == []

        await repo.set_activity_visible(other, "nobody")
        body = await (await client.get(f"/api/mini/people/{other}", headers=headers)).json()
        assert body["can_view"] is False and body["activity"] is None
    finally:
        await client.close()


async def test_the_card_sums_several_psn_accounts_into_one_row(repo: Repo) -> None:
    """The PSN row is a sum over the person's accounts (#10), so its level and
    its date are too: the highest level, the earliest link — not the first
    account's."""
    from bot.constants import Platform
    from bot.web.mini_chat import build_person_payload

    await repo.ensure_user(7, "player7")
    await repo.link_platform_account(await repo.person_id(7), Platform.PSN, "psn-a", "First")
    await repo.link_platform_account(await repo.person_id(7), Platform.PSN, "psn-b", "Second")
    await repo.set_psn_trophy_level(await repo.person_id(7), 120, account_id="psn-a")
    await repo.set_psn_trophy_level(await repo.person_id(7), 450, account_id="psn-b")
    target = await repo.get_user(await repo.person_id(7))
    payload = await build_person_payload(repo, target, locale="ru")
    (psn,) = [p for p in payload["platforms"] if p["platform"] == Platform.PSN]
    assert psn["name"] == "First, Second"
    assert psn["trophy_level"] == 450
    assert psn["linked_at"] is not None
