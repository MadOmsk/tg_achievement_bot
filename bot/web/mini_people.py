"""Mini API for people (#157): search, follows, followers, blocks, a profile card.
Nobody removes a follower: following is the follower's own choice; one may only
unfollow or block.

Every route here speaks in person ids (`users.id`); `tg_id` is sent along only so
the app can ask for an avatar. A nickname is public, so search and lists show it
to anybody; what a person *did* is behind `can_view_activity`."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web

from bot.db.repo import Repo
from bot.db.repo._follows import PersonRow
from bot.i18n import gettext
from bot.services.people import ACTIVITY_CHOICES, Relation

log = logging.getLogger(__name__)

RequireUser = Callable[[web.Request], Awaitable[Any]]


def _relation_json(relation: Relation) -> dict[str, bool]:
    return {
        "following": relation.following,
        "followed_by": relation.followed_by,
        "friends": relation.friends,
        "blocked": relation.blocked,
    }


def person_json(row: PersonRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "tg_id": row.tg_id,
        "handle": row.handle,
        "relation": _relation_json(row.relation),
    }


def register(app: web.Application, require_user: RequireUser) -> None:
    """Add the routes. `require_user` is the Mini API's own Init Data check, passed
    in rather than imported to keep this module out of an import cycle."""

    async def me_id(request: web.Request) -> tuple[Repo, int]:
        user = await require_user(request)
        repo: Repo = request.app["mini_repo"]
        await repo.ensure_user(user.tg_id, user.username)
        person = await repo.person_id(user.tg_id)
        if person is None:
            raise web.HTTPNotFound(text="no person")
        return repo, person

    def target_id(request: web.Request) -> int:
        try:
            return int(request.match_info["person_id"])
        except ValueError as exc:
            raise web.HTTPBadRequest(text="bad person id") from exc

    async def search(request: web.Request) -> web.Response:
        repo, me = await me_id(request)
        rows = await repo.search_people(me, request.query.get("q", ""))
        return web.json_response({"people": [person_json(row) for row in rows]})

    async def suggestions(request: web.Request) -> web.Response:
        repo, me = await me_id(request)
        rows = await repo.suggested_people(me)
        return web.json_response({"people": [person_json(row) for row in rows]})

    async def following(request: web.Request) -> web.Response:
        repo, me = await me_id(request)
        rows = await repo.following_of(me)
        return web.json_response({"people": [person_json(row) for row in rows]})

    async def followers(request: web.Request) -> web.Response:
        repo, me = await me_id(request)
        rows = await repo.followers_of(me)
        return web.json_response({"people": [person_json(row) for row in rows]})

    async def blocked(request: web.Request) -> web.Response:
        repo, me = await me_id(request)
        rows = await repo.blocked_by(me)
        return web.json_response({"people": [person_json(row) for row in rows]})

    async def profile_by_tg(request: web.Request) -> web.Response:
        """The same card, asked for by the Telegram id a feed item carries."""
        repo, _me = await me_id(request)
        try:
            tg_id = int(request.match_info["tg_id"])
        except ValueError as exc:
            raise web.HTTPBadRequest(text="bad tg_id") from exc
        person = await repo.person_id(tg_id)
        if person is None:
            raise web.HTTPNotFound(text="no such person")
        return await profile(request, person)

    async def profile(request: web.Request, person: int | None = None) -> web.Response:
        repo, me = await me_id(request)
        other = person if person is not None else target_id(request)
        row = await repo.person_with_relation(me, other)
        if row is None:
            raise web.HTTPNotFound(text="no such person")
        relation = row.relation
        if relation.blocked_by:
            # Someone who blocked you is simply not there.
            raise web.HTTPNotFound(text="no such person")
        followers_count, following_count = await repo.follow_counts(other)
        can_view = await repo.can_view_activity(me, other)
        return web.json_response(
            {
                **person_json(row),
                "followers": followers_count,
                "following": following_count,
                "can_view": can_view,
                "activity": await _activity(request, repo, me, other) if can_view else None,
            }
        )

    async def follow(request: web.Request) -> web.Response:
        repo, me = await me_id(request)
        other = target_id(request)
        if await repo.follow(me, other):
            await _tell_new_follower(request, repo, me, other)
        return web.json_response({"relation": _relation_json(await repo.relation(me, other))})

    async def unfollow(request: web.Request) -> web.Response:
        repo, me = await me_id(request)
        other = target_id(request)
        await repo.unfollow(me, other)
        return web.json_response({"relation": _relation_json(await repo.relation(me, other))})

    async def block(request: web.Request) -> web.Response:
        repo, me = await me_id(request)
        other = target_id(request)
        await repo.block(me, other)
        return web.json_response({"relation": _relation_json(await repo.relation(me, other))})

    async def unblock(request: web.Request) -> web.Response:
        repo, me = await me_id(request)
        other = target_id(request)
        await repo.unblock(me, other)
        return web.json_response({"relation": _relation_json(await repo.relation(me, other))})

    async def put_activity(request: web.Request) -> web.Response:
        repo, me = await me_id(request)
        try:
            body = await request.json()
            value = str(body["activity_visible"])
        except Exception as exc:
            raise web.HTTPBadRequest(text="invalid json") from exc
        if value not in ACTIVITY_CHOICES:
            raise web.HTTPBadRequest(text="bad activity_visible")
        await repo.set_activity_visible(me, value)
        return web.json_response({"activity_visible": value})

    async def get_activity(request: web.Request) -> web.Response:
        repo, me = await me_id(request)
        return web.json_response({"activity_visible": await repo.activity_visible(me)})

    router = app.router
    router.add_get("/api/mini/people/search", search)
    router.add_get("/api/mini/people/suggestions", suggestions)
    router.add_get("/api/mini/people/tg/{tg_id}", profile_by_tg)
    router.add_get("/api/mini/people/{person_id}", profile)
    router.add_post("/api/mini/people/{person_id}/follow", follow)
    router.add_delete("/api/mini/people/{person_id}/follow", unfollow)
    router.add_post("/api/mini/people/{person_id}/block", block)
    router.add_delete("/api/mini/people/{person_id}/block", unblock)
    router.add_get("/api/mini/me/following", following)
    router.add_get("/api/mini/me/followers", followers)
    router.add_get("/api/mini/me/blocked", blocked)
    router.add_get("/api/mini/me/privacy", get_activity)
    router.add_put("/api/mini/me/privacy", put_activity)


async def _activity(request: web.Request, repo: Repo, me: int, other: int) -> dict[str, Any] | None:
    """What the person card shows of someone's play: now, the accounts with their
    counts, this month, and the latest unlocks. Only called once the privacy
    check has passed."""
    from bot.web.mini_chat import build_person_payload

    target_row = await repo.person_row(other)
    if target_row is None or target_row.tg_id is None:
        return None
    target = await repo.get_user(target_row.tg_id)
    viewer_row = await repo.person_row(me)
    settings = (
        await repo.get_user_settings(viewer_row.tg_id) if viewer_row and viewer_row.tg_id else None
    )
    if target is None:
        return None
    payload = await build_person_payload(repo, target, locale=settings.locale if settings else "ru")
    return {
        "presence": payload.get("presence"),
        "platforms": payload["platforms"],
        "month": payload["month"],
        "games": _month_games(payload["feed"]),
    }


def _month_games(feed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The games behind this month's unlocks, most recently played first, each
    with how many it gave — the card's horizontal strip."""
    games: dict[tuple[str, str], dict[str, Any]] = {}
    for item in feed:
        key = (item["platform"], item["title_id"])
        if not item.get("game"):
            continue
        game = games.setdefault(
            key,
            {
                "platform": item["platform"],
                "title_id": item["title_id"],
                "name": item["game"],
                "cover": item.get("game_icon_url"),
                "count": 0,
            },
        )
        game["count"] += 1
    return list(games.values())


async def _tell_new_follower(request: web.Request, repo: Repo, me: int, other: int) -> None:
    """A direct message to the person just followed. Best-effort: they may not
    have Telegram at all, or have blocked the bot, and neither may undo a follow.
    Friends' achievements are never sent this way, only this one notice."""
    bot = request.app.get("mini_bot")
    if bot is None:
        return
    target = await repo.person_row(other)
    follower = await repo.person_row(me)
    if target is None or follower is None or target.tg_id is None:
        return
    relation = await repo.relation(other, me)
    settings = await repo.get_user_settings(target.tg_id)
    if settings is not None and not settings.notify_followers:
        return
    locale = settings.locale if settings else "ru"
    key = "people-new-friend" if relation.friends else "people-new-follower"
    try:
        await bot.send_message(
            target.tg_id, gettext("people", key, locale=locale, name=follower.handle)
        )
    except Exception as exc:
        # They may have blocked the bot or never started it; the follow stands.
        log.info("new-follower notice to tg_id=%s not sent: %r", target.tg_id, exc)
