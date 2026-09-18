"""HowLongToBeat search/resolve for the Mini App. Cache-or-fetch, never a secret."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from bot.db.repo import Repo
from bot.services.hltb import HltbError, HltbResult, overlay_cache, resolve, search
from bot.services.translate.auth import AnthropicAuth

DESCRIPTION_LIMIT = 800


def _as_payload(result: HltbResult, *, locale: str) -> dict[str, Any]:
    description = result.description(locale)
    if description and len(description) > DESCRIPTION_LIMIT:
        description = description[: DESCRIPTION_LIMIT - 1].rstrip() + "…"
    return {
        "hltb_id": result.hltb_id,
        "name": result.name,
        "release_year": result.release_year,
        "main_hours": result.main_hours,
        "extra_hours": result.extra_hours,
        "completionist_hours": result.completionist_hours,
        "platforms": result.platforms,
        "game_url": result.game_url,
        "image_url": result.image_url,
        "genre": result.genre,
        "description": description,
    }


def setup_hltb_routes(app: web.Application) -> None:
    app.router.add_get("/api/mini/hltb", handle_hltb_search)
    app.router.add_get(r"/api/mini/hltb/{hltb_id:\d+}", handle_hltb_resolve)


async def handle_hltb_search(request: web.Request) -> web.Response:
    from bot.web.mini_api import _require_user

    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    query = (request.query.get("q") or "").strip()
    if len(query) < 2:
        raise web.HTTPBadRequest(text="query too short")
    locale = await repo.user_locale(user.tg_id)
    try:
        results = await overlay_cache(repo, await search(query))
    except HltbError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=502)
    return web.json_response({"results": [_as_payload(item, locale=locale) for item in results]})


async def handle_hltb_resolve(request: web.Request) -> web.Response:
    from bot.web.mini_api import _require_user

    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    locale = await repo.user_locale(user.tg_id)
    anthropic: AnthropicAuth | None = request.app.get("mini_anthropic_auth")
    try:
        result = await resolve(repo, int(request.match_info["hltb_id"]), anthropic_auth=anthropic)
    except HltbError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=502)
    return web.json_response(_as_payload(result, locale=locale))
