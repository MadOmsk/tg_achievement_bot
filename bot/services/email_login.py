"""Signing in with an email address (#162): a six-digit code goes to the
address, and whoever types it back proves they read that mailbox.

The rules live here; the storage is `db/repo/_logins.py`, the sending
`services/email.py`.

- A code lives `CODE_TTL_MINUTES`, takes `MAX_ATTEMPTS` guesses, and is kept
  only as an HMAC keyed by the bot's own secret, so the table alone does not
  give the codes away.
- A new code replaces the previous one. One address gets at most one code a
  `RESEND_SECONDS` and `MAX_CODES_PER_HOUR` an hour: a code is not a way to
  flood somebody's mailbox.
- Whether an address is known is never said before the code is typed: a
  stranger cannot use the form to learn who uses the app.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from bot.db.repo import Repo
from bot.i18n import gettext
from bot.services.email import EmailSender
from bot.util import parse_iso, utcnow

CODE_LENGTH = 6
CODE_TTL_MINUTES = 10
MAX_ATTEMPTS = 5
RESEND_SECONDS = 60
MAX_CODES_PER_HOUR = 5
MAX_EMAIL_LENGTH = 254

SIGN_IN = "sign_in"
LINK = "link"

# Deliberately plain: one @, something on both sides, a dot in the domain, no
# spaces. The code is the real check — an address that looks fine and does
# not exist simply never gets one.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailInvalid(Exception):
    pass


class EmailTooSoon(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(retry_after)
        self.retry_after = retry_after


class CodeWrong(Exception):
    def __init__(self, attempts_left: int) -> None:
        super().__init__(attempts_left)
        self.attempts_left = attempts_left


class CodeExpired(Exception):
    """No live code: never sent, used, replaced, out of time or of guesses."""


def normalize_email(raw: str) -> str:
    email = (raw or "").strip().lower()
    if len(email) > MAX_EMAIL_LENGTH or not _EMAIL.match(email):
        raise EmailInvalid(raw)
    return email


def _hash(secret: bytes, email: str, code: str) -> str:
    return hmac.new(secret, f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


class EmailLogin:
    def __init__(self, repo: Repo, sender: EmailSender, secret: bytes) -> None:
        self._repo = repo
        self._sender = sender
        self._secret = secret

    async def send_code(
        self, raw_email: str, purpose: str, *, locale: str, person_id: int | None = None
    ) -> str:
        """Send a fresh code; returns the normalized address. Raises
        EmailInvalid, EmailTooSoon, or the sender's EmailSendError."""
        email = normalize_email(raw_email)
        now = utcnow()
        sent = await self._repo.email_codes_since(
            email, (now - timedelta(hours=1)).isoformat(timespec="seconds")
        )
        if sent:
            last = parse_iso(sent[0])
            wait = RESEND_SECONDS - int((now - last).total_seconds()) if last else 0
            if wait > 0:
                raise EmailTooSoon(wait)
        if len(sent) >= MAX_CODES_PER_HOUR:
            oldest = parse_iso(sent[-1])
            wait = 3600 - int((now - oldest).total_seconds()) if oldest else 3600
            raise EmailTooSoon(max(wait, 1))

        code = f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"
        expires = (now + timedelta(minutes=CODE_TTL_MINUTES)).isoformat(timespec="seconds")
        await self._repo.add_email_code(
            email, purpose, person_id, _hash(self._secret, email, code), expires
        )
        await self._sender.send(
            email,
            gettext("email", "email-code-subject", locale=locale, code=code),
            gettext("email", "email-code-body", locale=locale, code=code, minutes=CODE_TTL_MINUTES),
        )
        return email

    async def check_code(
        self, raw_email: str, code: str, purpose: str, *, person_id: int | None = None
    ) -> str:
        """The address, once the code proves it; raises CodeWrong / CodeExpired.
        A code asked for by one signed-in person is no good to another."""
        email = normalize_email(raw_email)
        live = await self._repo.live_email_code(email, purpose)
        if live is None or (purpose == LINK and live.person_id != person_id):
            raise CodeExpired()
        expires = parse_iso(live.expires_at)
        if expires is None or expires <= utcnow() or live.attempts >= MAX_ATTEMPTS:
            await self._repo.use_email_code(live.id)
            raise CodeExpired()
        typed = re.sub(r"\D", "", code or "")
        if not hmac.compare_digest(live.code_hash, _hash(self._secret, email, typed)):
            await self._repo.count_email_code_attempt(live.id)
            left = MAX_ATTEMPTS - live.attempts - 1
            if left <= 0:
                await self._repo.use_email_code(live.id)
                raise CodeExpired()
            raise CodeWrong(left)
        await self._repo.use_email_code(live.id)
        return email
