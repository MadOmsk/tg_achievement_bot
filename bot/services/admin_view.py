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

from bot.db.repo import Repo
from bot.poller.fetcher import Fetcher
from bot.poller.service_health import STATUS_ACTIVE as STEAM_KEY_ACTIVE
from bot.poller.service_health import STEAM_CHECKED_AT_KEY, STEAM_STATUS_KEY
from bot.poller.steam_fetcher import SteamFetcher
from bot.services.psn.auth import STATUS_ACTIVE as PSN_KEY_ACTIVE
from bot.services.psn.auth import STATUS_NOT_CONFIGURED as PSN_NOT_CONFIGURED
from bot.services.psn.auth import PsnAuth
from bot.services.psn.client import request_count_today
from bot.services.stats import local_now
from bot.util import humanize_ago

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
        return f"✅ жив, проверен {humanize_ago(checked_at)}" if checked_at else "✅ жив"
    return f"⚠️ протух, проверен {humanize_ago(checked_at)}" if checked_at else "⚠️ протух"


def _format_api_usage(windows: list[tuple[int, int, float]]) -> str:
    """ "3/100 за 15с · 12/300 за 5 мин" — how close the shared achievements
    rate limiter is to Microsoft's own windows (SPEC 4), a diagnostic against
    a bug in the poller, not a persisted budget."""
    parts = []
    for used, limit, span in windows:
        label = f"{span / 60:g} мин" if span >= 60 else f"{span:g}с"
        parts.append(f"{used}/{limit} за {label}")
    return " · ".join(parts) if parts else "нет данных"


async def render_admin_home(
    repo: Repo, fetcher: Fetcher, steam_fetcher: SteamFetcher, psn_auth: PsnAuth
) -> tuple[str, InlineKeyboardMarkup]:
    users = await repo.admin_users()
    chats = await repo.admin_chats()

    # Split by platform (2026-09-05 follow-up): "вход активен"/"без входа"
    # only ever meant Xbox's own token — lumping Steam-only people (no
    # token row at all, token_status is None for them) into "без входа"
    # made them look like a broken Xbox login instead of "no Xbox at all".
    xbox_linked = [u for u in users if u.xuid]
    steam_linked = [u for u in users if u.steam_id]
    psn_linked = [u for u in users if u.psn_account_id]
    xbox_active = sum(1 for u in xbox_linked if u.token_status == "active" and not u.is_excluded)
    xbox_broken = sum(1 for u in xbox_linked if u.token_status != "active")
    excluded = sum(1 for u in users if u.is_excluded)

    # Steam's own key is a permanent .env secret (config.py) — no "not
    # configured" state worth showing separately here, every Steam feature
    # already answers that on its own when it's unset.
    steam_key_status = await repo.get_app_setting(STEAM_STATUS_KEY, STEAM_KEY_ACTIVE)
    steam_key_checked = await repo.get_app_setting(STEAM_CHECKED_AT_KEY)
    psn_status = await psn_auth.status()
    psn_checked = await psn_auth.checked_at()
    psn_key_line = (
        "не настроен — «🏆 Трофеи PSN» ниже примет NPSSO"
        if psn_status == PSN_NOT_CONFIGURED
        else await _key_status_line(psn_status, psn_checked, active_value=PSN_KEY_ACTIVE)
    )
    steam_key_line = await _key_status_line(
        steam_key_status, steam_key_checked, active_value=STEAM_KEY_ACTIVE
    )

    # Same "always show when this was last true" treatment /online's table
    # gives its own header (Follow-up 2026-09-06) — this screen now
    # refreshes itself on a timer (poller/admin_refresh.py), so a bare
    # "Администрирование" title would leave no way to tell a fresh render
    # from one that silently stopped updating.
    updated_label = local_now(_DEFAULT_TZ_OFFSET_MIN).strftime("%H:%M")

    text = (
        f"⚙️ Администрирование  ·  обновлено {updated_label}\n\n"
        f"Пользователей: {len(users)} (исключено: {excluded})\n"
        f"  XBOX:  {len(xbox_linked)} (вход активен: {xbox_active}, без входа: {xbox_broken})\n"
        f"  Steam: {len(steam_linked)}\n"
        f"  PSN:   {len(psn_linked)}\n"
        f"Чатов:          {sum(1 for c in chats if c.is_active)}\n"
        f"API XBOX (достижения):  {_format_api_usage(fetcher.api_usage())}\n"
        f"API Steam (достижения): {_format_api_usage(steam_fetcher.api_usage())}\n"
        f"Ключ Steam: {steam_key_line}\n"
        f"Ключ PSN:   {psn_key_line}\n"
        # No known daily cap to compare against (SPEC 9, M-PSN-1 checklist
        # item 4 — nowhere documented) — a bare count, not a "used/limit"
        # ratio that would imply a number we don't actually have.
        f"Запросов к PSN за сутки: {request_count_today()}"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 Новые пользователи ▸", callback_data="a:newusers")],
            [InlineKeyboardButton(text="⚙️ Глобальные настройки ▸", callback_data="a:limits")],
            [InlineKeyboardButton(text="Пользователи ▸", callback_data="a:users:0")],
            [InlineKeyboardButton(text="Чаты ▸", callback_data="a:chats")],
            [InlineKeyboardButton(text="🏆 Трофеи PSN (тест) ▸", callback_data="a:psntest")],
        ]
    )
    return text, keyboard
