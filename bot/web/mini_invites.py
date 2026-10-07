"""Invites in the Mini App (owner, 2026-10-05; `services/invites.py`).

Signing up in a browser takes a code. A sign-in that proved somebody new — an
email's code checked, or Telegram's Login Widget signed — and brought no usable
code answers `invite_required` (403) with a `signup` token; the person types the
code and `POST /api/mini/auth/signup` `{signup, invite}` finishes it. A code
already in hand (a shared link, `?invite=`) rides along with the sign-in itself
and no step is shown. `invite_invalid` is a code unknown or already spent;
`signup_expired` a token past its time.

A member's own codes: `GET /api/mini/me/invites`, `POST` makes one, `DELETE
/api/mini/me/invites/{code}` takes back an unused one.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web

from bot.config import Settings
from bot.db.repo import Repo
from bot.i18n import normalize_locale
from bot.services import invites
from bot.services.naming import person_name
from bot.web.mini_auth import MiniAppUser
from bot.web.mini_session import start_session

log = logging.getLogger(__name__)

PENDING_KEY = "mini_signups"

RequireUser = Callable[[web.Request], Awaitable[MiniAppUser]]


class _InviteSpent(Exception):
    """The code went to somebody else between the check and the sign-up."""


def _error(code: str, status: int, **extra: Any) -> web.Response:
    return web.json_response({"error": code, **extra}, status=status)


def _pending(app: web.Application) -> invites.PendingSignups:
    store = app.get(PENDING_KEY)
    if store is None:
        store = invites.PendingSignups()
        app[PENDING_KEY] = store
    return store


async def _existing(repo: Repo, proof: dict[str, Any]) -> int | None:
    """The person this proof already is — somebody may have come in meanwhile
    (written to the bot, say): then it is a sign-in, not a sign-up."""
    if proof["kind"] == "email":
        return await repo.person_by_email(proof["email"])
    return await repo.person_id(proof["tg_id"])


async def _create(repo: Repo, proof: dict[str, Any]) -> int | None:
    if proof["kind"] == "email":
        person = await repo.create_email_person(proof["email"])
        if proof.get("locale"):
            await repo.update_user_settings(person, locale=normalize_locale(str(proof["locale"])))
        await repo.give_handle(person)
        return person
    return await repo.ensure_user(
        proof["tg_id"], proof.get("username"), proof.get("first_name"), proof.get("last_name")
    )


async def sign_up(request: web.Request, proof: dict[str, Any], raw_invite: object) -> web.Response:
    """Let somebody new in with a code, or ask for one: what a sign-in calls once
    it has proved an address or a Telegram account nobody has yet."""
    repo: Repo = request.app["mini_repo"]
    code = invites.normalize(raw_invite)
    if code is not None and await repo.invite_usable(code):
        # The person and the spent code land together or not at all (#167).
        # This used to create, then delete the person again when the code had
        # gone a moment before — and a double submit of one proof could delete
        # the person the first request had just made.
        try:
            async with repo.transaction():
                person = await _create(repo, proof)
                if person is None:
                    raise web.HTTPNotFound(text="no person")
                if not await repo.redeem_invite(code, person):
                    raise _InviteSpent
        except _InviteSpent:
            return _error("invite_invalid", 400, signup=_pending(request.app).put(proof))
        except sqlite3.IntegrityError:
            # The same proof signed up a moment ago: that is who this is.
            existing = await _existing(repo, proof)
            if existing is None:
                raise
            return await start_session(request, repo, existing)
        log.info("new person_id=%s signed up (%s) with an invite", person, proof["kind"])
        return await start_session(request, repo, person)
    token = _pending(request.app).put(proof)
    if raw_invite:
        return _error("invite_invalid", 400, signup=token)
    return _error("invite_required", 403, signup=token)


def register(app: web.Application, require_user: RequireUser) -> None:
    _pending(app)

    async def finish(request: web.Request) -> web.Response:
        repo: Repo = request.app["mini_repo"]
        try:
            body = await request.json()
        except Exception as exc:
            raise web.HTTPBadRequest(text="invalid json") from exc
        if not isinstance(body, dict):
            raise web.HTTPBadRequest(text="invalid json")
        store = _pending(request.app)
        token = body.get("signup")
        proof = store.get(token)
        if proof is None:
            return _error("signup_expired", 410)
        existing = await _existing(repo, proof)
        if existing is not None:
            store.drop(str(token))
            return await start_session(request, repo, existing)
        answer = await sign_up(request, proof, body.get("invite"))
        if answer.status == 200:
            store.drop(str(token))
        return answer

    async def listing(request: web.Request) -> web.Response:
        user = await require_user(request)
        repo: Repo = request.app["mini_repo"]
        settings: Settings = request.app["mini_settings"]
        base = (settings.mini_app_url or "").strip()
        rows = await repo.invites_of(user.person_id)
        return web.json_response(
            {
                # Where a shared link opens, the code filled in; None to build it
                # from the page's own address.
                "link_base": base or None,
                "items": [
                    {
                        "code": row.code,
                        "created_at": row.created_at,
                        "used_at": row.used_at,
                        "used_by": (
                            {
                                "person_id": row.used_by,
                                "name": person_name(person_id=row.used_by, handle=row.used_handle),
                            }
                            if row.used_by is not None
                            else None
                        ),
                    }
                    for row in rows
                ],
            }
        )

    async def make(request: web.Request) -> web.Response:
        user = await require_user(request)
        repo: Repo = request.app["mini_repo"]
        code = invites.new_code()
        await repo.create_invite(user.person_id, code)
        return web.json_response({"code": code})

    async def take_back(request: web.Request) -> web.Response:
        user = await require_user(request)
        repo: Repo = request.app["mini_repo"]
        code = invites.normalize(request.match_info["code"])
        if code is None or not await repo.delete_invite(user.person_id, code):
            raise web.HTTPNotFound(text="no such invite")
        return web.json_response({"ok": True})

    app.router.add_post("/api/mini/auth/signup", finish)
    app.router.add_get("/api/mini/me/invites", listing)
    app.router.add_post("/api/mini/me/invites", make)
    app.router.add_delete("/api/mini/me/invites/{code}", take_back)
