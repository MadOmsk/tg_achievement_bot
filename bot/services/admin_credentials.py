"""The shared credentials, one registry for both admin surfaces (#176).

The bot's /admin keys screen, its text input and its clear button, and the
Mini App's `GET/PUT/DELETE /api/mini/admin/keys/{name}` all walk this list:
a new credential is one entry here plus its `admin-keys-<name>-*` strings in
`admin.ftl` (label, hint, add / change / clear, prompt, saved, invalid).

Each entry wraps the credential's own auth class (#17's shape: encrypted in
`app_settings`, verified before it is saved, cleared from the panel); this
module only gives them one face — `configured`, a health status where the
credential has one, `set` raising `CredentialInvalid`, `clear`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.constants import TokenStatus
from bot.services.psn.auth import PsnAuth
from bot.services.psn.client import PsnClientSetupError, PsnTokenDeadError
from bot.services.smtp_auth import SmtpAuth, SmtpLoginInvalidError
from bot.services.steam.auth import SteamAuth, SteamKeyInvalidError
from bot.services.translate.auth import AnthropicAuth, AnthropicKeyInvalidError
from bot.services.youtube.auth import YouTubeAuth, YouTubeKeyInvalidError

# Every auth class with a health check says "not configured" the same way.
_NOT_CONFIGURED = "not_configured"


class CredentialInvalid(Exception):
    """The service refused the value; nothing was saved."""


class CredentialSetupError(Exception):
    """The value could not even be tried — a fault on our side, not the
    value's (psnawp failing to build its client). Worded differently, so a
    bug is not blamed on the key."""


@dataclass(frozen=True, slots=True)
class CredentialState:
    name: str
    configured: bool
    # `active` / `invalid` for a credential the health check watches (Steam,
    # PSN, Anthropic); None for one it does not, or one not configured.
    status: str | None
    checked_at: str | None


class _Credential:
    """One entry: the auth object and how to call it. Methods are looked up
    when used, never when the registry is built."""

    name: str
    invalid: tuple[type[Exception], ...] = ()
    watched = True  # has status() / checked_at() from the health check

    def __init__(self, auth: Any) -> None:
        self.auth = auth

    async def configured(self) -> bool:
        return await self.auth.status() != _NOT_CONFIGURED

    async def store(self, value: str, admin_id: int) -> None:
        await self.auth.set_key(value, admin_id)

    async def state(self) -> CredentialState:
        configured = await self.configured()
        if not configured or not self.watched:
            return CredentialState(self.name, configured, None, None)
        status = await self.auth.status()
        if status not in (TokenStatus.ACTIVE, TokenStatus.INVALID):
            status = TokenStatus.ACTIVE
        return CredentialState(self.name, True, status, await self.auth.checked_at())

    async def set(self, value: str, admin_id: int) -> None:
        try:
            await self.store(value, admin_id)
        except self.invalid as exc:
            raise CredentialInvalid from exc


class _Psn(_Credential):
    name = "psn"
    invalid = (PsnTokenDeadError,)

    async def store(self, value: str, admin_id: int) -> None:
        try:
            await self.auth.set_npsso(value, admin_id)
        except PsnClientSetupError as exc:
            raise CredentialSetupError(str(exc)) from exc


class _Steam(_Credential):
    name = "steam"
    invalid = (SteamKeyInvalidError,)


class _Anthropic(_Credential):
    name = "anthropic"
    invalid = (AnthropicKeyInvalidError,)


class _YouTube(_Credential):
    name = "youtube"
    invalid = (YouTubeKeyInvalidError,)
    watched = False

    async def configured(self) -> bool:
        return await self.auth.configured()


class _Smtp(_Credential):
    name = "smtp"
    invalid = (SmtpLoginInvalidError,)
    watched = False

    async def configured(self) -> bool:
        return await self.auth.configured()

    async def store(self, value: str, admin_id: int) -> None:
        await self.auth.set_login(value, admin_id)


class AdminCredentials:
    """The credentials this process has, in the order both panels list them."""

    def __init__(
        self,
        *,
        psn: PsnAuth | None = None,
        steam: SteamAuth | None = None,
        anthropic: AnthropicAuth | None = None,
        youtube: YouTubeAuth | None = None,
        smtp: SmtpAuth | None = None,
    ) -> None:
        self.smtp = smtp
        pairs: list[tuple[type[_Credential], Any]] = [
            (_Psn, psn),
            (_Steam, steam),
            (_Anthropic, anthropic),
            (_YouTube, youtube),
            (_Smtp, smtp),
        ]
        self._entries = {kind.name: kind(auth) for kind, auth in pairs if auth is not None}

    @property
    def names(self) -> list[str]:
        return list(self._entries)

    def __contains__(self, name: object) -> bool:
        return name in self._entries

    async def state(self, name: str) -> CredentialState:
        return await self._entries[name].state()

    async def states(self) -> list[CredentialState]:
        return [await entry.state() for entry in self._entries.values()]

    async def set(self, name: str, raw: str, admin_id: int) -> None:
        """Checked by the service before it is saved: a typo never replaces
        a working value. Raises CredentialInvalid or CredentialSetupError."""
        value = raw.strip()
        if not value:
            raise CredentialInvalid
        await self._entries[name].set(value, admin_id)

    async def clear(self, name: str, admin_id: int) -> None:
        await self._entries[name].auth.clear(admin_id)
