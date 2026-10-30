"""A player's own PSN token in the Mini App (#233): add one to a linked PSN
account, remove it, or link a new PSN account by its token. The rules are
`services/psn/personal.py`'s; a token is never sent back, and a refusal is a
code the app words (`format`, `refused`, `mismatch` with the account the
token opens, `unavailable`, `not_linked`).
"""

from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from bot.constants import MAX_PSN_ACCOUNTS, Platform
from bot.db.repo import Repo
from bot.poller.psn_fetcher import PsnFetcher
from bot.services.psn.auth import STATUS_NOT_CONFIGURED, PsnAuth
from bot.services.psn.personal import PsnPersonalAuth, PsnTokenError
from bot.web.mini_auth import MiniAppUser

log = logging.getLogger(__name__)


def setup(app: web.Application) -> None:
    app.router.add_put("/api/mini/psn/token", handle_token_put)
    app.router.add_delete("/api/mini/psn/token", handle_token_delete)
    app.router.add_post("/api/mini/connect/psn-token", handle_connect_by_token)


def _personal(request: web.Request) -> PsnPersonalAuth:
    psn_auth: PsnAuth | None = request.app["mini_psn_auth"]
    if psn_auth is None or psn_auth.personal is None:
        raise web.HTTPServiceUnavailable(text="psn unavailable")
    return psn_auth.personal


def _refused(exc: PsnTokenError) -> web.Response:
    body: dict[str, object] = {"ok": False, "error": exc.code}
    if exc.online_id:
        body["other"] = exc.online_id
    return web.json_response(body, status=503 if exc.code == "unavailable" else 400)


async def handle_token_put(request: web.Request) -> web.Response:
    from bot.web.mini_api import _json_body, _require_user

    user = await _require_user(request)
    personal = _personal(request)
    body = await _json_body(request)
    account_id = str(body.get("account_id") or "").strip()
    try:
        profile = await personal.add(user.person_id, account_id, str(body.get("token") or ""))
    except PsnTokenError as exc:
        return _refused(exc)
    return web.json_response({"ok": True, "online_id": profile.online_id})


async def handle_token_delete(request: web.Request) -> web.Response:
    from bot.web.mini_api import _json_body, _require_user

    user = await _require_user(request)
    personal = _personal(request)
    body = await _json_body(request) if request.can_read_body else {}
    account_id = str(body.get("account_id") or request.query.get("account_id") or "").strip()
    await personal.remove(user.person_id, account_id)
    return web.json_response({"ok": True})


async def handle_connect_by_token(request: web.Request) -> web.Response:
    """Links the PSN account a token opens and keeps the token for it: its
    trophies may be hidden, its own token reads them. The same limit and
    cooldown as linking by nickname."""
    from bot.web.mini_api import _json_body, _require_user

    user = await _require_user(request)
    body = await _json_body(request)
    return await link_by_token(request, user, str(body.get("token") or ""))


async def link_by_token(request: web.Request, user: MiniAppUser, raw: str) -> web.Response:
    """Linking by a token, whichever field it was pasted into: the token's
    own route, or the nickname's (`handle_connect_psn`), where it must never
    be logged or sent to Sony's search."""
    from bot.web.mini_api import _psn_backfill

    personal = _personal(request)
    repo: Repo = request.app["mini_repo"]
    psn_fetcher: PsnFetcher | None = request.app["mini_psn_fetcher"]
    if psn_fetcher is None:
        raise web.HTTPServiceUnavailable(text="psn unavailable")
    if await request.app["mini_psn_auth"].status() == STATUS_NOT_CONFIGURED:
        # No shared token: the poller reads nobody, a linked account included.
        return web.json_response({"ok": False, "error": "not_configured"}, status=400)
    try:
        npsso, profile = await personal.identify(raw, user.person_id)
    except PsnTokenError as exc:
        return _refused(exc)

    held = await repo.platform_links_for(user.person_id, Platform.PSN)
    if (
        all(link.external_id != profile.account_id for link in held)
        and len(held) >= MAX_PSN_ACCOUNTS
    ):
        return web.json_response(
            {"ok": False, "error": "limit", "max": MAX_PSN_ACCOUNTS}, status=409
        )
    cooldown = await repo.check_platform_cooldown(user.tg_id, Platform.PSN, profile.account_id)
    if cooldown.is_blocked:
        return web.json_response(
            {"ok": False, "error": "cooldown", "cooldown_seconds": cooldown.remaining_seconds},
            status=400,
        )

    await repo.link_platform_account(
        user.person_id, Platform.PSN, profile.account_id, profile.online_id
    )
    await repo.set_achievements_visible(
        user.person_id, Platform.PSN, True, external_id=profile.account_id
    )
    await personal.keep(user.person_id, profile.account_id, npsso)
    log.info("mini: psn account %s linked by its own token", profile.account_id)
    asyncio.create_task(  # noqa: RUF006
        _psn_backfill(psn_fetcher, user.person_id, profile.account_id)
    )
    return web.json_response(
        {
            "ok": True,
            "account_id": profile.account_id,
            "online_id": profile.online_id,
            "backfill": "started",
        }
    )
