"""Service-wide PSN authentication (SPEC 9, M-PSN-1) — one NPSSO for the
whole bot, not per-user OAuth like Xbox's services/xbox/auth.py.

Storage still lives in the database rather than .env, unlike Steam's static
key (config.py's steam_api_key): PSN's NPSSO is not a permanent secret, it
expires (observed ~60 days) and the admin needs to paste a fresh one from
time to time — doing that as an app_settings row means no .env edit and no
restart, the same reasoning that already puts every other admin-editable
value there.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from psnawp_api import PSNAWP

from bot.constants import TokenStatus
from bot.db.repo import Repo
from bot.services.crypto import TokenCipher
from bot.services.psn.client import (
    TRANSLATION_HEADERS,
    PsnApiError,
    PsnTokenDeadError,
    build_client,
    check_alive,
)
from bot.util import utcnow

log = logging.getLogger(__name__)

NPSSO_KEY = "psn_npsso_enc"
STATUS_KEY = "psn_key_status"
CHECKED_AT_KEY = "psn_key_checked_at"

STATUS_NOT_CONFIGURED = "not_configured"
# Compatibility aliases for callers that import the PSN service statuses.
STATUS_ACTIVE = TokenStatus.ACTIVE
STATUS_INVALID = TokenStatus.INVALID


class PsnNotConfiguredError(Exception):
    """No NPSSO has ever been set — /connect_psn and the admin panel both
    answer "not configured" rather than reaching this at all."""


class PsnAuth:
    """Holds the single process-wide PSNAWP instance, built lazily from
    whatever NPSSO is currently stored. The library keeps its own access/
    refresh token in memory and refreshes the access token from the refresh
    token before each request on its own (verified against psnawp_api's own
    Authenticator.fetch_access_token_from_refresh) — so unlike
    XboxAuthService there is no lazy-refresh-before-request lock to write
    here: a dead NPSSO only ever surfaces as PsnTokenDeadError, handled the
    same "expected failure" way as everywhere else in this bot.
    """

    def __init__(self, repo: Repo, cipher: TokenCipher) -> None:
        self._repo = repo
        self._cipher = cipher
        self._client: PSNAWP | None = None
        # A second, Russian-locale client (2026-09-09, #48) — see
        # get_translation_client() below and client.py's own
        # TRANSLATION_HEADERS for why this needs a whole separate PSNAWP
        # instance rather than a per-request parameter.
        self._client_ru: PSNAWP | None = None
        # Set from main.py, same pattern as XboxAuthService.on_token_dead —
        # fired at most once per active->invalid transition
        # (poller/service_health.py owns not spamming this every tick).
        self.on_dead: Callable[[], Awaitable[None]] | None = None

    async def status(self) -> str:
        return await self._repo.get_app_setting(STATUS_KEY, STATUS_NOT_CONFIGURED) or (
            STATUS_NOT_CONFIGURED
        )

    async def checked_at(self) -> str | None:
        return await self._repo.get_app_setting(CHECKED_AT_KEY)

    async def set_npsso(self, npsso: str, admin_id: int) -> None:
        """Validates with a real verification call before saving anything —
        a typo'd NPSSO must not silently overwrite a working one.
        build_client() alone does NOT prove the NPSSO works (found live
        2026-09-06: psnawp_api's constructor "succeeds" instantly even for
        complete garbage — no network call happens until the first real
        request), so this makes that first real request itself
        (check_alive) rather than trusting construction to mean anything.
        """
        client = await build_client(npsso)
        if not await check_alive(client):
            raise PsnTokenDeadError("NPSSO rejected on verification call")
        encrypted = self._cipher.encrypt(npsso).decode("ascii")
        await self._repo.set_app_setting(NPSSO_KEY, encrypted, admin_id)
        await self._repo.set_app_setting(STATUS_KEY, TokenStatus.ACTIVE, admin_id)
        await self._repo.set_app_setting(
            CHECKED_AT_KEY, utcnow().isoformat(timespec="seconds"), admin_id
        )
        self._client = client
        self._client_ru = None  # rebuilt lazily from the new NPSSO, next use

    async def clear(self, admin_id: int) -> None:
        """Remove the stored NPSSO entirely, reverting PSN to "not
        configured" (#17) — the admin panel's Clear action. `set_npsso`
        only ever overwrites; nothing deleted the row before this."""
        await self._repo.delete_app_setting(NPSSO_KEY)
        await self._repo.set_app_setting(STATUS_KEY, STATUS_NOT_CONFIGURED, admin_id)
        await self._repo.delete_app_setting(CHECKED_AT_KEY)
        self._client = None
        self._client_ru = None

    async def get_client(self) -> PSNAWP:
        if self._client is not None:
            return self._client
        encrypted = await self._repo.get_app_setting(NPSSO_KEY)
        if encrypted is None:
            raise PsnNotConfiguredError
        npsso = self._cipher.decrypt(encrypted.encode("ascii"))
        self._client = await build_client(npsso)
        return self._client

    async def get_translation_client(self) -> PSNAWP:
        """The second, Russian-locale PSNAWP instance services/psn/
        achievements.py's own bilingual-description fetch needs (2026-09-09,
        #48) — same lazy-build-from-storage shape as get_client() above,
        just with client.py's TRANSLATION_HEADERS instead of the library's
        own defaults. Deliberately its own cached instance, not a second
        call to get_client() with different headers: PSNAWP bakes headers
        into the client object at construction time, so there is no way to
        ask the *same* client for a different locale per call."""
        if self._client_ru is not None:
            return self._client_ru
        encrypted = await self._repo.get_app_setting(NPSSO_KEY)
        if encrypted is None:
            raise PsnNotConfiguredError
        npsso = self._cipher.decrypt(encrypted.encode("ascii"))
        self._client_ru = await build_client(npsso, headers=TRANSLATION_HEADERS)
        return self._client_ru

    async def check_health(self) -> bool:
        """Active health-check (SPEC 9, M-PSN-1's "мониторинг живости"
        paragraph) — a service token has no per-user isolation like Xbox's,
        so its death would otherwise stay invisible until someone's
        /connect_psn happened to hit it. Called periodically by
        poller/service_health.py, never from a request path."""
        if await self.status() == STATUS_NOT_CONFIGURED:
            return False  # nothing set up yet — not a failure, nothing to notify about

        was_active = await self.status() == TokenStatus.ACTIVE
        try:
            client = await self.get_client()
            alive = await check_alive(client)
        except PsnApiError:
            # PsnTokenDeadError (bad NPSSO) or PsnClientSetupError (couldn't
            # even construct the client, e.g. the sandboxed-temp-dir bug
            # found live 2026-09-06) — either way, not alive right now.
            alive = False

        await self._repo.set_app_setting(
            STATUS_KEY, TokenStatus.ACTIVE if alive else TokenStatus.INVALID
        )
        await self._repo.set_app_setting(CHECKED_AT_KEY, utcnow().isoformat(timespec="seconds"))
        if not alive:
            # Force a fresh exchange for both clients once a new NPSSO is
            # set — the translation client shares the same NPSSO, so a dead
            # primary means it's equally dead.
            self._client = None
            self._client_ru = None
        if was_active and not alive and self.on_dead is not None:
            await self.on_dead()
        return alive
