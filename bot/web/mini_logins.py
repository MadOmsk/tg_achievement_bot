"""The ways a person gets in (#162): signing in by email, and the logins a
signed-in person keeps — an email address and a Telegram account, either of
which may come first.

Sign-in by email: `POST /api/mini/auth/email/start` sends a code,
`POST /api/mini/auth/email/verify` checks it and opens a session — for the
person with that address, or a new person when nobody has it yet.

Settings → «Вход»: `GET /api/mini/me/logins`; `POST /api/mini/me/email/start`
and `/verify` add or change the address — never remove it: email is the main
way in (owner, 2026-10-05); `POST /api/mini/me/telegram` adds a Telegram account
through the Login Widget. An address or a Telegram
account that already belongs to somebody else is refused (`taken`): joining two
people is a merge, a separate request of the person's own.

Answers that need wording carry an `error` code for the Mini App to word
itself: `invalid`, `too_soon` (with `retry_after` seconds), `unavailable` (no
mail server), `send_failed`, `wrong_code` (with `attempts_left`), `expired`,
`taken`, `already`, `last_login`, `admin`, `in_telegram`, `not_linked`.

`DELETE /api/mini/me/telegram` takes Telegram away while an address is left to
sign in with — never from a super-admin, and only from a browser (see
`_telegram_blocked`).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web

from bot.config import Settings
from bot.db.repo import LoginTaken, Repo, User
from bot.i18n import normalize_locale
from bot.services import email_login
from bot.services.email import EmailSendError, build_sender
from bot.services.email_login import (
    CodeExpired,
    CodeWrong,
    EmailInvalid,
    EmailLogin,
    EmailTooSoon,
)
from bot.web.mini_auth import InitDataError, MiniAppUser, validate_login_widget
from bot.web.mini_session import start_session

log = logging.getLogger(__name__)


def forget_file(relative: str) -> None:
    """The Telegram photo kept on disk goes with the Telegram account."""
    from bot.services.avatars import avatar_dir

    try:
        path = avatar_dir() / relative
        if path.is_file():
            path.unlink()
    except OSError:
        log.warning("could not remove the Telegram photo %s", relative)


RequireUser = Callable[[web.Request], Awaitable[MiniAppUser]]


def build_email_login(settings: Settings, repo: Repo) -> EmailLogin | None:
    """The email sign-in, or None when there is no way to send mail. The codes'
    HMAC key is derived from FERNET_KEY, the one secret every install has."""
    sender = build_sender(settings)
    if sender is None:
        return None
    secret = hashlib.sha256(
        b"email-codes:" + settings.fernet_key.get_secret_value().encode()
    ).digest()
    return EmailLogin(repo, sender, secret)


def _error(code: str, status: int, **extra: Any) -> web.Response:
    return web.json_response({"error": code, **extra}, status=status)


async def _body(request: web.Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as exc:
        raise web.HTTPBadRequest(text="invalid json") from exc
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(text="invalid json")
    return body


async def _send(
    request: web.Request,
    purpose: str,
    raw_email: str,
    locale: str,
    person_id: int | None = None,
) -> web.Response:
    login: EmailLogin | None = request.app.get("mini_email_login")
    if login is None:
        return _error("unavailable", 503)
    try:
        await login.send_code(raw_email, purpose, locale=locale, person_id=person_id)
    except EmailInvalid:
        return _error("invalid", 400)
    except EmailTooSoon as exc:
        return _error("too_soon", 429, retry_after=exc.retry_after)
    except EmailSendError as exc:
        log.warning("sign-in code not sent: %s", exc)
        return _error("send_failed", 502)
    return web.json_response({"ok": True, "resend_after": email_login.RESEND_SECONDS})


async def _check(
    request: web.Request, purpose: str, body: dict[str, Any], person_id: int | None = None
) -> str | web.Response:
    login: EmailLogin | None = request.app.get("mini_email_login")
    if login is None:
        return _error("unavailable", 503)
    try:
        return await login.check_code(
            str(body.get("email", "")), str(body.get("code", "")), purpose, person_id=person_id
        )
    except EmailInvalid:
        return _error("invalid", 400)
    except CodeWrong as exc:
        return _error("wrong_code", 400, attempts_left=exc.attempts_left)
    except CodeExpired:
        return _error("expired", 410)


def register(app: web.Application, require_user: RequireUser) -> None:
    """Add the routes. `require_user` is the Mini API's own check, passed in to
    keep this module out of an import cycle."""

    async def sign_in_start(request: web.Request) -> web.Response:
        body = await _body(request)
        locale = normalize_locale(str(body.get("locale") or "ru"))
        return await _send(request, email_login.SIGN_IN, str(body.get("email", "")), locale)

    async def sign_in_verify(request: web.Request) -> web.Response:
        repo: Repo = request.app["mini_repo"]
        body = await _body(request)
        checked = await _check(request, email_login.SIGN_IN, body)
        if isinstance(checked, web.Response):
            return checked
        person = await repo.person_by_email(checked)
        if person is None:
            person = await repo.create_email_person(checked)
            locale = body.get("locale")
            if locale:
                await repo.update_user_settings(person, locale=normalize_locale(str(locale)))
            await repo.give_handle(person)
            log.info("new person_id=%s signed up by email", person)
        return await start_session(request, repo, person)

    async def logins(request: web.Request) -> web.Response:
        user = await require_user(request)
        repo: Repo = request.app["mini_repo"]
        return web.json_response(await _logins_payload(request, repo, user.person_id))

    async def email_start(request: web.Request) -> web.Response:
        user = await require_user(request)
        repo: Repo = request.app["mini_repo"]
        body = await _body(request)
        try:
            address = email_login.normalize_email(str(body.get("email", "")))
        except EmailInvalid:
            return _error("invalid", 400)
        owner = await repo.person_by_email(address)
        if owner is not None and owner != user.person_id:
            return _error("taken", 409)
        locale = await repo.user_locale(user.person_id)
        return await _send(request, email_login.LINK, address, locale, user.person_id)

    async def email_verify(request: web.Request) -> web.Response:
        user = await require_user(request)
        repo: Repo = request.app["mini_repo"]
        body = await _body(request)
        checked = await _check(request, email_login.LINK, body, user.person_id)
        if isinstance(checked, web.Response):
            return checked
        try:
            await repo.set_email(user.person_id, checked)
        except LoginTaken:
            return _error("taken", 409)
        return web.json_response(await _logins_payload(request, repo, user.person_id))

    async def telegram_link(request: web.Request) -> web.Response:
        user = await require_user(request)
        repo: Repo = request.app["mini_repo"]
        settings: Settings = request.app["mini_settings"]
        if user.tg_id is not None:
            return _error("already", 409)
        body = await _body(request)
        try:
            widget = validate_login_widget(body, settings.bot_token.get_secret_value())
        except InitDataError as exc:
            log.info("telegram link rejected: %s", exc)
            raise web.HTTPUnauthorized(text="invalid login") from exc
        try:
            await repo.set_telegram(
                user.person_id,
                widget.tg_id,
                widget.username,
                widget.first_name,
                widget.last_name,
            )
        except LoginTaken:
            return _error("taken", 409)
        log.info("person_id=%s added a Telegram account", user.person_id)
        return web.json_response(await _logins_payload(request, repo, user.person_id))

    async def telegram_remove(request: web.Request) -> web.Response:
        user = await require_user(request)
        repo: Repo = request.app["mini_repo"]
        person = await repo.get_user(user.person_id)
        if person is None or person.tg_id is None:
            return _error("not_linked", 409)
        blocked = _telegram_blocked(request, person)
        if blocked is not None:
            return _error(blocked, 409)
        photo = await repo.remove_telegram(user.person_id)
        if photo:
            forget_file(photo)
        log.info("person_id=%s removed their Telegram account", user.person_id)
        return web.json_response(await _logins_payload(request, repo, user.person_id))

    app.router.add_post("/api/mini/auth/email/start", sign_in_start)
    app.router.add_post("/api/mini/auth/email/verify", sign_in_verify)
    app.router.add_get("/api/mini/me/logins", logins)
    app.router.add_post("/api/mini/me/email/start", email_start)
    app.router.add_post("/api/mini/me/email/verify", email_verify)
    app.router.add_post("/api/mini/me/telegram", telegram_link)
    app.router.add_delete("/api/mini/me/telegram", telegram_remove)


def _telegram_blocked(request: web.Request, user: User | None) -> str | None:
    """Why Telegram may not be taken away right now, or None if it may:
    `last_login` — without an address there would be no way in; `admin` — a
    super-admin is named by Telegram id and must keep one; `in_telegram` — the app
    opened in Telegram signs in with that very account, and would come back as a
    new person the moment it is gone, so it is done from a browser."""
    settings: Settings = request.app["mini_settings"]
    if user is None or user.tg_id is None:
        return None
    if not user.email:
        return "last_login"
    if settings.is_admin(user.tg_id):
        return "admin"
    if request.headers.get("X-Telegram-Init-Data"):
        return "in_telegram"
    return None


async def _logins_payload(request: web.Request, repo: Repo, person_id: int) -> dict[str, Any]:
    user = await repo.get_user(person_id)
    has_telegram = bool(user and user.tg_id is not None)
    return {
        "email": user.email if user else None,
        "telegram": {
            "linked": has_telegram,
            "username": user.username if user and has_telegram else None,
            # Whether it may be taken away, and if not, why (`_telegram_blocked`).
            "removable": has_telegram and _telegram_blocked(request, user) is None,
            "blocked": _telegram_blocked(request, user) if has_telegram else None,
        },
        # Whether a code can be sent at all; without a mail server the address
        # can still be seen and removed, not added.
        "email_available": request.app.get("mini_email_login") is not None,
    }
