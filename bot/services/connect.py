"""Orchestration of the /connect_xbox flow, shared by the handler and the web callback."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

from bot.db.repo import Repo
from bot.i18n import gettext
from bot.services.xbox.auth import XboxAuthService, XboxIdentity
from bot.util import utcnow

log = logging.getLogger(__name__)

STATE_TTL_SECONDS = 600


class ConnectError(Exception):
    """Something the user should be told about in plain Russian."""


@dataclass(slots=True)
class _PendingState:
    tg_id: int
    created_at: float
    origin_chat_id: int | None = None


class ConnectService:
    """Hands out one-time `state` values and completes the OAuth callback.

    States live in memory only: a restart mid-login just means pressing
    «Подключить XBOX» again, which is cheaper than another table.
    """

    def __init__(self, auth: XboxAuthService, repo: Repo) -> None:
        self._auth = auth
        self._repo = repo
        self._pending: dict[str, _PendingState] = {}

    def start_login(self, tg_id: int, origin_chat_id: int | None = None) -> str:
        """`origin_chat_id` is the group where the person pressed «Подключить XBOX»
        from, if any — carried through to `complete_login` so we can
        auto-subscribe him there once the login actually succeeds (SPEC 6.3).
        """
        self._forget_expired()
        state = secrets.token_urlsafe(24)
        self._pending[state] = _PendingState(
            tg_id=tg_id, created_at=utcnow().timestamp(), origin_chat_id=origin_chat_id
        )
        return self._auth.authorization_url(state)

    async def complete_login(self, state: str, code: str) -> tuple[int, XboxIdentity, int | None]:
        """Validate the state, exchange the code, store the account."""
        self._forget_expired()
        pending = self._pending.pop(state, None)
        if pending is None:
            # Unknown or expired state — also what a forged callback looks
            # like, so there is no person here whose language to use (#48).
            raise ConnectError(gettext("connectservice", "connectservice-state-expired"))

        identity = await self._auth.exchange_code(code)

        owner = await self._repo.get_user_by_xuid(identity.xuid)
        if owner is not None and owner.tg_id != pending.tg_id:
            # One Xbox account per person (SPEC 1): otherwise the same
            # achievements would be published twice under different names.
            # Unlike the branch above, this one knows who is being told.
            raise ConnectError(
                gettext(
                    "connectservice",
                    "connectservice-account-owned",
                    locale=await self.user_locale(pending.tg_id),
                )
            )

        await self._auth.store_identity(pending.tg_id, identity)
        log.info("tg_id=%s linked xuid=%s", pending.tg_id, identity.xuid)
        return pending.tg_id, identity, pending.origin_chat_id

    async def user_locale(self, tg_id: int) -> str:
        """Passed through for web/oauth.py, which renders the post-login page
        for one known person but holds no Repo of its own (#48)."""
        return await self._repo.user_locale(tg_id)

    def _forget_expired(self) -> None:
        now = utcnow().timestamp()
        expired = [
            state
            for state, pending in self._pending.items()
            if now - pending.created_at > STATE_TTL_SECONDS
        ]
        for state in expired:
            del self._pending[state]
