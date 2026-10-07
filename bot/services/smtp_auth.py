"""The mail server's login, admin-settable (owner, 2026-10-07) — the shape of
SteamAuth, AnthropicAuth and YouTubeAuth (#17): kept encrypted in
app_settings, set / changed / cleared from /admin → «🔑 Ключи платформ» with no
restart and no trip to the server. `SMTP_USERNAME` / `SMTP_PASSWORD` in `.env`
are only a first-run seed; clearing the login in the panel disables the seed.

Where the server is (`SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`) and whom the
mail is from (`SMTP_FROM`) stay in `.env`: they are not secrets, and without
them email is off whatever is stored here.

The sender reads the login on every message (`credentials`), never a copy
taken at start: a login set in the panel works on the next code sent.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl

from bot.config import Settings
from bot.db.repo import Repo
from bot.services.crypto import TokenCipher

log = logging.getLogger(__name__)

LOGIN_ENC_KEY = "smtp_login_enc"
_CHECK_TIMEOUT_SECONDS = 20


class SmtpLoginInvalidError(Exception):
    """The login was not two words, or the mail server refused it."""


class SmtpAuth:
    def __init__(self, repo: Repo, cipher: TokenCipher, settings: Settings) -> None:
        self._repo = repo
        self._cipher = cipher
        self._settings = settings
        env_password = settings.smtp_password.get_secret_value() if settings.smtp_password else ""
        self._env = (
            (settings.smtp_username, env_password)
            if settings.smtp_username and env_password
            else None
        )
        self._seeded = False

    async def _seed_from_env_once(self) -> None:
        if self._seeded:
            return
        self._seeded = True
        if self._env is None or await self._repo.get_app_setting(LOGIN_ENC_KEY) is not None:
            return
        await self._store(*self._env, None)
        log.info("smtp login seeded from the environment into app_settings")

    async def credentials(self) -> tuple[str, str] | None:
        """`(username, password)`, read from storage each time."""
        await self._seed_from_env_once()
        encrypted = await self._repo.get_app_setting(LOGIN_ENC_KEY)
        if not encrypted:
            return None
        try:
            username, _, password = self._cipher.decrypt(encrypted.encode("ascii")).partition("\n")
        except ValueError:
            log.warning(
                "smtp login in app_settings cannot be decrypted with this FERNET_KEY"
                " — set it again in the admin panel"
            )
            return None
        return (username, password) if username and password else None

    async def configured(self) -> bool:
        return await self.credentials() is not None

    async def set_login(self, raw: str, admin_id: int) -> None:
        """`raw` is "login key" (any whitespace between). Checked by logging in
        to the mail server first: a typo must not replace a working login."""
        parts = raw.split()
        if len(parts) != 2:
            raise SmtpLoginInvalidError
        username, password = parts
        if not self._settings.smtp_host:
            raise SmtpLoginInvalidError
        try:
            await asyncio.to_thread(self._check_blocking, username, password)
        except (OSError, smtplib.SMTPException) as exc:
            log.info("smtp login refused on verification: %s", type(exc).__name__)
            raise SmtpLoginInvalidError from None
        await self._store(username, password, admin_id)

    async def clear(self, admin_id: int) -> None:
        await self._repo.delete_app_setting(LOGIN_ENC_KEY)
        # The panel's clear is the newer decision: a stale env var stays out.
        self._seeded = True
        self._env = None

    async def _store(self, username: str, password: str, admin_id: int | None) -> None:
        encrypted = self._cipher.encrypt(f"{username}\n{password}").decode("ascii")
        await self._repo.set_app_setting(LOGIN_ENC_KEY, encrypted, admin_id)

    def _check_blocking(self, username: str, password: str) -> None:
        settings = self._settings
        assert settings.smtp_host is not None
        context = ssl.create_default_context()
        if settings.smtp_security == "ssl":
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=_CHECK_TIMEOUT_SECONDS,
                context=context,
            )
        else:
            server = smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=_CHECK_TIMEOUT_SECONDS
            )
        with server:
            if settings.smtp_security == "starttls":
                server.starttls(context=context)
            server.login(username, password)
