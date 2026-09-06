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

from bot.db.repo import Repo
from bot.services.crypto import TokenCipher
from bot.services.psn.client import PsnTokenDeadError, build_client, check_alive
from bot.util import utcnow

log = logging.getLogger(__name__)

NPSSO_KEY = "psn_npsso_enc"
STATUS_KEY = "psn_key_status"
CHECKED_AT_KEY = "psn_key_checked_at"

STATUS_NOT_CONFIGURED = "not_configured"
STATUS_ACTIVE = "active"
STATUS_INVALID = "invalid"


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
        """Validates by actually building a client before saving anything —
        a typo'd NPSSO must not silently overwrite a working one."""
        client = await build_client(npsso)  # raises PsnTokenDeadError if bad
        encrypted = self._cipher.encrypt(npsso).decode("ascii")
        await self._repo.set_app_setting(NPSSO_KEY, encrypted, admin_id)
        await self._repo.set_app_setting(STATUS_KEY, STATUS_ACTIVE, admin_id)
        await self._repo.set_app_setting(
            CHECKED_AT_KEY, utcnow().isoformat(timespec="seconds"), admin_id
        )
        self._client = client

    async def get_client(self) -> PSNAWP:
        if self._client is not None:
            return self._client
        encrypted = await self._repo.get_app_setting(NPSSO_KEY)
        if encrypted is None:
            raise PsnNotConfiguredError
        npsso = self._cipher.decrypt(encrypted.encode("ascii"))
        self._client = await build_client(npsso)
        return self._client

    async def check_health(self) -> bool:
        """Active health-check (SPEC 9, M-PSN-1's "мониторинг живости"
        paragraph) — a service token has no per-user isolation like Xbox's,
        so its death would otherwise stay invisible until someone's
        /connect_psn happened to hit it. Called periodically by
        poller/service_health.py, never from a request path."""
        if await self.status() == STATUS_NOT_CONFIGURED:
            return False  # nothing set up yet — not a failure, nothing to notify about

        was_active = await self.status() == STATUS_ACTIVE
        try:
            client = await self.get_client()
            alive = await check_alive(client)
        except PsnTokenDeadError:
            alive = False

        await self._repo.set_app_setting(STATUS_KEY, STATUS_ACTIVE if alive else STATUS_INVALID)
        await self._repo.set_app_setting(CHECKED_AT_KEY, utcnow().isoformat(timespec="seconds"))
        if not alive:
            self._client = None  # force a fresh exchange once a new NPSSO is set
        if was_active and not alive and self.on_dead is not None:
            await self.on_dead()
        return alive
