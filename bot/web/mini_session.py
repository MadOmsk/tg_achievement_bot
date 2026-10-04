"""Browser sign-in for the Mini App (#157): Telegram Login in a plain browser,
a server session in an HttpOnly cookie, and the way out.

Inside Telegram nothing changes — Init Data still signs every request. Here a
request with neither header falls back to the cookie. The cookie is SameSite=Lax
and the CORS layer never allows credentials, so another site can neither send nor
read it."""

from __future__ import annotations

import logging

from aiohttp import web

from bot.config import Settings
from bot.db.repo import Repo
from bot.web.mini_auth import InitDataError, MiniAppUser, validate_login_widget

log = logging.getLogger(__name__)

COOKIE = "ab_session"
COOKIE_MAX_AGE = 30 * 24 * 3600


async def session_user(request: web.Request) -> MiniAppUser | None:
    """Who the session cookie belongs to, or None."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    repo: Repo = request.app["mini_repo"]
    tg_id = await repo.session_tg_id(token)
    if tg_id is None:
        return None
    user = await repo.get_user(await repo.person_id(tg_id))
    if user is None:
        return None
    return MiniAppUser(
        tg_id=tg_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=None,
        is_premium=False,
        person_id=user.id,
    )


def register(app: web.Application) -> None:
    async def config(request: web.Request) -> web.Response:
        """What the sign-in screen needs: the bot the Login Widget belongs to."""
        username = request.app.get("mini_bot_username")
        bot = request.app.get("mini_bot")
        if username is None and bot is not None:
            try:
                username = (await bot.me()).username
            except Exception:
                log.warning("could not read the bot's username for the sign-in screen")
            request.app["mini_bot_username"] = username
        return web.json_response({"bot_username": username})

    async def login(request: web.Request) -> web.Response:
        settings: Settings = request.app["mini_settings"]
        repo: Repo = request.app["mini_repo"]
        try:
            body = await request.json()
            user = validate_login_widget(body, settings.bot_token.get_secret_value())
        except InitDataError as exc:
            log.info("telegram login rejected: %s", exc)
            raise web.HTTPUnauthorized(text="invalid login") from exc
        except Exception as exc:
            raise web.HTTPBadRequest(text="invalid json") from exc
        await repo.ensure_user(user.tg_id, user.username, user.first_name, user.last_name)
        person = await repo.person_id(user.tg_id)
        if person is None:
            raise web.HTTPNotFound(text="no person")
        token = await repo.create_session(person, request.headers.get("User-Agent"))
        response = web.json_response({"ok": True})
        response.set_cookie(
            COOKIE,
            token,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="Lax",
            secure=request.headers.get("X-Forwarded-Proto", request.scheme) == "https",
            path="/",
        )
        return response

    async def logout(request: web.Request) -> web.Response:
        repo: Repo = request.app["mini_repo"]
        token = request.cookies.get(COOKIE)
        if token:
            await repo.end_session(token)
        response = web.json_response({"ok": True})
        response.del_cookie(COOKIE, path="/")
        return response

    app.router.add_get("/api/mini/auth/config", config)
    app.router.add_post("/api/mini/auth/telegram", login)
    app.router.add_post("/api/mini/auth/logout", logout)
