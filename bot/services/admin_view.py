"""The /admin home screen's own render (Follow-up 2026-09-06) — split out of
handlers/admin.py so poller/admin_refresh.py can reuse the exact same
rendering the manual command uses, same relationship services/online_view.py
already has with handlers/chat.py's /online and poller/online_refresh.py.

Only the *home* screen lives here — /admin's sub-screens (users list, a
chat's card, the PSN test screen, ...) are still handlers/admin.py's own,
same as /online has no auto-refreshing equivalent for /who's picker.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.constants import TokenStatus
from bot.db.repo import Repo
from bot.i18n import gettext
from bot.poller.fetcher import Fetcher
from bot.poller.steam_fetcher import SteamFetcher
from bot.services.psn.auth import STATUS_NOT_CONFIGURED as PSN_NOT_CONFIGURED
from bot.services.psn.auth import PsnAuth
from bot.services.psn.client import request_count_today
from bot.services.stats import local_now
from bot.services.steam.auth import STATUS_NOT_CONFIGURED as STEAM_NOT_CONFIGURED
from bot.services.steam.auth import SteamAuth
from bot.util import humanize_ago

_ = lambda key, **kwargs: gettext("adminview", key, **kwargs)  # noqa: E731

# Europe/Moscow — same default the rest of the project falls back to
# (schema.sql's chat_settings.tz_offset_min, config.py's Settings.tz) when
# nothing more specific applies. The admin panel isn't scoped to any one
# chat, so there is no per-chat offset to read here the way /online has.
_DEFAULT_TZ_OFFSET_MIN = 180


async def _key_status_line(status: str, checked_at: str | None, *, active_value: str) -> str:
    """Common rendering for the two shared-credential status lines below
    (SPEC 9, M-PSN-1's "мониторинг живости" paragraph, applied to Steam
    too) — a bare word would hide a stale check, so this always says when
    it last actually ran."""
    if status == active_value:
        return (
            _("adminview-key-alive-checked", ago=humanize_ago(checked_at))
            if checked_at
            else _("adminview-key-alive")
        )
    return (
        _("adminview-key-stale-checked", ago=humanize_ago(checked_at))
        if checked_at
        else _("adminview-key-stale")
    )


def _format_api_usage(windows: list[tuple[int, int, float]]) -> str:
    """A compact usage summary — how close the shared achievements
    rate limiter is to Microsoft's own windows (SPEC 4), a diagnostic against
    a bug in the poller, not a persisted budget."""
    parts = []
    for used, limit, span in windows:
        label = (
            _("adminview-usage-min", span=f"{span / 60:g}")
            if span >= 60
            else _("adminview-usage-sec", span=f"{span:g}")
        )
        parts.append(_("adminview-usage-part", used=used, limit=limit, label=label))
    return " · ".join(parts) if parts else _("adminview-usage-none")


async def render_admin_home(
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_auth: PsnAuth,
    steam_auth: SteamAuth,
) -> tuple[str, InlineKeyboardMarkup]:
    users = await repo.admin_users()
    chats = await repo.admin_chats()

    # Split by platform (2026-09-05 follow-up): configured/not configured
    # only ever meant Xbox's own token — lumping Steam-only people (no
    # token row at all, token_status is None for them) into not configured
    # made them look like a broken Xbox login instead of "no Xbox at all".
    xbox_linked = [u for u in users if u.xuid]
    steam_linked = [u for u in users if u.steam_id]
    psn_linked = [u for u in users if u.psn_account_id]
    xbox_active = sum(
        1 for u in xbox_linked if u.token_status == TokenStatus.ACTIVE and not u.is_excluded
    )
    xbox_broken = sum(1 for u in xbox_linked if u.token_status != TokenStatus.ACTIVE)
    excluded = sum(1 for u in users if u.is_excluded)

    # As of #17 the Steam key is admin-settable and can be genuinely "not
    # configured" (same as PSN's NPSSO), so it gets the same three-way line.
    steam_status = await steam_auth.status()
    steam_checked = await steam_auth.checked_at()
    psn_status = await psn_auth.status()
    psn_checked = await psn_auth.checked_at()
    psn_key_line = (
        _("adminview-psn-not-configured")
        if psn_status == PSN_NOT_CONFIGURED
        else await _key_status_line(psn_status, psn_checked, active_value=TokenStatus.ACTIVE)
    )
    steam_key_line = (
        _("adminview-steam-not-configured")
        if steam_status == STEAM_NOT_CONFIGURED
        else await _key_status_line(steam_status, steam_checked, active_value=TokenStatus.ACTIVE)
    )

    # Same "always show when this was last true" treatment /online's table
    # gives its own header (Follow-up 2026-09-06) — this screen now
    # refreshes itself on a timer (poller/admin_refresh.py), so a bare
    # An admin title alone would leave no way to tell a fresh render
    # from one that silently stopped updating.
    updated_label = local_now(_DEFAULT_TZ_OFFSET_MIN).strftime("%H:%M")

    text = _(
        "adminview-home",
        updated=updated_label,
        users=len(users),
        excluded=excluded,
        xbox_linked=len(xbox_linked),
        xbox_active=xbox_active,
        xbox_broken=xbox_broken,
        steam_linked=len(steam_linked),
        psn_linked=len(psn_linked),
        chats=sum(1 for c in chats if c.is_active),
        xbox_usage=_format_api_usage(fetcher.api_usage()),
        steam_usage=_format_api_usage(steam_fetcher.api_usage()),
        steam_key_line=steam_key_line,
        psn_key_line=psn_key_line,
        # No known daily cap to compare against (SPEC 9, M-PSN-1 checklist
        # item 4 — nowhere documented) — a bare count, not a "used/limit"
        # ratio that would imply a number we don't actually have.
        psn_requests=request_count_today(),
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("adminview-btn-newusers"), callback_data="a:newusers")],
            [InlineKeyboardButton(text=_("adminview-btn-limits"), callback_data="a:limits")],
            [InlineKeyboardButton(text=_("adminview-btn-users"), callback_data="a:users:0")],
            [InlineKeyboardButton(text=_("adminview-btn-chats"), callback_data="a:chats")],
            [InlineKeyboardButton(text=_("adminview-btn-keys"), callback_data="a:keys")],
            [InlineKeyboardButton(text=_("adminview-btn-psntest"), callback_data="a:psntest")],
        ]
    )
    return text, keyboard
