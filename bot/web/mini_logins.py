"""The ways a person gets in (#162): signing in by email, and the logins a
signed-in person keeps — an email address and a Telegram account, either of
which may come first.

Sign-in by email: `POST /api/mini/auth/email/start` sends a code,
`POST /api/mini/auth/email/verify` checks it and opens a session — for the
person with that address, or a new person when nobody has it yet, who needs an
invite (`web/mini_invites.py`).

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

**Merging** (`services/merge.py`): adding a login that belongs to somebody
else answers `taken` with a `merge` preview — the same human, proved by the code
or the signature — and the offer waits: `GET /api/mini/me/merge` shows it,
`POST` performs it with the person's `choices`, `DELETE` turns it down.
`GET /api/mini/me/telegram/link` gives a `t.me/<bot>?start=link_<token>` link that
adds Telegram by writing to the bot from it.

`DELETE /api/mini/me/telegram` takes Telegram away while an address is left to
sign in with — never from a super-admin, and only from a browser (see
`_telegram_blocked`).
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web

from bot.config import Settings
from bot.db.repo import LoginTaken, Repo, User
from bot.i18n import normalize_locale
from bot.services import email_login
from bot.services.admin_settings import (
    DEFAULT_EMAIL_CHECKS_PER_CLIENT,
    DEFAULT_EMAIL_SENDS_PER_CLIENT,
    DEFAULT_EMAIL_SENDS_TOTAL,
    EMAIL_CHECKS_PER_CLIENT_KEY,
    EMAIL_SENDS_PER_CLIENT_KEY,
    EMAIL_SENDS_TOTAL_KEY,
)
from bot.services.crypto import TokenCipher
from bot.services.email import EmailSendError, build_sender
from bot.services.email_login import (
    CodeExpired,
    CodeWrong,
    EmailInvalid,
    EmailLogin,
    EmailTooSoon,
    TrustingEmailLogin,
)
from bot.services.merge import MergeRefused
from bot.services.smtp_auth import SmtpAuth
from bot.web.mini_auth import InitDataError, MiniAppUser, validate_login_widget
from bot.web.mini_invites import sign_up
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


def build_email_login(
    settings: Settings, repo: Repo, *, smtp_auth: SmtpAuth | None = None
) -> EmailLogin | None:
    """The email sign-in, or None when there is no way to send mail. The codes'
    HMAC key is derived from FERNET_KEY, the one secret every install has."""
    if settings.email_skip_code:
        if settings.smtp_host:
            log.error("EMAIL_SKIP_CODE is ignored: a mail server is configured (SMTP_HOST)")
        else:
            log.warning(
                "EMAIL_SKIP_CODE is on: an email address signs in with no code. "
                "Development only — never on a server."
            )
            return TrustingEmailLogin(repo)
    # The login the super-admin set in /admin, read on every message — the
    # bot's own SmtpAuth when there is one, so a clear in the panel is seen
    # here too (a second instance would seed the env login back in).
    if smtp_auth is None:
        smtp_auth = SmtpAuth(repo, TokenCipher(settings.fernet_key.get_secret_value()), settings)
    sender = build_sender(settings, smtp_auth.credentials)
    if sender is None:
        return None
    secret = hashlib.sha256(
        b"email-codes:" + settings.fernet_key.get_secret_value().encode()
    ).digest()
    return EmailLogin(repo, sender, secret)


class _Throttle:
    """At most `limit` events per key in a sliding `window` seconds, in memory.
    The per-address limits of `services/email_login.py` stop a mailbox from
    being flooded; these stop one client from going through many addresses
    (sending mail in our name) or guessing codes in bulk. The limit is read
    from the admin's settings on every call, so a change applies at once."""

    def __init__(self, setting: str, default: int, window: float) -> None:
        self.setting = setting
        self.default = default
        self.window = window
        self._events: dict[str, deque[float]] = {}

    def retry_after(self, key: str, limit: int) -> int:
        """0 and the event counted, or how many seconds until one more is allowed."""
        now = time.monotonic()
        events = self._events.setdefault(key, deque())
        while events and now - events[0] >= self.window:
            events.popleft()
        if len(events) >= limit:
            return max(1, int(self.window - (now - events[0])) + 1)
        events.append(now)
        if len(self._events) > 10_000:
            # Forget keys whose window has passed, so the dict stays small.
            for stale in [
                k for k, v in self._events.items() if not v or now - v[-1] >= self.window
            ]:
                del self._events[stale]
        return 0


THROTTLES = "mini_login_throttles"


def _client(request: web.Request) -> str:
    """Who is asking: nginx's X-Real-IP (it overwrites any the client sent),
    else the socket's peer."""
    return request.headers.get("X-Real-IP") or request.remote or "?"


async def _throttled(request: web.Request, *names: str) -> web.Response | None:
    repo: Repo = request.app["mini_repo"]
    for name in names:
        throttle: _Throttle = request.app[THROTTLES][name]
        limit = await repo.get_int_setting(throttle.setting, throttle.default)
        key = "all" if name == "sends_total" else _client(request)
        wait = throttle.retry_after(key, limit)
        if wait:
            log.info("email sign-in throttled for %s (%ss)", key, wait)
            return _error("too_soon", 429, retry_after=wait)
    return None


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
    if not login.skips_code and (refused := await _throttled(request, "sends", "sends_total")):
        return refused
    try:
        await login.send_code(raw_email, purpose, locale=locale, person_id=person_id)
    except EmailInvalid:
        return _error("invalid", 400)
    except EmailTooSoon as exc:
        return _error("too_soon", 429, retry_after=exc.retry_after)
    except EmailSendError as exc:
        log.warning("sign-in code not sent: %s", exc)
        return _error("send_failed", 502)
    return web.json_response(
        # `skip_code`: the dev server's no-code mode — the app goes straight on.
        {"ok": True, "resend_after": email_login.RESEND_SECONDS, "skip_code": login.skips_code}
    )


