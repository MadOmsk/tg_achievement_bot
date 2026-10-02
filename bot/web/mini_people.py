"""Mini API for people (#157): search, follows, followers, blocks, a profile card.

Every route here speaks in person ids (`users.id`); `tg_id` is sent along only so
the app can ask for an avatar. A nickname is public, so search and lists show it
to anybody; what a person *did* is behind `can_view_activity`."""

from __future__ import annotations

import contextlib
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

    async def profile(request: web.Request) -> web.Response:
        repo, me = await me_id(request)
        other = target_id(request)
        row = await repo.person_with_relation(me, other)
        if row is None:
            raise web.HTTPNotFound(text="no such person")
        relation = row.relation
        if relation.blocked_by:
            # Someone who blocked you is simply not there.
            raise web.HTTPNotFound(text="no such person")
        followers_count, following_count = await repo.follow_counts(other)
        return web.json_response(
            {
                **person_json(row),
                "followers": followers_count,
                "following": following_count,
                "can_view": await repo.can_view_activity(me, other),
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

    async def remove_follower(request: web.Request) -> web.Response:
        repo, me = await me_id(request)
        other = target_id(request)
        await repo.remove_follower(me, other)
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
    router.add_get("/api/mini/people/{person_id}", profile)
    router.add_post("/api/mini/people/{person_id}/follow", follow)
    router.add_delete("/api/mini/people/{person_id}/follow", unfollow)
    router.add_delete("/api/mini/people/{person_id}/follower", remove_follower)
    router.add_post("/api/mini/people/{person_id}/block", block)
    router.add_delete("/api/mini/people/{person_id}/block", unblock)
    router.add_get("/api/mini/me/following", following)
    router.add_get("/api/mini/me/followers", followers)
    router.add_get("/api/mini/me/blocked", blocked)
    router.add_get("/api/mini/me/privacy", get_activity)
    router.add_put("/api/mini/me/privacy", put_activity)


async def _tell_new_follower(request: web.Request, repo: Repo, me: int, other: int) -> None:
    """A direct message to the person just followed. Best-effort: they may not
    have Telegram at all, or have blocked the bot, and neither may undo a follow.
    Friends' achievements are never sent this way, only this one notice."""
    bot = request.app.get("mini_bot")
    if bot is None:
        return
    with contextlib.suppress(Exception):
        target = await repo.person_row(other)
        follower = await repo.person_row(me)
        if target is None or follower is None or target.tg_id is None:
            return
        relation = await repo.relation(other, me)
        settings = await repo.get_user_settings(target.tg_id)
        locale = settings.locale if settings else "ru"
        key = "people-new-friend" if relation.friends else "people-new-follower"
        await bot.send_message(
            target.tg_id, gettext("people", key, locale=locale, name=follower.handle)
        )
