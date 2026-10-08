"""The /admin home screen's own render (Follow-up 2026-09-06) — split out of
handlers/admin.py so poller/admin_refresh.py can reuse the exact same
rendering the manual command uses, same relationship views/online.py
already has with handlers/chat.py's /online and poller/online_refresh.py.

What it shows is `services/admin_status.py`'s, the same object the Mini
App's admin home serializes (#176); this module only words it.

Only the *home* screen lives here — /admin's sub-screens (users list, a
chat's card, the PSN test screen, ...) are still handlers/admin.py's own,
same as /online has no auto-refreshing equivalent for /who's picker.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.constants import TokenStatus
from bot.db.repo import Repo
from bot.i18n import translator
from bot.poller.fetcher import Fetcher
from bot.poller.steam_fetcher import SteamFetcher
from bot.services.admin_credentials import AdminCredentials
from bot.services.admin_status import admin_status
from bot.services.stats import local_now
from bot.util import humanize_ago

# Europe/Moscow — same default the rest of the project falls back to
# (schema.sql's chat_settings.tz_offset_min, config.py's Settings.tz) when
# nothing more specific applies. The admin panel isn't scoped to any one
# chat, so there is no per-chat offset to read here the way /online has.
_DEFAULT_TZ_OFFSET_MIN = 180


async def _key_status_line(
    status: str, checked_at: str | None, *, active_value: str, locale: str
) -> str:
    """Common rendering for the two shared-credential status lines below
    (SPEC 9, M-PSN-1's "мониторинг живости" paragraph, applied to Steam
    too) — a bare word would hide a stale check, so this always says when
    it last actually ran."""
    _ = translator("adminview", locale)
    if status == active_value:
        return (
            _("adminview-key-alive-checked", ago=humanize_ago(checked_at, locale))
            if checked_at
            else _("adminview-key-alive")
        )
    return (
        _("adminview-key-stale-checked", ago=humanize_ago(checked_at, locale))
        if checked_at
        else _("adminview-key-stale")
    )


def format_api_usage(windows: list[tuple[int, int, float]], *, locale: str) -> str:
    """A compact usage summary — how close the shared achievements
    rate limiter is to Microsoft's own windows (SPEC 4), a diagnostic against
    a bug in the poller, not a persisted budget."""
    _ = translator("adminview", locale)
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
    credentials: AdminCredentials,
    *,
    locale: str,
) -> tuple[str, InlineKeyboardMarkup]:
    _ = translator("adminview", locale)
    status = await admin_status(
        repo,
        credentials=credentials,
        xbox_usage=fetcher.api_usage(),
        steam_usage=steam_fetcher.api_usage(),
    )

    async def key_line(name: str, not_configured: str) -> str:
        # Steam's key is admin-settable and can be genuinely "not configured"
        # (#17), as PSN's NPSSO can, so both get the same three-way line.
        state = status.credential(name)
        if state is None or not state.configured:
            return _(not_configured)
        return await _key_status_line(
            state.status or TokenStatus.ACTIVE,
            state.checked_at,
            active_value=TokenStatus.ACTIVE,
            locale=locale,
        )

    # Same "always show when this was last true" treatment /online's table
    # gives its own header — this screen refreshes itself on a timer
    # (poller/admin_refresh.py), so a bare title alone would leave no way to
    # tell a fresh render from one that silently stopped updating.
    updated_label = local_now(_DEFAULT_TZ_OFFSET_MIN).strftime("%H:%M")
    mail = status.mail

    text = _(
        "adminview-home",
        updated=updated_label,
        users=status.users,
        excluded=status.excluded,
        xbox_linked=status.xbox_linked,
        xbox_active=status.xbox_active,
        xbox_broken=status.xbox_broken,
        steam_linked=status.steam_linked,
        psn_linked=status.psn_linked,
        chats=status.chats,
        xbox_usage=format_api_usage(status.xbox_usage, locale=locale),
        steam_usage=format_api_usage(status.steam_usage, locale=locale),
        steam_key_line=await key_line("steam", "adminview-steam-not-configured"),
        psn_key_line=await key_line("psn", "adminview-psn-not-configured"),
        psn_requests=status.psn_requests,
        mail_usage=_(
            "adminview-mail-usage",
            hour=mail.hour,
            hour_limit=mail.hour_limit,
            day=mail.day,
            day_limit=mail.day_limit,
        ),
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translator("admin", locale)("admin-settings-button"),
                    callback_data="a:set",
                )
            ],
            [InlineKeyboardButton(text=_("adminview-btn-users"), callback_data="a:users:0")],
            [InlineKeyboardButton(text=_("adminview-btn-chats"), callback_data="a:chats")],
            [InlineKeyboardButton(text=_("adminview-btn-keys"), callback_data="a:keys")],
        ]
    )
    return text, keyboard
