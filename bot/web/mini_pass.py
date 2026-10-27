"""The season pass in the Mini App (owner, 2026-10-27): where the month's
points stand, which themes are claimed, and claiming one — checked here, so a
theme cannot be opened by editing the page."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from bot.db.repo import Repo
from bot.services import season_pass
from bot.util import utcnow
from bot.web.mini_chat import _person_month


def setup_pass_routes(app: web.Application) -> None:
    app.router.add_get("/api/mini/pass", handle_pass)
    app.router.add_post("/api/mini/pass/claim", handle_claim)


async def _state(repo: Repo, person_id: int) -> dict[str, Any]:
    month, since, until, _current, _n = await _person_month(repo, person_id, None)
    points = await repo.points_for_person(person_id, since, until)
    claimed = await repo.pass_claims(person_id)
    return {
        "ok": True,
        "month": month,
        "points": points,
        "days_left": max(1, -(-int((until - utcnow()).total_seconds()) // 86400)),
        "tiers": [
            {
                "level": t.level,
                "points": t.points,
                "tier": t.tier,
                "palette": t.palette,
                "claimed": t.palette in claimed,
            }
            for t in season_pass.TIERS
        ],
    }


async def _person(request: web.Request) -> tuple[Repo, int]:
    from bot.web.mini_api import _require_user

    user = await _require_user(request)
    if user.person_id is None:
        raise web.HTTPForbidden(text="no person")
    return request.app["mini_repo"], user.person_id


async def _tier(request: web.Request) -> season_pass.Tier:
    try:
        body = await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text="bad json") from None
    tier = season_pass.tier_of(str(body.get("palette") or ""))
    if tier is None:
        raise web.HTTPBadRequest(text="unknown palette")
    return tier


async def handle_pass(request: web.Request) -> web.Response:
    repo, person_id = await _person(request)
    return web.json_response(await _state(repo, person_id))


async def handle_claim(request: web.Request) -> web.Response:
    repo, person_id = await _person(request)
    tier = await _tier(request)
    state = await _state(repo, person_id)
    if state["points"] < tier.points:
        return web.json_response({"ok": False, "error": "not_reached"}, status=403)
    await repo.set_pass_claim(person_id, tier.palette, state["month"], True)
    return web.json_response(await _state(repo, person_id))
