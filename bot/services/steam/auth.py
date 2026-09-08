"""Admin-settable Steam Web API key (#17) — the Steam counterpart of
services/psn/auth.py's PsnAuth.

The key used to be environment-only (config.py's `steam_api_key`). It now
lives encrypted in `app_settings`, so an admin can set / change / clear it
from the bot with no `.env` edit and no restart — the same reasoning that
already put the PSN NPSSO and every Xbox refresh token there. The env var
stays as a one-time seed: on first access, if the database has no key but
the environment does, the environment value is imported once and the
database copy wins from then on. Clearing the key from the panel is a
newer, explicit decision than the env var, so a clear disables the seed.

This module owns the two status keys the /admin home and
poller/service_health.py read (`STATUS_KEY` / `CHECKED_AT_KEY`) — the same
split PsnAuth already has, and the reason service_health can import from
here without a cycle.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from bot.constants import TokenStatus
from bot.db.repo import Repo
from bot.services.crypto import TokenCipher
from bot.services.steam.client import check_alive
from bot.util import utcnow

log = logging.getLogger(__name__)

KEY_ENC_KEY = "steam_api_key_enc"
STATUS_KEY = "steam_key_status"
CHECKED_AT_KEY = "steam_key_checked_at"

STATUS_NOT_CONFIGURED = "not_configured"
# Compatibility aliases for callers that import the Steam service statuses.
STATUS_ACTIVE = TokenStatus.ACTIVE
STATUS_INVALID = TokenStatus.INVALID


class SteamNotConfiguredError(Exception):
    """No Steam key has ever been set — /connect_steam and the admin panel
    both answer "not configured" rather than reaching this."""


class SteamKeyInvalidError(Exception):
    """A candidate key failed its verification call and was not saved."""


class SteamAuth:
    """Holds the process-wide Steam Web API key, read lazily from whatever
    is currently stored so an admin's set/change/clear takes effect without
    a restart. Unlike XboxAuthService there is nothing to refresh — a Steam
    key is a long-lived secret; a dead one only ever surfaces as
    SteamKeyDeadError, handled the same "expected failure" way everywhere.
    """

    def __init__(self, repo: Repo, cipher: TokenCipher, *, env_key: str | None = None) -> None:
        self._repo = repo
        self._cipher = cipher
        self._env_key = env_key or None
        self._key: str | None = None
        self._seeded = False
        # Set from main.py, same pattern as PsnAuth.on_dead — fired at most
        # once per active->invalid transition (poller/service_health.py owns
        # the "not every tick" gating).
        self.on_dead: Callable[[], Awaitable[None]] | None = None

    async def _seed_from_env_once(self) -> None:
        if self._seeded:
            return
        self._seeded = True
        if self._env_key is None:
            return
        if await self._repo.get_app_setting(KEY_ENC_KEY) is not None:
            return  # the database already has a key — env is only a first-run seed
        encrypted = self._cipher.encrypt(self._env_key).decode("ascii")
        await self._repo.set_app_setting(KEY_ENC_KEY, encrypted)
        if await self._repo.get_app_setting(STATUS_KEY) is None:
            # Don't presume it's alive — service_health's next tick verifies.
            await self._repo.set_app_setting(STATUS_KEY, TokenStatus.ACTIVE)
        log.info("steam api key seeded from the environment into app_settings")

    async def get_key(self) -> str | None:
        if self._key is not None:
            return self._key
        await self._seed_from_env_once()
        encrypted = await self._repo.get_app_setting(KEY_ENC_KEY)
        if encrypted is None:
            return None
        self._key = self._cipher.decrypt(encrypted.encode("ascii"))
        return self._key

    async def require_key(self) -> str:
        key = await self.get_key()
        if key is None:
            raise SteamNotConfiguredError
        return key

    async def status(self) -> str:
        if await self.get_key() is None:
            return STATUS_NOT_CONFIGURED
        return (
            await self._repo.get_app_setting(STATUS_KEY, TokenStatus.ACTIVE)
        ) or TokenStatus.ACTIVE

    async def checked_at(self) -> str | None:
        return await self._repo.get_app_setting(CHECKED_AT_KEY)

    async def set_key(self, api_key: str, admin_id: int) -> None:
        """Verify with a real API call before saving — a typo'd key must not
        silently overwrite a working one (same guard PsnAuth.set_npsso has)."""
        api_key = api_key.strip()
        if not await check_alive(api_key):
            raise SteamKeyInvalidError
        encrypted = self._cipher.encrypt(api_key).decode("ascii")
        await self._repo.set_app_setting(KEY_ENC_KEY, encrypted, admin_id)
        await self._repo.set_app_setting(STATUS_KEY, TokenStatus.ACTIVE, admin_id)
        await self._repo.set_app_setting(
            CHECKED_AT_KEY, utcnow().isoformat(timespec="seconds"), admin_id
        )
        self._key = api_key

    async def clear(self, admin_id: int) -> None:
        await self._repo.delete_app_setting(KEY_ENC_KEY)
        await self._repo.set_app_setting(STATUS_KEY, STATUS_NOT_CONFIGURED, admin_id)
        await self._repo.delete_app_setting(CHECKED_AT_KEY)
        self._key = None
        # A cleared key must not be re-seeded from a stale env var on the
        # next get_key() — the panel clear is the explicit newer decision.
        self._seeded = True
        self._env_key = None

    async def check_health(self) -> bool:
        """Active liveness check (poller/service_health.py calls it on a
        timer). Mirrors PsnAuth.check_health: updates the stored status and
        fires on_dead exactly once per active->invalid transition."""
        key = await self.get_key()
        if key is None:
            return False  # nothing configured — not a failure, nothing to notify
        was_active = (
            await self._repo.get_app_setting(STATUS_KEY, TokenStatus.ACTIVE)
        ) == TokenStatus.ACTIVE
        alive = await check_alive(key)
        await self._repo.set_app_setting(
            STATUS_KEY, TokenStatus.ACTIVE if alive else TokenStatus.INVALID
        )
        await self._repo.set_app_setting(CHECKED_AT_KEY, utcnow().isoformat(timespec="seconds"))
        if was_active and not alive and self.on_dead is not None:
            await self.on_dead()
        return alive
