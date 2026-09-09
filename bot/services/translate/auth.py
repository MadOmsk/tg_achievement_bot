"""Admin-settable Anthropic API key (2026-09-09 user request) — the
achievement-description-translation counterpart of services/steam/auth.py's
SteamAuth, same shape (#17's pattern, applied to a third shared credential).

The key lives encrypted in app_settings, admin-settable from the panel with
no `.env` edit and no restart. `ANTHROPIC_API_KEY` in `.env` is only a
first-run seed — once a key exists in the database, the env var is never
consulted again; clearing the key from the panel disables the seed too
(the panel action is the newer, explicit decision).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from bot.constants import TokenStatus
from bot.db.repo import Repo
from bot.services.crypto import TokenCipher
from bot.services.translate.client import check_alive
from bot.util import utcnow

log = logging.getLogger(__name__)

KEY_ENC_KEY = "anthropic_api_key_enc"
STATUS_KEY = "anthropic_key_status"
CHECKED_AT_KEY = "anthropic_key_checked_at"

STATUS_NOT_CONFIGURED = "not_configured"


class AnthropicNotConfiguredError(Exception):
    """No Anthropic key has ever been set — translation is simply skipped
    (an achievement description just keeps whatever language it was fetched
    in), never a hard failure anywhere that calls into this."""


class AnthropicKeyInvalidError(Exception):
    """A candidate key failed its verification call and was not saved."""


class AnthropicAuth:
    """Holds the process-wide Anthropic API key, read lazily from whatever
    is currently stored so an admin's set/change/clear takes effect without
    a restart. Mirrors SteamAuth exactly — see that module's own docstring
    for the reasoning this one shares."""

    def __init__(self, repo: Repo, cipher: TokenCipher, *, env_key: str | None = None) -> None:
        self._repo = repo
        self._cipher = cipher
        self._env_key = env_key or None
        self._key: str | None = None
        self._seeded = False
        # Set from main.py, same pattern as SteamAuth.on_dead / PsnAuth.on_dead
        # — fired at most once per active->invalid transition
        # (poller/service_health.py owns the "not every tick" gating).
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
        log.info("anthropic api key seeded from the environment into app_settings")

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
            raise AnthropicNotConfiguredError
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
        silently overwrite a working one (same guard SteamAuth/PsnAuth have)."""
        api_key = api_key.strip()
        if not await check_alive(api_key):
            raise AnthropicKeyInvalidError
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
        timer). Mirrors SteamAuth.check_health: updates the stored status
        and fires on_dead exactly once per active->invalid transition."""
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
