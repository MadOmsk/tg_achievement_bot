"""Sending email (#162). One interface, `EmailSender`, so the rest of the bot
never knows how mail leaves the machine: today SMTP through the standard
library (any server — the VPS's own, or a provider's relay), and anything else
later is one more class here.

`build_sender` picks from the settings: SMTP when `SMTP_HOST` and `SMTP_FROM`
are set, the log when `EMAIL_LOG_CODES` is on (development only), otherwise
nothing — and with nothing the Mini App does not offer email at all.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol

from bot.config import Settings

log = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 20


class EmailSendError(Exception):
    """The message could not be handed to the mail server."""


class EmailSender(Protocol):
    async def send(self, to: str, subject: str, text: str) -> None: ...


class SmtpSender:
    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        *,
        security: str = "starttls",
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        if security not in ("starttls", "ssl", "none"):
            raise ValueError(f"unknown SMTP security {security!r}")
        self._host = host
        self._port = port
        self._sender = sender
        self._security = security
        self._username = username
        self._password = password

    async def send(self, to: str, subject: str, text: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)
        try:
            await asyncio.to_thread(self._send_blocking, message)
        except (OSError, smtplib.SMTPException) as exc:
            # Never the message itself in the log: it carries the code.
            raise EmailSendError(f"{type(exc).__name__}: {exc}") from None

    def _send_blocking(self, message: EmailMessage) -> None:
        context = ssl.create_default_context()
        if self._security == "ssl":
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                self._host, self._port, timeout=SMTP_TIMEOUT_SECONDS, context=context
            )
        else:
            server = smtplib.SMTP(self._host, self._port, timeout=SMTP_TIMEOUT_SECONDS)
        with server:
            if self._security == "starttls":
                server.starttls(context=context)
            if self._username and self._password:
                server.login(self._username, self._password)
            server.send_message(message)


class LogSender:
    """Development only: the message goes to the log instead of a mailbox."""

    async def send(self, to: str, subject: str, text: str) -> None:
        log.warning("EMAIL_LOG_CODES is on — not sent, to=%s subject=%r\n%s", to, subject, text)


def build_sender(settings: Settings) -> EmailSender | None:
    if settings.smtp_host and settings.smtp_from:
        return SmtpSender(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_from,
            security=settings.smtp_security,
            username=settings.smtp_username,
            password=settings.smtp_password.get_secret_value() if settings.smtp_password else None,
        )
    if settings.email_log_codes:
        return LogSender()
    return None