async def _check(
    request: web.Request, purpose: str, body: dict[str, Any], person_id: int | None = None
) -> str | web.Response:
    login: EmailLogin | None = request.app.get("mini_email_login")
    if login is None:
        return _error("unavailable", 503)
    if not login.skips_code and (refused := await _throttled(request, "checks")):
        return refused
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
    # Kept on the app, so each app (and each test's) starts with clean counts.
    app[THROTTLES] = {
        "sends": _Throttle(EMAIL_SENDS_PER_CLIENT_KEY, DEFAULT_EMAIL_SENDS_PER_CLIENT, 3600),
        "sends_total": _Throttle(EMAIL_SENDS_TOTAL_KEY, DEFAULT_EMAIL_SENDS_TOTAL, 3600),
        "checks": _Throttle(EMAIL_CHECKS_PER_CLIENT_KEY, DEFAULT_EMAIL_CHECKS_PER_CLIENT, 600),
    }

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
            # Somebody new: only with an invite, for now (owner, 2026-10-05).
            proof = {"kind": "email", "email": checked, "locale": body.get("locale")}
            return await sign_up(request, proof, body.get("invite"))
        return await start_session(request, repo, person)

    async def email_later(request: web.Request) -> web.Response:
        user = await require_user(request)
        repo: Repo = request.app["mini_repo"]
        await repo.put_off_email_prompt(user.person_id)
        return web.json_response({"ok": True})

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
        # An address somebody else signs in with still gets its code: typing it
        # back proves this person reads that mailbox, and then the two may merge.
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
            owner = await repo.person_by_email(checked)
            return await _offer_merge(request, user.person_id, owner)
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
            owner = await repo.person_id(widget.tg_id)
            return await _offer_merge(request, user.person_id, owner)
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

    async def telegram_link_url(request: web.Request) -> web.Response:
        """A `t.me` link that adds Telegram by writing to the bot from it — for a
        phone, or a host the Login Widget does not render on."""
        user = await require_user(request)
        if user.tg_id is not None:
            return _error("already", 409)
        merge = request.app.get("mini_merge")
        bot_username = await _bot_username(request)
        if merge is None or not bot_username:
            return _error("unavailable", 503)
        token = merge.link_token(user.person_id)
        return web.json_response({"url": f"https://t.me/{bot_username}?start=link_{token}"})

    async def merge_get(request: web.Request) -> web.Response:
        user = await require_user(request)
        merge = request.app.get("mini_merge")
        absorb = merge.pending(user.person_id) if merge else None
        preview = await merge.preview(user.person_id, absorb) if absorb else None
        return web.json_response({"merge": preview})

    async def merge_do(request: web.Request) -> web.Response:
        user = await require_user(request)
        repo: Repo = request.app["mini_repo"]
        merge = request.app.get("mini_merge")
        absorb = merge.pending(user.person_id) if merge else None
        if merge is None or absorb is None:
            return _error("expired", 410)
        body = await _body(request)
        try:
            await merge.merge(user.person_id, absorb, body.get("choices") or {})
        except MergeRefused as exc:
            return _error(exc.reason, 409)
        return web.json_response(await _logins_payload(request, repo, user.person_id))

    async def merge_cancel(request: web.Request) -> web.Response:
        user = await require_user(request)
        merge = request.app.get("mini_merge")
        if merge is not None:
            merge.drop(user.person_id)
        return web.json_response({"ok": True})

    app.router.add_post("/api/mini/auth/email/start", sign_in_start)
    app.router.add_post("/api/mini/auth/email/verify", sign_in_verify)
    app.router.add_get("/api/mini/me/logins", logins)
    app.router.add_post("/api/mini/me/email/start", email_start)
    app.router.add_post("/api/mini/me/email/verify", email_verify)
    app.router.add_post("/api/mini/me/email/later", email_later)
    app.router.add_post("/api/mini/me/telegram", telegram_link)
    app.router.add_delete("/api/mini/me/telegram", telegram_remove)
    app.router.add_get("/api/mini/me/telegram/link", telegram_link_url)
    app.router.add_get("/api/mini/me/merge", merge_get)
    app.router.add_post("/api/mini/me/merge", merge_do)
    app.router.add_delete("/api/mini/me/merge", merge_cancel)


async def _offer_merge(request: web.Request, keep: int, absorb: int | None) -> web.Response:
    """The login just proved belongs to somebody else: the same human, so offer
    to make the two one (`services/merge.py`). Without the merge service it is a
    plain refusal."""
    merge = request.app.get("mini_merge")
    if merge is None or absorb is None or absorb == keep:
        return _error("taken", 409)
    merge.offer(keep, absorb)
    return _error("taken", 409, merge=await merge.preview(keep, absorb))


async def _bot_username(request: web.Request) -> str | None:
    username = request.app.get("mini_bot_username")
    bot = request.app.get("mini_bot")
    if username is None and bot is not None:
        try:
            username = (await bot.me()).username
        except Exception:
            log.warning("could not read the bot's username for a Telegram link")
        request.app["mini_bot_username"] = username
    return username


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
    if settings.is_superadmin(user.tg_id):
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
        # A merge waiting for the person's word (#162), e.g. after linking
        # Telegram through the bot: the app opens it.
        "merge_pending": bool(
            request.app.get("mini_merge") and request.app["mini_merge"].pending(person_id)
        ),
        # Whether a code can be sent at all; without a mail server the address
        # can be seen, not added.
        "email_available": request.app.get("mini_email_login") is not None,
    }
