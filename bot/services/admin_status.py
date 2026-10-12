"""What the super-admin's home shows, computed once for both surfaces (#176).

The bot's /admin home (`views/admin_home.py`) renders `AdminStatus` as text
and the Mini App's `GET /api/mini/admin` serializes the same object as JSON
— a counter added here appears in both.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import timedelta

from bot.constants import TokenStatus
from bot.db.repo import Repo
from bot.services import api_usage
from bot.services.admin_credentials import AdminCredentials, CredentialState
from bot.services.admin_settings import (
    DEFAULT_EMAIL_PROVIDER_DAILY,
    DEFAULT_EMAIL_SENDS_TOTAL,
    EMAIL_PROVIDER_DAILY_KEY,
    EMAIL_SENDS_TOTAL_KEY,
)
from bot.services.steam.client import RATE_WINDOWS as STEAM_WINDOWS
from bot.util import utcnow

# Steam's key has one: so many requests a day.
STEAM_LIMIT_DAY = next(limit for limit, span in STEAM_WINDOWS if span == api_usage.DAY)


@dataclass(frozen=True, slots=True)
class XboxWindow:
    """Xbox requests in one window, per account polled (owner, 2026-10-12):
    the median account and the busiest — Microsoft's budget is each
    person's, so a total would say nothing."""

    span: float
    median: float
    most: int


@dataclass(frozen=True, slots=True)
class CountWindow:
    """Requests made with one shared key in one window, and its limit."""

    span: float
    used: int
    limit: int | None


@dataclass(frozen=True, slots=True)
class TokenWindow:
    """Requests to the model in one window, and the tokens they spent."""

    span: float
    requests: int
    tokens: int


@dataclass(frozen=True, slots=True)
class ApiUsage:
    """Every outside API's load over 5 minutes, an hour and a day — in the
    order the home lists them: Xbox, Steam, PSN, Anthropic (hour and day)."""

    xbox: list[XboxWindow]
    steam: list[CountWindow]
    psn: list[CountWindow]
    anthropic: list[TokenWindow]


def api_load(accounts: int) -> ApiUsage:
    """`accounts`: the Xbox accounts polled — the median is over all of them,
    a quiet one counting as nought."""
    xbox: list[XboxWindow] = []
    for span in api_usage.WINDOWS:
        counts = sorted(api_usage.per_key(api_usage.XBOX, span).values())
        counts = [0] * max(0, accounts - len(counts)) + counts
        xbox.append(
            XboxWindow(
                span=span,
                median=statistics.median(counts) if counts else 0.0,
                most=counts[-1] if counts else 0,
            )
        )
    return ApiUsage(
        xbox=xbox,
        steam=[
            CountWindow(
                span,
                api_usage.count(api_usage.STEAM, span),
                STEAM_LIMIT_DAY if span == api_usage.DAY else None,
            )
            for span in api_usage.WINDOWS
        ],
        # Sony documents no limit, so none is claimed.
        psn=[
            CountWindow(span, api_usage.count(api_usage.PSN, span), None)
            for span in api_usage.WINDOWS
        ],
        anthropic=[
            TokenWindow(
                span,
                api_usage.count(api_usage.ANTHROPIC, span),
                api_usage.tokens(api_usage.ANTHROPIC, span),
            )
            for span in (api_usage.HOUR, api_usage.DAY)
        ],
    )


@dataclass(frozen=True, slots=True)
class MailUsage:
    """Sign-in codes sent in the last hour and day, against the app's own
    hourly cap and the mail service's daily one (owner, 2026-10-07)."""

    hour: int
    hour_limit: int
    day: int
    day_limit: int
    # The mail server they go through (`SMTP_HOST`), None when there is none.
    server: str | None = None


@dataclass(frozen=True, slots=True)
class AdminStatus:
    users: int
    excluded: int
    xbox_linked: int
    xbox_active: int
    xbox_broken: int
    steam_linked: int
    psn_linked: int
    chats: int
    api: ApiUsage
    mail: MailUsage
    credentials: list[CredentialState]

    def credential(self, name: str) -> CredentialState | None:
        return next((item for item in self.credentials if item.name == name), None)


async def mail_usage(repo: Repo, server: str | None = None) -> MailUsage:
    now = utcnow()
    hour = await repo.email_codes_sent_since(
        (now - timedelta(hours=1)).isoformat(timespec="seconds")
    )
    day = await repo.email_codes_sent_since((now - timedelta(days=1)).isoformat(timespec="seconds"))
    return MailUsage(
        hour=hour,
        hour_limit=await repo.get_int_setting(EMAIL_SENDS_TOTAL_KEY, DEFAULT_EMAIL_SENDS_TOTAL),
        day=day,
        day_limit=await repo.get_int_setting(
            EMAIL_PROVIDER_DAILY_KEY, DEFAULT_EMAIL_PROVIDER_DAILY
        ),
        server=server,
    )


async def admin_status(
    repo: Repo,
    *,
    credentials: AdminCredentials,
) -> AdminStatus:
    users = await repo.admin_users()
    chats = await repo.admin_chats()
    # Split by platform: a Steam-only person has no token row at all, and
    # counting them as "no login" would read as a broken Xbox login.
    xbox_linked = [u for u in users if u.xuid]
    xbox_active = sum(
        1 for u in xbox_linked if u.token_status == TokenStatus.ACTIVE and not u.is_excluded
    )
    return AdminStatus(
        users=len(users),
        excluded=sum(1 for u in users if u.is_excluded),
        xbox_linked=len(xbox_linked),
        xbox_active=xbox_active,
        xbox_broken=sum(1 for u in xbox_linked if u.token_status != TokenStatus.ACTIVE),
        steam_linked=sum(1 for u in users if u.steam_id),
        psn_linked=sum(1 for u in users if u.psn_account_id),
        chats=sum(1 for c in chats if c.is_active),
        api=api_load(xbox_active),
        mail=await mail_usage(repo, credentials.smtp.host if credentials.smtp else None),
        credentials=await credentials.states(),
    )
