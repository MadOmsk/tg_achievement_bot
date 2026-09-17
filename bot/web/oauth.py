"""HTTP surface: Microsoft OAuth callback + Mini App JSON API.

OAuth still has no UI beyond a "you can close this tab" page — Microsoft
insists on a browser redirect. The Mini App SPA is separate (Vite / nginx);
this process only serves ``/api/mini/*`` next to ``/auth/callback`` so one
listen port covers both.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

from aiohttp import web

from bot.config import Settings
from bot.db.repo import Repo
from bot.i18n import DEFAULT_LOCALE, translator
from bot.services.connect import ConnectError, ConnectService
from bot.services.xbox.auth import TokenRefreshError, XboxIdentity
from bot.web.mini_api import cors_middleware, setup_mini_api

log = logging.getLogger(__name__)

# This page is rendered before anyone is identified, in most branches (#48):
# the OAuth `state` has not been resolved to a tg_id yet on the cancel/error
# paths, and a browser's Accept-Language is deliberately not consulted —
# locale is opt-in in this bot, never sniffed. Only the success page, which
# happens after complete_login hands back a tg_id, knows whose language to
# use. `_` here is therefore the default-locale translator, used only by
# those anonymous branches.
_ = translator("oauth", DEFAULT_LOCALE)

OnLinked = Callable[[int, XboxIdentity, "int | None"], Awaitable[None]]

_PAGE = """<!doctype html>
<meta charset="utf-8">
<title>Xbox Achievement Bot</title>
<style>
  body {{ font: 16px/1.5 system-ui, sans-serif; margin: 15vh auto; max-width: 30rem;
          padding: 0 1rem; text-align: center; }}
  .muted {{ color: #666; }}
</style>
<h1>{title}</h1>
<p class="muted">{text}</p>
"""


def _page(title: str, text: str, status: int = 200) -> web.Response:
    return web.Response(
        text=_PAGE.format(title=title, text=text), content_type="text/html", status=status
    )


class OAuthServer:
    def __init__(
        self,
        settings: Settings,
        connect: ConnectService,
        on_linked: OnLinked,
        repo: Repo,
        *,
        steam_auth: Any = None,
        steam_fetcher: Any = None,
        psn_auth: Any = None,
        psn_fetcher: Any = None,
        xbox_fetcher: Any = None,
        notifier: Any = None,
        anthropic_auth: Any = None,
        bot: Any = None,
    ) -> None:
        self._settings = settings
        self._connect = connect
        self._on_linked = on_linked
        self._repo = repo
        self._steam_auth = steam_auth
        self._steam_fetcher = steam_fetcher
        self._psn_auth = psn_auth
        self._psn_fetcher = psn_fetcher
        self._xbox_fetcher = xbox_fetcher
        self._notifier = notifier
        self._anthropic_auth = anthropic_auth
        self._bot = bot
        self._runner: web.AppRunner | None = None

    @property
    def _callback_path(self) -> str:
        # Taken from OAUTH_REDIRECT_URL so the route and what Azure knows
        # can never drift apart.
        return urlsplit(self._settings.oauth_redirect_url).path or "/auth/callback"

    async def start(self) -> None:
        app = web.Application(middlewares=[cors_middleware()])
        app.router.add_get(self._callback_path, self._handle_callback)
        setup_mini_api(
            app,
            self._settings,
            self._repo,
            connect=self._connect,
            steam_auth=self._steam_auth,
            steam_fetcher=self._steam_fetcher,
            psn_auth=self._psn_auth,
            psn_fetcher=self._psn_fetcher,
            xbox_fetcher=self._xbox_fetcher,
            notifier=self._notifier,
            anthropic_auth=self._anthropic_auth,
            bot=self._bot,
        )

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(
            self._runner, self._settings.oauth_listen_host, self._settings.oauth_listen_port
        )
        await site.start()
        log.info(
            "web listening on %s:%s (oauth %s, mini /api/mini/*)",
            self._settings.oauth_listen_host,
            self._settings.oauth_listen_port,
            self._callback_path,
        )

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def _handle_callback(self, request: web.Request) -> web.Response:
        error = request.query.get("error")
        if error:
            # The user pressed "Cancel" on the consent screen, or Microsoft
            # refused. error_description is for us, not for him.
            log.info(
                "consent screen returned error=%s: %s",
                error,
                request.query.get("error_description"),
            )
            return _page(_("oauth-cancelled-title"), _("oauth-cancelled-text"))

        code = request.query.get("code")
        state = request.query.get("state")
        if not code or not state:
            return _page(_("oauth-missing-title"), _("oauth-missing-text"), status=400)

        try:
            tg_id, identity, origin_chat_id = await self._connect.complete_login(state, code)
        except ConnectError as exc:
            return _page(_("oauth-failed-title"), str(exc), status=400)
        except TokenRefreshError:
            log.exception("token exchange failed")
            return _page(
                _("oauth-token-exchange-failed-title"),
                _("oauth-token-exchange-failed-text"),
                status=502,
            )

        try:
            await self._on_linked(tg_id, identity, origin_chat_id)
        except Exception:
            # The account is already linked; only the Telegram message failed.
            log.exception("could not notify tg_id=%s about a successful login", tg_id)

        # The one branch with a known person behind it.
        own = translator("oauth", await self._connect.user_locale(tg_id))
        return _page(
            own("oauth-success-title", gamertag=identity.gamertag), own("oauth-success-text")
        )
