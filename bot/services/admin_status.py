"""What the super-admin's home shows, computed once for both surfaces (#176).

The bot's /admin home (`views/admin_home.py`) renders `AdminStatus` as text
and the Mini App's `GET /api/mini/admin` serializes the same object as JSON
— a counter added here appears in both.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from bot.constants import TokenStatus
from bot.db.repo import Repo
from bot.services.admin_credentials import AdminCredentials, CredentialState
from bot.services.admin_settings import (
    DEFAULT_EMAIL_PROVIDER_DAILY,
    DEFAULT_EMAIL_SENDS_TOTAL,
    EMAIL_PROVIDER_DAILY_KEY,
    EMAIL_SENDS_TOTAL_KEY,
)
from bot.services.psn.client import request_count_today
from bot.util import utcnow

# (used, limit, window in seconds) — a rate limiter's own view of its windows.
UsageWindow = tuple[int, int, float]


@dataclass(frozen=True, slots=True)
class MailUsage:
    """Sign-in codes sent in the last hour and day, against the app's own
    hourly cap and the mail service's daily one (owner, 2026-10-07)."""

    hour: int
    hour_limit: int
    day: int
    day_limit: int


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
    xbox_usage: list[UsageWindow]
    steam_usage: list[UsageWindow]
    # No known daily cap to compare against (nowhere documented) — a bare
    # count, not a ratio that would imply a number we don't have.
    psn_requests: int
    mail: MailUsage
    credentials: list[CredentialState]

    def credential(self, name: str) -> CredentialState | None:
        return next((item for item in self.credentials if item.name == name), None)


async def mail_usage(repo: Repo) -> MailUsage:
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
    )


async def admin_status(
    repo: Repo,
    *,
    credentials: AdminCredentials,
    xbox_usage: list[UsageWindow],
    steam_usage: list[UsageWindow],
) -> AdminStatus:
    users = await repo.admin_users()
    chats = await repo.admin_chats()
    # Split by platform: a Steam-only person has no token row at all, and
    # counting them as "no login" would read as a broken Xbox login.
    xbox_linked = [u for u in users if u.xuid]
    return AdminStatus(
        users=len(users),
        excluded=sum(1 for u in users if u.is_excluded),
        xbox_linked=len(xbox_linked),
        xbox_active=sum(
            1 for u in xbox_linked if u.token_status == TokenStatus.ACTIVE and not u.is_excluded
        ),
        xbox_broken=sum(1 for u in xbox_linked if u.token_status != TokenStatus.ACTIVE),
        steam_linked=sum(1 for u in users if u.steam_id),
        psn_linked=sum(1 for u in users if u.psn_account_id),
        chats=sum(1 for c in chats if c.is_active),
        xbox_usage=xbox_usage,
        steam_usage=steam_usage,
        psn_requests=request_count_today(),
        mail=await mail_usage(repo),
        credentials=await credentials.states(),
    )
