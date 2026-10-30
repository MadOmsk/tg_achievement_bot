"""A player's own PSN token (owner, 2026-10-29; #233): an NPSSO a person adds
to one of their PSN accounts — opt-in, never required.

The shared admin NPSSO (`auth.PsnAuth`) stays the basic level: it reads every
account without a token and everything about games. A personal token reads
its own account — its trophies when trophy privacy is not "Everyone", its
presence when hidden, its play time — at its own pace, off the shared queue.

Rules: the format is checked before any request; a token is kept only for the
account it opens (`own_profile`), which must be the person's own linked
account; it is Fernet-encrypted, never logged, never shown back. A personal
token's failure never touches the shared credential's health: its account
falls back to the shared token and its owner is told (`on_dead`).
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Awaitable, Callable

from psnawp_api import PSNAWP

from bot.constants import Platform
from bot.db.repo import Repo
from bot.services.crypto import TokenCipher
from bot.services.psn.client import (
    PsnApiError,
    PsnProfile,
    PsnTokenDeadError,
    build_client,
    check_alive,
    own_profile,
)

log = logging.getLogger(__name__)

# What Sony's ssocookie page hands out: 64 letters and digits.
NPSSO_FORMAT = re.compile(r"[A-Za-z0-9]{64}")
# Tokens one person may have checked by Sony in a window: each check is a
# login on Sony's side and a client of its own.
ATTEMPTS_PER_WINDOW = 5
ATTEMPTS_WINDOW_SECONDS = 600


class PsnTokenError(Exception):
    """A token refused; `code` is what the screens word."""

    code = "invalid"

    def __init__(self, online_id: str | None = None) -> None:
        super().__init__(self.code)
        #: The account the token opens, shown when it is not the expected one
        #: so the person sees the mix-up. Never the token itself.
        self.online_id = online_id


class TokenFormatInvalid(PsnTokenError):
    code = "format"


class TokenRefused(PsnTokenError):
    """Sony did not accept it (expired, signed out, mistyped)."""

    code = "refused"


class TokenUnavailable(PsnTokenError):
    """Sony could not be asked right now; nothing is wrong with the token."""

    code = "unavailable"


class TokenTooOften(PsnTokenError):
    """More tokens tried than `ATTEMPTS_PER_WINDOW` in the window."""

    code = "too_soon"


class TokenMismatch(PsnTokenError):
    """It opens another PSN account than the one it is being added to."""

    code = "mismatch"


class TokenNotLinked(PsnTokenError):
    """The account it is added to is not this person's."""

    code = "not_linked"


def clean(raw: str) -> str:
    """What was pasted, without the quotes and the `"npsso":` around it when
    the whole JSON line was copied."""
    text = raw.strip()
    match = re.search(r'"npsso"\s*:\s*"([^"]*)"', text)
    if match:
        text = match.group(1)
    return text.strip().strip('"').strip()


def looks_like_token(raw: str) -> bool:
    """A token pasted where a nickname was asked (the token's button sits
    under that prompt): it must be neither logged nor echoed back."""
    return bool(NPSSO_FORMAT.fullmatch(clean(raw))) or '"npsso"' in raw


