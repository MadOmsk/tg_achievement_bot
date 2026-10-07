"""Browser sign-in for the Mini App (#157): Telegram Login in a plain browser
(email is `mini_logins.py`, #162), a server session in an HttpOnly cookie, and
the way out.

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
    person = await repo.session_person(token)
    user = await repo.get_user(person) if person is not None else None
    if user is None:
        return None
    return MiniAppUser(
        tg_id=user.tg_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=None,
        is_premium=False,
        person_id=user.id,
    )


async def start_session(request: web.Request, repo: Repo, person: int) -> web.Response:
    """Sign the browser in as `person`: a new session and its cookie."""
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
        settings: Settings = request.app["mini_settings"]
        # The bot's id is public (the part of its token before the colon):
        # Telegram's own sign-in page takes it, for a sign-in in the same tab.
        bot_id = settings.bot_token.get_secret_value().split(":", 1)[0]
        return web.json_response(
            {
                "bot_username": username,
                "bot_id": int(bot_id) if bot_id.isdigit() else None,
                # Whether a mail server is set up (#162): without one the
                # sign-in screen offers Telegram only.
                "email": request.app.get("mini_email_login") is not None,
            }
        )

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
        person = await repo.person_id(user.tg_id)
        if person is None:
            # Somebody new: only with an invite, for now (owner, 2026-10-05).
            # Imported here: mini_invites itself opens sessions through this module.
            from bot.web.mini_invites import sign_up

            proof = {
                "kind": "telegram",
                "tg_id": user.tg_id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
            }
            return await sign_up(request, proof, body.get("invite"))
        # Known already: keep Telegram's names fresh.
        await repo.ensure_user(user.tg_id, user.username, user.first_name, user.last_name)
        return await start_session(request, repo, person)

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
