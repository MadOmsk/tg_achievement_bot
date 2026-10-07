"""Admin-settable YouTube Data API key — the fourth shared credential, the
same shape as SteamAuth and AnthropicAuth (#17): kept encrypted in
app_settings, set / changed / cleared from the admin panel with no restart;
`YOUTUBE_API_KEY` in `.env` is only a first-run seed, and clearing the key in
the panel disables the seed. Video guides are optional: without a key they are
simply not read.
"""

from __future__ import annotations

import logging

from bot.db.repo import Repo
from bot.services.crypto import TokenCipher
from bot.services.youtube.client import check_alive

log = logging.getLogger(__name__)

KEY_ENC_KEY = "youtube_api_key_enc"


class YouTubeKeyInvalidError(Exception):
    """A candidate key failed its verification call and was not saved."""


class YouTubeAuth:
    def __init__(self, repo: Repo, cipher: TokenCipher, *, env_key: str | None = None) -> None:
        self._repo = repo
        self._cipher = cipher
        self._env_key = env_key or None
        self._key: str | None = None
        self._seeded = False

    async def _seed_from_env_once(self) -> None:
        if self._seeded:
            return
        self._seeded = True
        if self._env_key is None or await self._repo.get_app_setting(KEY_ENC_KEY) is not None:
            return
        encrypted = self._cipher.encrypt(self._env_key).decode("ascii")
        await self._repo.set_app_setting(KEY_ENC_KEY, encrypted)
        log.info("youtube api key seeded from the environment into app_settings")

    async def get_key(self) -> str | None:
        if self._key is not None:
            return self._key
        await self._seed_from_env_once()
        encrypted = await self._repo.get_app_setting(KEY_ENC_KEY)
        if encrypted is None:
            return None
        try:
            self._key = self._cipher.decrypt(encrypted.encode("ascii"))
        except ValueError:
            # Another instance's ciphertext (a copied database): no usable key,
            # never a reason to stop anything — guides are optional.
            log.warning(
                "youtube api key in app_settings cannot be decrypted with this FERNET_KEY"
                " — treating it as not configured; set it again in the admin panel"
            )
            return None
        return self._key

    async def configured(self) -> bool:
        return await self.get_key() is not None

    async def set_key(self, api_key: str, admin_id: int) -> None:
        """Checked with a real call first: a typo must not replace a working key."""
        api_key = api_key.strip()
        if not await check_alive(api_key):
            raise YouTubeKeyInvalidError
        encrypted = self._cipher.encrypt(api_key).decode("ascii")
        await self._repo.set_app_setting(KEY_ENC_KEY, encrypted, admin_id)
        self._key = api_key

    async def clear(self, admin_id: int) -> None:
        await self._repo.delete_app_setting(KEY_ENC_KEY)
        self._key = None
        # The panel's clear is the newer decision: a stale env var stays out.
        self._seeded = True
        self._env_key = None