class PsnPersonalAuth:
    def __init__(self, repo: Repo, cipher: TokenCipher) -> None:
        self._repo = repo
        self._cipher = cipher
        self._clients: dict[str, PSNAWP] = {}
        # Who tried a token when, in memory: a restart starts it over.
        self._attempts: dict[object, list[float]] = {}
        # Fired once when a live token is found dead (main.py: the notice).
        self.on_dead: Callable[[int, str], Awaitable[None]] | None = None

    def _attempt(self, who: object) -> None:
        now = time.monotonic()
        recent = [t for t in self._attempts.get(who, []) if now - t < ATTEMPTS_WINDOW_SECONDS]
        if len(recent) >= ATTEMPTS_PER_WINDOW:
            self._attempts[who] = recent
            raise TokenTooOften
        self._attempts[who] = [*recent, now]

    async def identify(self, raw: str, who: object = None) -> tuple[str, PsnProfile]:
        """The token cleaned and the account it opens; raises PsnTokenError.
        `who` (a person, a Telegram id) rations the checks Sony is asked."""
        npsso = clean(raw)
        if not NPSSO_FORMAT.fullmatch(npsso):
            raise TokenFormatInvalid
        if who is not None:
            self._attempt(who)
        try:
            client = await build_client(npsso)
            profile = await own_profile(client)
        except PsnTokenDeadError:
            raise TokenRefused from None
        except PsnApiError:
            raise TokenUnavailable from None
        return npsso, profile

    async def add(self, person_id: int, account_id: str, raw: str) -> PsnProfile:
        """Keeps a token for one of the person's linked PSN accounts. Nothing
        is stored unless it opens exactly that account."""
        held = {
            link.external_id
            for link in await self._repo.platform_links_for(person_id, Platform.PSN)
        }
        if account_id not in held:
            raise TokenNotLinked
        npsso, profile = await self.identify(raw, person_id)
        if profile.account_id != account_id:
            log.info("psn token for account %s opens another account", account_id)
            raise TokenMismatch(profile.online_id)
        await self.keep(person_id, profile.account_id, npsso)
        return profile

    async def keep(self, person_id: int, account_id: str, npsso: str) -> None:
        """Stores a token already identified as this account's (linking by
        token checks it before the account is linked)."""
        encrypted = self._cipher.encrypt(npsso)
        await self._repo.save_psn_token(account_id, person_id, encrypted)
        self._clients.pop(account_id, None)
        log.info("psn personal token kept for account %s", account_id)

    async def remove(self, person_id: int, account_id: str) -> None:
        row = await self._repo.psn_token(account_id)
        if row is None or row.person_id != person_id:
            return
        await self._repo.delete_psn_token(account_id)
        self._clients.pop(account_id, None)
        log.info("psn personal token removed for account %s", account_id)

    async def client_for(self, account_id: str) -> PSNAWP | None:
        """The account's own client while its token is alive, else None (the
        caller uses the shared one)."""
        row = await self._repo.psn_token(account_id)
        if row is None or row.status != "active":
            self._clients.pop(account_id, None)
            return None
        client = self._clients.get(account_id)
        if client is not None:
            return client
        try:
            npsso = self._cipher.decrypt(row.npsso_enc)
        except ValueError:
            # Another server's FERNET_KEY: this server cannot use it.
            log.warning("psn personal token of account %s cannot be decrypted here", account_id)
            return None
        try:
            client = await build_client(npsso)
        except PsnApiError as exc:
            # The class only: a library's message is no place to trust with a token.
            log.info(
                "psn personal client for account %s not built: %s",
                account_id,
                type(exc).__name__,
            )
            return None
        self._clients[account_id] = client
        return client

    async def mark_dead(self, account_id: str, reason: str) -> None:
        """A request with the account's own token was refused: the account
        falls back to the shared token, and its owner is told once."""
        self._clients.pop(account_id, None)
        row = await self._repo.psn_token(account_id)
        if row is None:
            return
        if await self._repo.mark_psn_token_dead(account_id, reason) and self.on_dead:
            log.info("psn personal token of account %s is dead: %s", account_id, reason)
            try:
                await self.on_dead(row.person_id, account_id)
            except Exception:
                log.exception("telling person_id=%s of a dead psn token failed", row.person_id)

    async def check_all(self) -> None:
        """The daily check of every live token (one request each); tokens of
        accounts that left their person are forgotten first."""
        forgotten = await self._repo.forget_unheld_psn_tokens()
        if forgotten:
            log.info("forgot %d psn tokens of accounts no longer held", forgotten)
        for row in await self._repo.active_psn_tokens():
            client = await self.client_for(row.account_id)
            if client is None:
                continue
            if await check_alive(client, unreachable_is_alive=True):
                await self._repo.mark_psn_token_checked(row.account_id)
            else:
                await self.mark_dead(row.account_id, "refused on the daily check")
