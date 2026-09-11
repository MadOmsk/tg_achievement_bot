"""/admin — the operator's screen (SPEC 6.4). UI only: all data comes from services.

One message that redraws itself, like the user panel. Access is the
ADMIN_TG_IDS list from the config, checked on the router so that no single
handler can forget it.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from datetime import timedelta

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import BaseFilter, Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram_i18n import I18nContext

from bot.config import Settings
from bot.constants import Platform, PresenceState, RarityMode, SettingKey, TokenStatus
from bot.db.repo import AdminUserRow, ChatTarget, PlatformLink, Repo, User
from bot.handlers.hltb import (
    DEFAULT_PAGE_SIZE,
    DEFAULT_RESULTS_LIMIT,
    PAGE_SIZE_KEY,
    RESULTS_LIMIT_KEY,
)
from bot.handlers.keyboards import (
    COMMON_OFFSETS_HOURS,
    format_offset,
    format_rarity,
    next_rarity_mode,
)
from bot.i18n import translator
from bot.poller.daily import DEFAULT_TABLE_TOP, TOP_LIMIT_KEY
from bot.poller.fetcher import Fetcher
from bot.poller.message_cleanup import DEFAULT_TTL_MINUTES as DEFAULT_SYSTEM_MESSAGE_TTL_MIN
from bot.poller.message_cleanup import TTL_SETTING_KEY as SYSTEM_MESSAGE_TTL_KEY
from bot.poller.online_refresh import DEFAULT_REFRESH_INTERVAL_MIN as DEFAULT_ONLINE_REFRESH_MIN
from bot.poller.online_refresh import DEFAULT_TTL_HOURS as DEFAULT_ONLINE_REFRESH_TTL_HOURS
from bot.poller.online_refresh import REFRESH_INTERVAL_KEY as ONLINE_REFRESH_INTERVAL_KEY
from bot.poller.online_refresh import TTL_HOURS_KEY as ONLINE_REFRESH_TTL_KEY
from bot.poller.psn_fetcher import PsnFetcher
from bot.poller.service_health import (
    DEFAULT_KEY_CHECK_INTERVAL_MIN,
    KEY_CHECK_INTERVAL_KEY,
)
from bot.poller.steam_fetcher import SteamFetcher
from bot.services.achievements import (
    COMPLETED_BADGE,
    plural_achievements,
    plural_trophies,
    visibility_status_text,
)
from bot.services.admin_view import render_admin_home
from bot.services.psn.auth import STATUS_NOT_CONFIGURED as PSN_NOT_CONFIGURED
from bot.services.psn.auth import PsnAuth
from bot.services.psn.client import (
    PsnClientSetupError,
    PsnTokenDeadError,
)
from bot.services.stats import month_cutoff_utc, today_cutoff_utc
from bot.services.steam.auth import (
    STATUS_NOT_CONFIGURED as STEAM_NOT_CONFIGURED,
)
from bot.services.steam.auth import (
    SteamAuth,
    SteamKeyInvalidError,
)
from bot.services.tables import truncate_name
from bot.services.translate.auth import (
    STATUS_NOT_CONFIGURED as ANTHROPIC_NOT_CONFIGURED,
)
from bot.services.translate.auth import (
    AnthropicAuth,
    AnthropicKeyInvalidError,
)
from bot.util import humanize_ago, parse_utc_offset, utcnow

log = logging.getLogger(__name__)

router = Router(name="admin")


PAGE_SIZE = 8

STATUS_ICON = {
    TokenStatus.ACTIVE: "✅",
    TokenStatus.INVALID: "⚠️",
    TokenStatus.REVOKED: "🔕",
}


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, settings: Settings) -> bool:
        user = getattr(event, "from_user", None)
        return user is not None and settings.is_admin(user.id)


router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


async def _replace_admin_home(
    bot: Bot,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_auth: PsnAuth,
    steam_auth: SteamAuth,
    admin_id: int,
    prefix: str = "",
) -> None:
    """Sends a fresh /admin home screen as a brand-new message, replacing
    whatever this admin had open before, and (re)arms the auto-refresh job
    for it (Follow-up 2026-09-06) — shared by the bare /admin command and
    every flow that confirms a change and redraws home as a new message
    rather than editing the current one in place (a:home's own callback
    does the latter, so it never needs this)."""
    # This one knows whose panel it is rebuilding, so it reads the locale
    # itself rather than making every caller carry it (#48).
    locale = await repo.user_locale(admin_id)
    text, markup = await render_admin_home(
        repo, fetcher, steam_fetcher, psn_auth, steam_auth, locale=locale
    )
    if prefix:
        text = f"{prefix}\n\n{text}"
    previous = await repo.get_admin_panel_refresh(admin_id)
    if previous is not None:
        with contextlib.suppress(Exception):
            await bot.delete_message(admin_id, previous.message_id)
    sent = await bot.send_message(admin_id, text, reply_markup=markup)
    interval = await repo.get_int_setting(KEY_CHECK_INTERVAL_KEY, DEFAULT_KEY_CHECK_INTERVAL_MIN)
    if interval > 0:
        await repo.start_admin_panel_refresh(admin_id, sent.message_id)


@router.message(Command("admin"), F.chat.type == ChatType.PRIVATE)
async def admin_command(
    message: Message,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_auth: PsnAuth,
    steam_auth: SteamAuth,
    bot: Bot,
) -> None:
    _awaiting_input.pop(message.from_user.id, None)  # a fresh /admin cancels any pending flow
    await _replace_admin_home(
        bot, repo, fetcher, steam_fetcher, psn_auth, steam_auth, message.chat.id
    )


@router.callback_query(F.data == "a:home")
async def admin_home(
    callback: CallbackQuery,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_auth: PsnAuth,
    steam_auth: SteamAuth,
    i18n: I18nContext,
) -> None:
    _awaiting_input.pop(callback.from_user.id, None)
    await _redraw(
        callback,
        *await render_admin_home(
            repo, fetcher, steam_fetcher, psn_auth, steam_auth, locale=i18n.locale
        ),
    )


# --------------------------------------------------------- Platform keys (#17)

# The "Ключи платформ" screen, where an admin sets/changes/clears the shared
# Steam key and PSN NPSSO — both take free-text answers, and the message
# handler for them is registered before the free-text numeric/timezone
# handlers below on purpose: aiogram tries message handlers in registration
# order and stops at the first whose filter matches, so an admin's answer
# here (a key or an NPSSO) must be claimed by this filter before the generic
# ones get a chance at it.
#
# This used to also host a PSN trophy-lookup test screen (a live, uncached
# carve-out of SPEC 1.5's cache-only rule, from before any of this was wired
# into /stats) — removed once this Keys screen covered NPSSO management on
# its own and the test screen had nothing left to justify a live API call
# outside a background job.
STEAM_KEY_KEY = "steam_api_key"
PSN_NPSSO_KEY = "psn_npsso"
# Anthropic (2026-09-09 user request) — achievement-description translation
# only, same admin-settable-shared-credential shape as the two above (#17).
ANTHROPIC_KEY_KEY = "anthropic_api_key"


class AwaitingAdminTextInput(BaseFilter):
    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        if user is None:
            return False
        pending = _awaiting_input.get(user.id)
        return pending is not None and pending[0] in (
            STEAM_KEY_KEY,
            PSN_NPSSO_KEY,
            ANTHROPIC_KEY_KEY,
        )


def _cancel_input_keyboard(*, locale: str) -> InlineKeyboardMarkup:
    _ = translator("admin", locale)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("admin-cancel"), callback_data="a:psncancel")]
        ]
    )


# ---- Platform keys (#17) ----


async def _keys_screen(
    steam_auth: SteamAuth, psn_auth: PsnAuth, anthropic_auth: AnthropicAuth, *, locale: str
) -> tuple[str, InlineKeyboardMarkup]:
    _ = translator("admin", locale)
    steam_configured = await steam_auth.status() != STEAM_NOT_CONFIGURED
    psn_configured = await psn_auth.status() != PSN_NOT_CONFIGURED
    anthropic_configured = await anthropic_auth.status() != ANTHROPIC_NOT_CONFIGURED
    text = _(
        "admin-keys-screen",
        steam=_("admin-keys-set") if steam_configured else _("admin-keys-unset"),
        psn=_("admin-keys-set") if psn_configured else _("admin-keys-unset"),
        anthropic=_("admin-keys-set") if anthropic_configured else _("admin-keys-unset"),
    )
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=_("admin-keys-steam-change") if steam_configured else _("admin-keys-steam-add"),
            callback_data="a:keyset:steam",
        )
    )
    if steam_configured:
        builder.row(
            InlineKeyboardButton(text=_("admin-keys-steam-clear"), callback_data="a:keyclr:steam")
        )
    builder.row(
        InlineKeyboardButton(
            text=_("admin-keys-psn-change") if psn_configured else _("admin-keys-psn-add"),
            callback_data="a:keyset:psn",
        )
    )
    if psn_configured:
        builder.row(
            InlineKeyboardButton(text=_("admin-keys-psn-clear"), callback_data="a:keyclr:psn")
        )
    builder.row(
        InlineKeyboardButton(
            text=_("admin-keys-anthropic-change")
            if anthropic_configured
            else _("admin-keys-anthropic-add"),
            callback_data="a:keyset:anthropic",
        )
    )
    if anthropic_configured:
        builder.row(
            InlineKeyboardButton(
                text=_("admin-keys-anthropic-clear"), callback_data="a:keyclr:anthropic"
            )
        )
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data="a:home"))
    return text, builder.as_markup()


@router.callback_query(F.data == "a:keys")
async def keys_menu(
    callback: CallbackQuery,
    steam_auth: SteamAuth,
    psn_auth: PsnAuth,
    anthropic_auth: AnthropicAuth,
    i18n: I18nContext,
) -> None:
    _awaiting_input.pop(callback.from_user.id, None)
    await _redraw(
        callback, *await _keys_screen(steam_auth, psn_auth, anthropic_auth, locale=i18n.locale)
    )


# One parameterized handler per action instead of a Steam/PSN pair each
# (2026-09-09 refactor, same shape reset_platform_confirm/_confirmed below
# already used for all three platforms) — callback_data's own trailing
# segment says which key, same "()" wiring on either platform's button.
# Anthropic (2026-09-09) slotted into the same dicts rather than a third
# handler pair — exactly the duplication this refactor exists to avoid.
_KEYSET_APP_SETTING_KEY = {
    "steam": STEAM_KEY_KEY,
    "psn": PSN_NPSSO_KEY,
    "anthropic": ANTHROPIC_KEY_KEY,
}
_KEYSET_PROMPT = {
    STEAM_KEY_KEY: "admin-keys-steam-prompt",
    PSN_NPSSO_KEY: "admin-keys-psn-prompt",
    ANTHROPIC_KEY_KEY: "admin-keys-anthropic-prompt",
}


@router.callback_query(F.data.startswith("a:keyset:"))
async def keys_set(callback: CallbackQuery, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    platform = callback.data.rsplit(":", 1)[1]
    key = _KEYSET_APP_SETTING_KEY[platform]
    _awaiting_input[callback.from_user.id] = (key, None)
    await _redraw(callback, _(_KEYSET_PROMPT[key]), _cancel_input_keyboard(locale=i18n.locale))


@router.callback_query(F.data.startswith("a:keyclr:"))
async def keys_clear(
    callback: CallbackQuery,
    steam_auth: SteamAuth,
    psn_auth: PsnAuth,
    anthropic_auth: AnthropicAuth,
    i18n: I18nContext,
) -> None:
    assert callback.data is not None
    platform = callback.data.rsplit(":", 1)[1]
    auth: SteamAuth | PsnAuth | AnthropicAuth = {
        "steam": steam_auth,
        "psn": psn_auth,
        "anthropic": anthropic_auth,
    }[platform]
    await auth.clear(callback.from_user.id)
    _awaiting_input.pop(callback.from_user.id, None)
    await _redraw(
        callback, *await _keys_screen(steam_auth, psn_auth, anthropic_auth, locale=i18n.locale)
    )


@router.callback_query(F.data == "a:psncancel")
async def admin_text_input_cancel(
    callback: CallbackQuery,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_auth: PsnAuth,
    steam_auth: SteamAuth,
    i18n: I18nContext,
) -> None:
    """The way out of a still-armed key/NPSSO retry (Follow-up 2026-09-06,
    found live: a stray later message got misread as the next answer once
    nobody explicitly cancelled) — drops back to the admin home screen."""
    _awaiting_input.pop(callback.from_user.id, None)
    await _redraw(
        callback,
        *await render_admin_home(
            repo, fetcher, steam_fetcher, psn_auth, steam_auth, locale=i18n.locale
        ),
    )


@router.message(F.chat.type == ChatType.PRIVATE, AwaitingAdminTextInput())
async def admin_text_input(
    message: Message,
    psn_auth: PsnAuth,
    steam_auth: SteamAuth,
    anthropic_auth: AnthropicAuth,
    i18n: I18nContext,
) -> None:
    _ = translator("admin", i18n.locale)
    assert message.from_user is not None and message.text is not None
    pending = _awaiting_input.get(message.from_user.id)
    assert pending is not None
    key = pending[0]
    raw = message.text.strip()

    if key == STEAM_KEY_KEY:
        try:
            await steam_auth.set_key(raw, message.from_user.id)
        except SteamKeyInvalidError:
            # Stays armed — a typo is worth just retrying — but the explicit
            # cancel is there for a stray later paste, same as PSN below.
            await message.answer(
                _("admin-keys-steam-invalid"),
                reply_markup=_cancel_input_keyboard(locale=i18n.locale),
            )
            return
        _awaiting_input.pop(message.from_user.id, None)
        text, markup = await _keys_screen(steam_auth, psn_auth, anthropic_auth, locale=i18n.locale)
        await message.answer(_("admin-keys-steam-saved", text=text), reply_markup=markup)
        return

    if key == PSN_NPSSO_KEY:
        try:
            await psn_auth.set_npsso(raw, message.from_user.id)
        except PsnTokenDeadError:
            # Stays armed on purpose — a typo is worth just retrying,
            # not a trip back through /admin — but a stray later message
            # (found live 2026-09-06: a repeated paste while debugging got
            # misread as a PSN Online ID once the state moved on) needs an
            # explicit way out too, not just "send something else".
            await message.answer(
                _("admin-psn-npsso-invalid"),
                reply_markup=_cancel_input_keyboard(locale=i18n.locale),
            )
            return
        except PsnClientSetupError as exc:
            # Found live 2026-09-06: psnawp couldn't even construct its own
            # client (a sandboxed temp dir) and the admin got no reply at
            # all — this is deliberately a different message from the one
            # above, so a real bug doesn't get blamed on the NPSSO itself.
            log.exception("admin_text_input: could not set up the PSN client")
            await message.answer(
                _("admin-psn-client-error", error=exc),
                reply_markup=_cancel_input_keyboard(locale=i18n.locale),
            )
            return
        _awaiting_input.pop(message.from_user.id, None)
        text, markup = await _keys_screen(steam_auth, psn_auth, anthropic_auth, locale=i18n.locale)
        await message.answer(_("admin-keys-psn-saved", text=text), reply_markup=markup)
        return

    if key == ANTHROPIC_KEY_KEY:
        try:
            await anthropic_auth.set_key(raw, message.from_user.id)
        except AnthropicKeyInvalidError:
            # Same "stays armed, typo is worth just retrying" shape as
            # Steam/PSN above.
            await message.answer(
                _("admin-keys-anthropic-invalid"),
                reply_markup=_cancel_input_keyboard(locale=i18n.locale),
            )
            return
        _awaiting_input.pop(message.from_user.id, None)
        text, markup = await _keys_screen(steam_auth, psn_auth, anthropic_auth, locale=i18n.locale)
        await message.answer(_("admin-keys-anthropic-saved", text=text), reply_markup=markup)
        return


@router.callback_query(F.data == "a:newusers")
async def new_user_defaults_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    await _redraw(callback, *await _new_user_defaults(repo, locale=i18n.locale))


@router.callback_query(F.data == "a:defaultrarity")
async def default_rarity_cycle(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    current = await repo.get_app_setting(DEFAULT_RARITY_MODE_KEY, DEFAULT_RARITY_MODE_DEFAULT)
    assert current is not None
    mode = next_rarity_mode(current)
    await repo.set_app_setting(DEFAULT_RARITY_MODE_KEY, mode, callback.from_user.id)
    await _redraw(callback, *await _new_user_defaults(repo, locale=i18n.locale))


@router.callback_query(F.data == "a:defaultlinks")
async def default_show_links_toggle(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    current = await repo.get_int_setting(DEFAULT_SHOW_LINKS_KEY, int(DEFAULT_SHOW_LINKS_DEFAULT))
    await repo.set_app_setting(
        DEFAULT_SHOW_LINKS_KEY, "0" if current else "1", callback.from_user.id
    )
    await _redraw(callback, *await _new_user_defaults(repo, locale=i18n.locale))


# ------------------------------------------------------ free-text numeric settings

# Row-cap settings (always global — no per-chat meaning) and the per-chat
# rare threshold share one "type a number, not a button" flow — free values
# a handful of preset buttons could not cover anyway. Keyed by tg_id ->
# (which setting, which chat — None for a global row-cap), so a stray digit
# typed by an admin who isn't in this flow is never mistaken for input, and
# the one regex handler below knows which validation and target apply.
_awaiting_input: dict[int, tuple[str, int | None]] = {}

RARE_THRESHOLD_MIN = 0.01
RARE_THRESHOLD_MAX = 100.0
LIMIT_MIN = 1
LIMIT_MAX = 50

# Anti-flood filter (2026-09-09 user request) — per-chat, admin-set like the
# rare threshold above. flood_limit's own 0 means "off for this chat", same
# convention as min_gamerscore/summary_top_limit.
FLOOD_LIMIT_MIN = 0
FLOOD_LIMIT_MAX = 50
FLOOD_WINDOW_MIN = 1
FLOOD_WINDOW_MAX = 1440  # 24h — a longer buffer than that stops being "soon"
# What the on/off toggle below turns flood_limit *back on* to — matches
# chat_settings' own schema default (schema.sql), so a chat that never
# touched this setting and one that was switched off and back on land on
# the same starting point.
FLOOD_LIMIT_DEFAULT = 3

# Chat-scoped keys sharing numeric_setting_input()'s "type a number" flow
# with the always-global NUMERIC_SETTINGS above (rare_threshold_percent's
# own comment there explains the split).
_CHAT_SCOPED_KEYS = ("rare_threshold_percent", "flood_limit", "flood_window_minutes")

# What a brand-new subscription starts at (Repo.subscribe) — used to be a
# flat DEFAULT 'all' baked into the subscriptions table (schema.sql), now an
# admin-configurable app_settings row instead, same cycling button/helpers
# the personal and per-chat toggles already use (keyboards.py) rather than
# the free-text numeric flow above — 'all'/'rare'/'hidden' isn't a number.
DEFAULT_RARITY_MODE_KEY = "default_rarity_mode"
DEFAULT_RARITY_MODE_DEFAULT = RarityMode.ALL

# What a brand-new person's user_settings row starts with (Repo.ensure_user,
# Follow-up 2026-09-06) — same admin-configurable-default shape as
# DEFAULT_RARITY_MODE_KEY above, just a plain on/off instead of a cycle
# through three modes.
DEFAULT_SHOW_LINKS_KEY = "default_show_profile_links"
DEFAULT_SHOW_LINKS_DEFAULT = "0"


def unlimited_label(locale: str) -> str:
    """What a 0 renders as in the numeric-settings screens. Was a
    module-level constant, which froze whichever locale loaded first (#48) —
    the same trap PLATFORM_LABEL and HELP_TEXT had."""
    return translator("admin", locale)("admin-unlimited")


# stats_games_limit's own (key, default) belong to handlers/chat.py by rights
# (same as the other five, each imported from wherever it actually lives) —
# but chat.py already imports IsAdmin from this module, so importing back
# from chat.py here would be circular. Duplicated on purpose, just this one.
_DEFAULT_STATS_GAMES_LIMIT = 15


@dataclass(frozen=True, slots=True)
class NumericSetting:
    """One row of the "type a number" admin flow (2026-09-05 refactor —
    replaces five parallel dicts, all keyed by the same setting names, with
    one). `zero_label` only matters when `min == 0`; a setting that doesn't
    allow 0 never reaches _format_limit's zero branch at all."""

    label: str
    default: int
    min: int = LIMIT_MIN
    max: int = LIMIT_MAX
    zero_label: str = "admin-unlimited"


# Every admin-configurable count/limit/interval in the bot, one place —
# each (key, default) pair still lives with the code that actually falls
# back to it (imported above), so this registry can't drift from reality
# the way five hand-typed dicts eventually would have.
NUMERIC_SETTINGS: dict[str, NumericSetting] = {
    TOP_LIMIT_KEY: NumericSetting("admin-setting-summary-rows", DEFAULT_TABLE_TOP, min=0),
    # SPEC 1.6: both render into a <blockquote expandable>, not a fixed-width
    # table — an "unlimited" list fits there just fine, so these two alone
    # allow 0 for "no cap". Everything else below stays at min=1: a page
    # size or a search pool of 0 is just broken, not "show everything".
    SettingKey.STATS_GAMES_LIMIT: NumericSetting(
        "admin-setting-stats-games", _DEFAULT_STATS_GAMES_LIMIT, min=0
    ),
    RESULTS_LIMIT_KEY: NumericSetting("admin-setting-hltb-results", DEFAULT_RESULTS_LIMIT),
    # Feeds Telegram inline-keyboard rows directly — 50 buttons on one page
    # would be unusable, unlike the two above.
    PAGE_SIZE_KEY: NumericSetting("admin-setting-hltb-page", DEFAULT_PAGE_SIZE, max=10),
    # These two's own 0 means something else again — "off", not "no cap".
    SYSTEM_MESSAGE_TTL_KEY: NumericSetting(
        "admin-setting-system-ttl",
        DEFAULT_SYSTEM_MESSAGE_TTL_MIN,
        min=0,
        max=60,
        zero_label="admin-disabled",
    ),
    ONLINE_REFRESH_INTERVAL_KEY: NumericSetting(
        "admin-setting-online-interval",
        DEFAULT_ONLINE_REFRESH_MIN,
        min=0,
        max=60,
        zero_label="admin-disabled",
    ),
    # Stays at the default min (1): a 0-hour window is just "off" spelled a
    # more confusing way than the interval's own off switch already is.
    ONLINE_REFRESH_TTL_KEY: NumericSetting(
        "admin-setting-online-ttl", DEFAULT_ONLINE_REFRESH_TTL_HOURS, max=24
    ),
    # One shared cadence for two things (Follow-up 2026-09-06): how often
    # poller/service_health.py rechecks the Steam/PSN keys, AND how often
    # the /admin home screen refreshes itself in place — deliberately the
    # same knob, not two settings that merely start out equal, since the
    # panel's own numbers (key status, request counts) are only ever as
    # fresh as the last health check anyway. No off switch (unlike the
    # online-refresh interval above): silently killing the key-dead alert
    # by tweaking a "refresh interval" setting would be a real footgun.
    KEY_CHECK_INTERVAL_KEY: NumericSetting(
        "admin-setting-key-check",
        DEFAULT_KEY_CHECK_INTERVAL_MIN,
        min=1,
        max=60,
    ),
}


def _format_limit(key: str, value: str, *, locale: str) -> str:
    _ = translator("admin", locale)
    spec = NUMERIC_SETTINGS[key]
    return _(spec.zero_label) if value == "0" else value


def _setting_label(spec: NumericSetting, *, locale: str) -> str:
    _ = translator("admin", locale)
    return _(spec.label)


@router.callback_query(F.data == "a:limits")
async def limits_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    builder = InlineKeyboardBuilder()
    for key, spec in NUMERIC_SETTINGS.items():
        current = await repo.get_app_setting(key, str(spec.default))
        builder.row(
            InlineKeyboardButton(
                text=(
                    f"{_setting_label(spec, locale=i18n.locale)}: "
                    f"{_format_limit(key, current, locale=i18n.locale)} ▸"
                ),
                callback_data=f"a:limit:{key}",
            )
        )
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data="a:home"))
    await _redraw(
        callback,
        _("admin-limits-screen"),
        builder.as_markup(),
    )


@router.callback_query(F.data.startswith("a:limit:"))
async def limit_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    key = callback.data.rsplit(":", 1)[1]
    spec = NUMERIC_SETTINGS[key]
    current = await repo.get_app_setting(key, str(spec.default))
    _awaiting_input[callback.from_user.id] = (key, None)
    zero_hint = (
        f" (0 — {_format_limit(key, '0')}, locale=i18n.locale, locale=i18n.locale)"
        if spec.min == 0
        else ""
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data="a:limits"))
    await _redraw(
        callback,
        _(
            "admin-limit-prompt",
            label=_setting_label(spec, locale=i18n.locale),
            current=_format_limit(key, current, locale=i18n.locale),
            minimum=spec.min,
            maximum=spec.max,
            zero_hint=zero_hint,
        ),
        builder.as_markup(),
    )


@router.message(F.chat.type == ChatType.PRIVATE, F.text.regexp(r"^\d+([.,]\d+)?$"))
async def numeric_setting_input(
    message: Message,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_auth: PsnAuth,
    steam_auth: SteamAuth,
    bot: Bot,
    i18n: I18nContext,
) -> None:
    _ = translator("admin", i18n.locale)
    assert message.from_user is not None and message.text is not None
    pending = _awaiting_input.get(message.from_user.id)
    if pending is None:
        return  # a plain number from an admin who isn't in this flow — ignore
    key, chat_id = pending
    if key not in NUMERIC_SETTINGS and key not in _CHAT_SCOPED_KEYS:
        # An all-digit PSN Online ID landing here while _awaiting_psn_lookup
        # is pending, say (SPEC 9, M-PSN-1) — not this flow's business, its
        # own handler (below) owns whatever key it registered.
        return

    if key == "rare_threshold_percent":
        assert chat_id is not None  # only ever chat-scoped now (SPEC 5.5)
        value = float(message.text.replace(",", "."))
        if not (RARE_THRESHOLD_MIN <= value <= RARE_THRESHOLD_MAX):
            await message.answer(
                _(
                    "admin-number-range-retry",
                    minimum=RARE_THRESHOLD_MIN,
                    maximum=RARE_THRESHOLD_MAX,
                )
            )
            return
        del _awaiting_input[message.from_user.id]
        await repo.update_chat_settings(chat_id, rare_threshold_percent=value)
        reply_text, markup = await _chat(repo, chat_id, locale=i18n.locale)
        await message.answer(
            _("admin-threshold-saved", value=f"{value:g}", text=reply_text),
            reply_markup=markup,
        )
        return

    if key in ("flood_limit", "flood_window_minutes"):
        assert chat_id is not None  # chat-scoped, same as rare_threshold_percent above
        if "." in message.text or "," in message.text:
            await message.answer(_("admin-integer-retry"))
            return
        value_int = int(message.text)
        minimum, maximum = (
            (FLOOD_LIMIT_MIN, FLOOD_LIMIT_MAX)
            if key == "flood_limit"
            else (FLOOD_WINDOW_MIN, FLOOD_WINDOW_MAX)
        )
        if not (minimum <= value_int <= maximum):
            await message.answer(_("admin-number-range-retry", minimum=minimum, maximum=maximum))
            return
        del _awaiting_input[message.from_user.id]
        await repo.update_chat_settings(chat_id, **{key: value_int})
        reply_text, markup = await _chat(repo, chat_id, locale=i18n.locale)
        saved_key = "admin-flood-saved" if key == "flood_limit" else "admin-flood-window-saved"
        await message.answer(_(saved_key, value=value_int, text=reply_text), reply_markup=markup)
        return

    # The row-cap settings below are always global — chat_id is always None
    # here, there is no per-chat meaning for them.
    if "." in message.text or "," in message.text:
        await message.answer(_("admin-integer-retry"))
        return
    value_int = int(message.text)
    spec = NUMERIC_SETTINGS[key]
    if not (spec.min <= value_int <= spec.max):
        await message.answer(_("admin-number-range-retry", minimum=spec.min, maximum=spec.max))
        return
    stored = str(value_int)
    confirm = (
        f"{_setting_label(spec, locale=i18n.locale)}: "
        f"{_format_limit(key, stored, locale=i18n.locale)}"
    )

    del _awaiting_input[message.from_user.id]
    await repo.set_app_setting(key, stored, message.from_user.id)
    await _replace_admin_home(
        bot,
        repo,
        fetcher,
        steam_fetcher,
        psn_auth,
        steam_auth,
        message.from_user.id,
        prefix=confirm,
    )


# ------------------------------------------------------- per-chat settings

# Rare threshold, daily-summary time and its timezone are always explicit
# per chat (SPEC 5.5, 5.7) — no global screen any more, editing always
# happens from a chat's own card.


def _hour_grid_markup(
    current: str, set_prefix: str, tz_callback: str, back_callback: str, *, locale: str
) -> InlineKeyboardMarkup:
    _ = translator("admin", locale)
    builder = InlineKeyboardBuilder()
    for hour in range(24):
        label = f"{hour:02d}"
        mark = "• " if current.startswith(label) else ""
        builder.add(
            InlineKeyboardButton(text=f"{mark}{label}", callback_data=f"{set_prefix}{hour}")
        )
    builder.adjust(6)
    builder.row(InlineKeyboardButton(text=_("admin-timezone-button"), callback_data=tz_callback))
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data=back_callback))
    return builder.as_markup()


def _tz_grid_markup(
    current_minutes: int, set_prefix: str, manual_callback: str, back_callback: str, *, locale: str
) -> InlineKeyboardMarkup:
    _ = translator("admin", locale)
    builder = InlineKeyboardBuilder()
    for hours in COMMON_OFFSETS_HOURS:
        minutes = hours * 60
        mark = "• " if minutes == current_minutes else ""
        builder.add(
            InlineKeyboardButton(
                text=f"{mark}{format_offset(minutes)}", callback_data=f"{set_prefix}{minutes}"
            )
        )
    builder.adjust(4)
    builder.row(
        InlineKeyboardButton(text=_("admin-timezone-manual"), callback_data=manual_callback)
    )
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data=back_callback))
    return builder.as_markup()


@router.callback_query(F.data.startswith("a:crt:"))
async def chat_rare_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await _find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    _awaiting_input[callback.from_user.id] = ("rare_threshold_percent", chat_id)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data=f"a:chat:{chat_id}"))
    await _redraw(
        callback,
        _(
            "admin-chat-threshold-prompt",
            title=chat.title or chat_id,
            value=f"{chat.rare_threshold_percent:g}",
        ),
        builder.as_markup(),
    )


@router.callback_query(F.data.startswith("a:cfltoggle:"))
async def chat_flood_toggle(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    """On/off for the whole filter (2026-09-09 user request), next to the
    limit/window buttons below — same one-tap-toggle shape as the daily
    summary switch above. Off is flood_limit = 0 (the schema's own "off"
    convention); back on lands on FLOOD_LIMIT_DEFAULT rather than
    remembering whatever it was set to before — no column exists to
    remember that, and re-tuning it with the limit button right next to
    this one costs one more tap, not a real loss."""
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await _find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    new_limit = 0 if chat.flood_limit > 0 else FLOOD_LIMIT_DEFAULT
    await repo.update_chat_settings(chat_id, flood_limit=new_limit)
    await callback.answer()
    await _redraw(callback, *await _chat(repo, chat_id, locale=i18n.locale))


@router.callback_query(F.data.startswith("a:cfl:"))
async def chat_flood_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await _find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    _awaiting_input[callback.from_user.id] = ("flood_limit", chat_id)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data=f"a:chat:{chat_id}"))
    await _redraw(
        callback,
        _(
            "admin-chat-flood-prompt",
            title=chat.title or chat_id,
            value=chat.flood_limit,
            minimum=FLOOD_LIMIT_MIN,
            maximum=FLOOD_LIMIT_MAX,
        ),
        builder.as_markup(),
    )


@router.callback_query(F.data.startswith("a:cflw:"))
async def chat_flood_window_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await _find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    _awaiting_input[callback.from_user.id] = ("flood_window_minutes", chat_id)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data=f"a:chat:{chat_id}"))
    await _redraw(
        callback,
        _(
            "admin-chat-flood-window-prompt",
            title=chat.title or chat_id,
            value=chat.flood_window_minutes,
            minimum=FLOOD_WINDOW_MIN,
            maximum=FLOOD_WINDOW_MAX,
        ),
        builder.as_markup(),
    )


@router.callback_query(F.data.startswith("a:ctime:"))
async def chat_time_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await _find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    await _redraw(
        callback,
        _("admin-chat-time-prompt", title=chat.title or chat_id, time=chat.daily_summary_time),
        _hour_grid_markup(
            chat.daily_summary_time,
            f"a:ctimes:{chat_id}:",
            f"a:ctz:{chat_id}",
            f"a:chat:{chat_id}",
            locale=i18n.locale,
        ),
    )


@router.callback_query(F.data.startswith("a:ctimes:"))
async def chat_time_set(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    _, _, chat_id_raw, hour_raw = callback.data.split(":")
    chat_id, hour = int(chat_id_raw), int(hour_raw)
    await repo.update_chat_settings(chat_id, daily_summary_time=f"{hour:02d}:00")
    await callback.answer(_("admin-chat-time-saved", time=f"{hour:02d}:00"))
    await _redraw(callback, *await _chat(repo, chat_id, locale=i18n.locale))


@router.callback_query(F.data.startswith("a:ctz:"))
async def chat_zone_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await _find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    await _redraw(
        callback,
        _(
            "admin-chat-zone-prompt",
            title=chat.title or chat_id,
            offset=format_offset(chat.tz_offset_min),
        ),
        _tz_grid_markup(
            chat.tz_offset_min,
            f"a:ctzs:{chat_id}:",
            f"a:ctzm:{chat_id}",
            f"a:ctime:{chat_id}",
            locale=i18n.locale,
        ),
    )


@router.callback_query(F.data.startswith("a:ctzs:"))
async def chat_zone_set(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    _, _, chat_id_raw, minutes_raw = callback.data.split(":")
    chat_id, minutes = int(chat_id_raw), int(minutes_raw)
    await repo.update_chat_settings(chat_id, tz_offset_min=minutes)
    await callback.answer(format_offset(minutes))
    await _redraw(callback, *await _chat(repo, chat_id, locale=i18n.locale))


@router.callback_query(F.data.startswith("a:ctzm:"))
async def chat_zone_manual_prompt(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await _find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    _awaiting_input[callback.from_user.id] = ("tz_offset_min", chat_id)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data=f"a:ctz:{chat_id}"))
    await _redraw(
        callback,
        _(
            "admin-chat-zone-manual-prompt",
            title=chat.title or chat_id,
            offset=format_offset(chat.tz_offset_min),
        ),
        builder.as_markup(),
    )


@router.message(
    F.chat.type == ChatType.PRIVATE, F.text.regexp(r"(?i)^(?:utc)?\s*[+-]\d{1,2}(?::[0-5]\d)?$")
)
async def chat_timezone_input(message: Message, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert message.from_user is not None and message.text is not None
    pending = _awaiting_input.get(message.from_user.id)
    if pending is None or pending[0] != "tz_offset_min":
        return  # a stray signed number from an admin not in this flow — ignore
    _, chat_id = pending
    assert chat_id is not None

    minutes = parse_utc_offset(message.text)
    if minutes is None:  # out of −12..+14 range — the regex alone can't catch that
        await message.answer(_("admin-timezone-invalid"))
        return

    del _awaiting_input[message.from_user.id]
    await repo.update_chat_settings(chat_id, tz_offset_min=minutes)
    reply_text, markup = await _chat(repo, chat_id, locale=i18n.locale)
    await message.answer(
        _("admin-timezone-saved", offset=format_offset(minutes), text=reply_text),
        reply_markup=markup,
    )


# --------------------------------------------------------------------- users


@router.callback_query(F.data.startswith("a:users:"))
async def users_page(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    page = int(callback.data.rsplit(":", 1)[1])
    await _redraw(callback, *await _users(repo, page, locale=i18n.locale))


@router.callback_query(F.data.startswith("a:u:"))
async def user_card(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    tg_id = int(callback.data.rsplit(":", 1)[1])
    await _redraw(callback, *await _card(repo, tg_id, locale=i18n.locale))


@router.callback_query(F.data.startswith("a:excl:"))
async def user_exclude(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    _, _, raw_id, raw_flag = callback.data.split(":")
    tg_id, excluded = int(raw_id), raw_flag == "1"
    await repo.set_excluded(tg_id, excluded, callback.from_user.id)
    await callback.answer(_("admin-user-excluded") if excluded else _("admin-user-restored"))
    await _redraw(callback, *await _card(repo, tg_id, locale=i18n.locale))


_SYNC_NOT_CONNECTED_KEY = {
    "xbox": "admin-user-not-connected",
    "steam": "admin-steam-not-connected",
    "psn": "admin-psn-not-connected",
}


async def _sync_target(
    repo: Repo, platform: str, tg_id: int, *, locale: str
) -> tuple[str, str] | None:
    """(external_id, display_name) for user_refresh below, or None if this
    platform isn't connected for this person — Xbox resolves through
    `users`, Steam/PSN through `platform_links`, same split every other
    per-platform lookup in this file already has."""
    _ = translator("admin", locale)
    if platform == "xbox":
        user = await repo.get_user(tg_id)
        if user is None or not user.xuid:
            return None
        return user.xuid, user.gamertag or _("admin-default-player")
    link = await repo.get_platform_link(
        tg_id, Platform.STEAM if platform == "steam" else Platform.PSN
    )
    if link is None:
        return None
    return link.external_id, link.display_name or link.external_id


@router.callback_query(F.data.startswith("a:sync:"))
async def user_refresh(
    callback: CallbackQuery,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_fetcher: PsnFetcher,
    i18n: I18nContext,
) -> None:
    """The only place in the whole interface that may call the API on demand
    (SPEC 1.5) — one handler for all three platforms (2026-09-09 refactor,
    same shape reset_platform_confirm/_confirmed below already used):
    Fetcher/SteamFetcher/PsnFetcher all expose a compatible
    refresh_user(tg_id, external_id, name, locale) -> str."""
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    _, _prefix, platform, tg_id_s = callback.data.split(":")
    tg_id = int(tg_id_s)

    target = await _sync_target(repo, platform, tg_id, locale=i18n.locale)
    if target is None:
        await callback.answer(_(_SYNC_NOT_CONNECTED_KEY[platform]), show_alert=True)
        return
    external_id, name = target

    await callback.answer(_("admin-refreshing"))
    fetcher_by_platform: dict[str, Fetcher | SteamFetcher | PsnFetcher] = {
        "xbox": fetcher,
        "steam": steam_fetcher,
        "psn": psn_fetcher,
    }
    try:
        summary = await fetcher_by_platform[platform].refresh_user(
            tg_id, external_id, name, i18n.locale
        )
    except Exception:
        log.exception("admin %s refresh of tg_id=%s failed", platform, tg_id)
        await callback.answer(_("admin-refresh-failed"), show_alert=True)
        return
    text, markup = await _card(repo, tg_id, locale=i18n.locale)
    await _redraw(callback, f"{text}\n\n{summary}", markup)


# --------------------------------------------------------------------- chats


@router.callback_query(F.data == "a:chats")
async def chats_list(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    await _redraw(callback, *await _chats(repo, locale=i18n.locale))


@router.callback_query(F.data.startswith("a:chat:"))
async def chat_card(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    await _redraw(callback, *await _chat(repo, chat_id, locale=i18n.locale))


@router.callback_query(F.data.startswith("a:cds:"))
async def chat_daily(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await _find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    await repo.update_chat_settings(chat_id, daily_summary=0 if chat.daily_summary else 1)
    await callback.answer()
    await _redraw(callback, *await _chat(repo, chat_id, locale=i18n.locale))


@router.callback_query(F.data.startswith("a:coff:"))
async def chat_toggle_active(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await _find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    await repo.set_chat_active(chat_id, not chat.is_active)
    await callback.answer(_("admin-chat-disabled") if chat.is_active else _("admin-chat-enabled"))
    await _redraw(callback, *await _chat(repo, chat_id, locale=i18n.locale))


# Telegram caps an answerCallbackQuery's own text at 200 characters total
# (2026-09-09) — `bot_messages.preview` can itself be up to 200 chars, which
# would leave nothing for the "🗑 Удалено: «…»" wrapper around it and get
# silently cut off by Telegram mid-word. Trim further, specifically for the
# toast; the group-chat confirmation (chat.py's own /delete_last, a real
# message with no such cap) uses the stored preview untouched.
TOAST_PREVIEW_MAX_CHARS = 100


def _toast_preview(preview: str) -> str:
    collapsed = " ".join(preview.splitlines())
    if len(collapsed) <= TOAST_PREVIEW_MAX_CHARS:
        return collapsed
    return collapsed[: TOAST_PREVIEW_MAX_CHARS - 1] + "…"


@router.callback_query(F.data.startswith("a:cdellast:"))
async def chat_delete_last(
    callback: CallbackQuery, repo: Repo, bot: Bot, i18n: I18nContext
) -> None:
    """The admin panel's own way in to /delete_last's logic (chat.py) —
    found live: an admin looking to undo the bot's last message in a chat
    went looking for it here first, not the group chat itself. Same target
    (the last *non-system* message, 2026-09-05) and same "expected failure,
    forget the row either way" handling, just reached from the chat card
    instead of typed into the chat.

    The toast itself now names what got deleted (2026-09-09 user request,
    `bot_messages.preview`) instead of a bare "Удалил последнее сообщение."
    — the card underneath is redrawn unchanged, the preview lives only in
    the toast (user feedback: baking it into the card body reads as
    permanent clutter, the toast is the right place for something
    transient).
    """
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    target = await repo.last_non_system_bot_message(chat_id)
    if target is None:
        await callback.answer(_("admin-no-bot-messages"), show_alert=True)
        return
    try:
        await bot.delete_message(chat_id, target.message_id)
    except Exception:
        log.info("admin delete_last failed for chat %s message %s", chat_id, target.message_id)
        await repo.forget_bot_messages(chat_id, [target.message_id])
        await callback.answer(_("admin-delete-old-failed"), show_alert=True)
        return
    await repo.forget_bot_messages(chat_id, [target.message_id])
    feedback = (
        _("admin-deleted-last-preview", preview=_toast_preview(target.preview))
        if target.preview
        else _("admin-deleted-last")
    )
    await callback.answer(feedback)
    await _redraw(callback, *await _chat(repo, chat_id, locale=i18n.locale))


WIPE_WINDOW_HOURS = 24


@router.callback_query(F.data.startswith("a:cwipe:"))
async def chat_wipe_prompt(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await _find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    ids = await repo.bot_messages_since(chat_id, utcnow() - timedelta(hours=WIPE_WINDOW_HOURS))
    if not ids:
        await callback.answer(_("admin-no-bot-messages-24h"), show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=_("admin-confirm-delete"), callback_data=f"a:cwipey:{chat_id}")
    )
    builder.row(InlineKeyboardButton(text=_("admin-cancel"), callback_data=f"a:chat:{chat_id}"))
    await _redraw(
        callback,
        _(
            "admin-wipe-prompt",
            count=len(ids),
            title=chat.title or chat_id,
            hours=WIPE_WINDOW_HOURS,
        ),
        builder.as_markup(),
    )


async def _bulk_delete_messages(bot: Bot, chat_id: int, ids: list[int]) -> bool:
    """Deletes in chunks of 100 — the Bot API's own cap on deleteMessages —
    shared by the unconditional wipe and the "system only" pair below
    (2026-09-05 refactor: this loop was duplicated verbatim between them).
    Returns whether every chunk went through; a failed chunk is logged, not
    raised — same "expected failure" tolerance as everywhere else here."""
    ok = True
    for start in range(0, len(ids), 100):
        try:
            await bot.delete_messages(chat_id, ids[start : start + 100])
        except Exception:
            log.info("bulk delete failed for chat %s, chunk at %s", chat_id, start)
            ok = False
    return ok


async def _wipe_confirm(
    callback: CallbackQuery, repo: Repo, bot: Bot, chat_id: int, ids: list[int], *, locale: str
) -> None:
    """Shared tail of every wipe variant below: delete what the caller
    already decided on, forget the log rows either way (Telegram silently
    skips ids it can no longer delete — too old, already gone — and
    retrying those later would not help), report, redraw the chat card."""
    _ = translator("admin", locale)
    ok = await _bulk_delete_messages(bot, chat_id, ids)
    await repo.forget_bot_messages(chat_id, ids)
    await callback.answer(_("admin-wipe-done") if ok else _("admin-wipe-partial"))
    await _redraw(callback, *await _chat(repo, chat_id, locale=locale))


@router.callback_query(F.data.startswith("a:cwipey:"))
async def chat_wipe_confirm(
    callback: CallbackQuery, repo: Repo, bot: Bot, i18n: I18nContext
) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    ids = await repo.bot_messages_since(chat_id, utcnow() - timedelta(hours=WIPE_WINDOW_HOURS))
    await _wipe_confirm(callback, repo, bot, chat_id, ids, locale=i18n.locale)


# A narrower sibling of the unconditional wipe above (2026-09-05 follow-up,
# "system message" auto-delete): these two leave published achievements,
# stats and summaries untouched, so they're safe as a routine cleanup, not
# just a "just in case" tool — one bounded to 24h, one with no time limit
# at all for whenever that isn't enough.


async def _system_wipe_prompt(
    callback: CallbackQuery,
    repo: Repo,
    chat_id: int,
    ids: list[int],
    confirm_callback: str,
    *,
    locale: str,
) -> None:
    _ = translator("admin", locale)
    chat = await _find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    if not ids:
        await callback.answer(_("admin-no-system-messages"), show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=_("admin-confirm-delete"), callback_data=confirm_callback)
    )
    builder.row(InlineKeyboardButton(text=_("admin-cancel"), callback_data=f"a:chat:{chat_id}"))
    await _redraw(
        callback,
        _(
            "admin-system-wipe-prompt",
            count=len(ids),
            title=chat.title or chat_id,
        ),
        builder.as_markup(),
    )


@router.callback_query(F.data.startswith("a:cswipe:"))
async def chat_system_wipe_prompt(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    since = utcnow() - timedelta(hours=WIPE_WINDOW_HOURS)
    ids = await repo.system_bot_messages_since(chat_id, since)
    await _system_wipe_prompt(
        callback, repo, chat_id, ids, f"a:cswipey:{chat_id}", locale=i18n.locale
    )


@router.callback_query(F.data.startswith("a:cswipey:"))
async def chat_system_wipe_confirm(
    callback: CallbackQuery, repo: Repo, bot: Bot, i18n: I18nContext
) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    since = utcnow() - timedelta(hours=WIPE_WINDOW_HOURS)
    ids = await repo.system_bot_messages_since(chat_id, since)
    await _wipe_confirm(callback, repo, bot, chat_id, ids, locale=i18n.locale)


@router.callback_query(F.data.startswith("a:cswipeall:"))
async def chat_system_wipe_all_prompt(
    callback: CallbackQuery, repo: Repo, i18n: I18nContext
) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    ids = await repo.all_system_bot_messages(chat_id)
    await _system_wipe_prompt(
        callback, repo, chat_id, ids, f"a:cswipeally:{chat_id}", locale=i18n.locale
    )


@router.callback_query(F.data.startswith("a:cswipeally:"))
async def chat_system_wipe_all_confirm(
    callback: CallbackQuery, repo: Repo, bot: Bot, i18n: I18nContext
) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    ids = await repo.all_system_bot_messages(chat_id)
    await _wipe_confirm(callback, repo, bot, chat_id, ids, locale=i18n.locale)


# ------------------------------------------------------------------- screens


async def _new_user_defaults(repo: Repo, *, locale: str) -> tuple[str, InlineKeyboardMarkup]:
    """Settings that only ever apply at the moment someone new subscribes —
    grouped on their own screen (2026-09-05 follow-up) rather than sitting
    on the home screen forever, since none of them affect anyone already
    subscribed. Just default_rarity_mode for now (SPEC 9, M-Steam-2e's own
    Repo.subscribe reads it) — the natural home for anything else of the
    same shape added later."""
    _ = translator("admin", locale)
    default_rarity_mode = await repo.get_app_setting(
        DEFAULT_RARITY_MODE_KEY, DEFAULT_RARITY_MODE_DEFAULT
    )
    assert default_rarity_mode is not None  # a default was given above
    default_show_links = await repo.get_int_setting(
        DEFAULT_SHOW_LINKS_KEY, int(DEFAULT_SHOW_LINKS_DEFAULT)
    )

    text = _("admin-new-users-screen")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_(
                        "admin-default-rarity",
                        rarity=format_rarity(default_rarity_mode),
                    ),
                    callback_data="a:defaultrarity",
                )
            ],
            [
                InlineKeyboardButton(
                    text=_(
                        "admin-default-links",
                        visible=_("admin-yes") if default_show_links else _("admin-no"),
                    ),
                    callback_data="a:defaultlinks",
                )
            ],
            [InlineKeyboardButton(text=_("admin-back"), callback_data="a:home")],
        ]
    )
    return text, keyboard


async def _users(repo: Repo, page: int, *, locale: str) -> tuple[str, InlineKeyboardMarkup]:
    _ = translator("admin", locale)
    users = await repo.admin_users()
    if not users:
        return _("admin-users-empty"), _back_home(locale=locale)

    # By tg_id, not xuid (2026-09-05 follow-up) — the old xuid-keyed lookup
    # showed 0 for a Steam-only person's achievements, and only the Xbox
    # half of the count for someone with both platforms.
    today = await repo.achievement_counts_by_tg_id(today_cutoff_utc())
    # This aggregate spans every user, with no single person's timezone to
    # key the calendar-month boundary off (#14) — the project default
    # (Europe/Moscow, +180) is the reference, same as admin_view.py's own
    # "updated HH:MM".
    month = await repo.achievement_counts_by_tg_id(month_cutoff_utc(180))

    pages = max(1, -(-len(users) // PAGE_SIZE))
    page = max(0, min(page, pages - 1))
    chunk = users[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    lines = [_("admin-users-header", page=page + 1, pages=pages), ""]
    builder = InlineKeyboardBuilder()
    for user in chunk:
        name = (
            user.gamertag
            or user.steam_name
            or user.psn_online_id
            or _("admin-id", tg_id=user.tg_id)
        )
        lines.append(
            _(
                "admin-users-row",
                icon=_icon(user),
                name=truncate_name(name, 14),
                ago=humanize_ago(user.last_online_at, locale),
                today=today.get(user.tg_id, (0, 0))[0],
                month=month.get(user.tg_id, (0, 0))[0],
                note=_note(user, locale=locale),
            )
        )
        builder.row(
            InlineKeyboardButton(text=f"{_icon(user)} {name}", callback_data=f"a:u:{user.tg_id}")
        )

    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton(text="‹", callback_data=f"a:users:{page - 1}"))
    if page < pages - 1:
        navigation.append(InlineKeyboardButton(text="›", callback_data=f"a:users:{page + 1}"))
    if navigation:
        builder.row(*navigation)
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data="a:home"))

    lines += ["", _("admin-users-columns")]
    return "\n".join(lines), builder.as_markup()


def _admin_tg_header(user: User, *, locale: str) -> str:
    """Telegram identity, always shown in full (2026-09-08 user request) —
    unlike /stats' header (one best single name), the admin needs to see
    everything at once for lookups. The bare tg_id is never "@"-prefixed:
    it isn't a real, resolvable username, only a genuine `user.username` is
    (mentioning a nonexistent "@<number>" account risks nothing today, but
    a real account could later register that exact numeric string as its
    username and retroactively become a target of every old message that
    did this)."""
    _ = translator("admin", locale)
    bits = []
    full_name = " ".join(part for part in (user.first_name, user.last_name) if part)
    if full_name:
        bits.append(full_name)
    if user.username:
        bits.append(f"@{user.username}")
    bits.append(_("admin-user-tgid", tg_id=user.tg_id))
    return _("admin-user-header", identity=", ".join(bits))


async def _xbox_admin_block(repo: Repo, user: User, today_count: int, *, locale: str) -> list[str]:
    """One block, five fixed lines (2026-09-08 restructure, user request):
    nickname, id, status (+ when last checked), achievements, last online —
    each its own line instead of the old single achievements-and-all header
    line, so a long line no longer buries the id next to the nickname."""
    _ = translator("admin", locale)
    count = await repo.xbox_achievement_count(user.tg_id)
    completed = await repo.xbox_completed_games_count(user.xuid)
    parts = [plural_achievements(count, locale)]
    if completed:
        parts.append(f"{COMPLETED_BADGE} {completed}")
    parts.append(_("admin-today-tag", count=today_count))
    parts.append(_("admin-gamerscore-tag", score=user.gamerscore or 0))

    token = await repo.get_token(user.tg_id)
    presence = await repo.presence_of(user.xuid)
    login = _("admin-login-not-connected")
    if token is not None:
        login = {
            TokenStatus.ACTIVE: _(
                "admin-login-active", ago=humanize_ago(token.last_refresh_at, locale)
            ),
            TokenStatus.INVALID: _("admin-login-invalid"),
            TokenStatus.REVOKED: _("admin-login-revoked"),
        }.get(token.status, token.status)

    online = _("admin-no-data")
    if presence is not None:
        # Presence gives no name for PC titles, so fall back to the cache
        # the poller fills — an id in the card tells the admin nothing.
        game = presence.title_name or ""
        if not game and presence.title_id:
            game = await repo.title_name(presence.title_id) or presence.title_id
        game = game or _("admin-no-game")
        online = (
            _(
                "admin-online-playing",
                ago=humanize_ago(presence.updated_at, locale),
                game=game,
            )
            if presence.state == PresenceState.ONLINE
            else humanize_ago(presence.updated_at, locale)
        )
    return [
        _("admin-xbox-header", gamertag=user.gamertag or _("admin-no-name")),
        _("admin-xuid-tag", xuid=user.xuid),
        _("admin-login-row", login=login),
        "  ·  ".join(parts),
        _("admin-online-row", online=online),
    ]


async def _steam_admin_block(
    repo: Repo, link: PlatformLink, today_count: int, *, locale: str
) -> list[str]:
    """Steam's counterpart of `_xbox_admin_block` — same five-line shape,
    its "status" line is achievement *visibility* (there is no login/token
    to be active or dead), worded exactly like /panel's own status
    (`visibility_status_text`, shared so the two never drift)."""
    _ = translator("admin", locale)
    count = await repo.platform_achievement_count(link.tg_id, Platform.STEAM)
    completed = await repo.steam_completed_games_count(link.tg_id)
    parts = [plural_achievements(count, locale)]
    if completed:
        parts.append(f"{COMPLETED_BADGE} {completed}")
    parts.append(_("admin-today-tag", count=today_count))

    steam_presence = await repo.steam_presence_of(link.external_id)
    online = _("admin-no-data")
    if steam_presence is not None:
        game = steam_presence.game_name or (_("admin-no-game") if steam_presence.gameid else "")
        is_online = (steam_presence.persona_state or 0) != 0
        online = (
            _(
                "admin-online-playing",
                ago=humanize_ago(steam_presence.updated_at, locale),
                game=game,
            )
            if is_online and game
            else (
                _("admin-online-idle")
                if is_online
                else humanize_ago(steam_presence.updated_at, locale)
            )
        )
    return [
        _("admin-steam-header", name=link.display_name or _("admin-no-name")),
        _("admin-steamid-tag", external_id=link.external_id),
        _("admin-login-row", login=visibility_status_text(link, locale)),
        "  ·  ".join(parts),
        _("admin-online-row", online=online),
    ]


async def _psn_admin_block(
    repo: Repo, link: PlatformLink, today_count: int, *, locale: str
) -> list[str]:
    """PSN's counterpart — five lines now, same shape as Xbox/Steam
    (issue #1's presence poller, poller/psn_presence.py): trophy sync
    itself still has no presence hook at all (that's a separate, permanent
    design decision — see CLAUDE.md's PSN section), but /online's presence
    tracking is unrelated to it, so this block gets its "last online" line
    back same as the other two platforms."""
    _ = translator("admin", locale)
    count = await repo.platform_achievement_count(link.tg_id, Platform.PSN)
    platinum = await repo.psn_platinum_count(link.tg_id)
    parts = [plural_trophies(count, locale)]
    if platinum:
        parts.append(f"{COMPLETED_BADGE} {platinum}")
    parts.append(_("admin-today-tag", count=today_count))
    if link.psn_trophy_level is not None:
        parts.append(_("admin-psn-level-tag", level=link.psn_trophy_level))

    psn_presence = await repo.psn_presence_of(link.external_id)
    online = _("admin-no-data")
    if psn_presence is not None:
        game = psn_presence.title_name or (_("admin-no-game") if psn_presence.title_id else "")
        is_online = psn_presence.state == PresenceState.ONLINE
        online = (
            _(
                "admin-online-playing",
                ago=humanize_ago(psn_presence.updated_at, locale),
                game=game,
            )
            if is_online and game
            else (
                _("admin-online-idle")
                if is_online
                else humanize_ago(psn_presence.updated_at, locale)
            )
        )
    return [
        _("admin-psn-header", name=link.display_name or _("admin-no-name")),
        _("admin-psn-id-tag", external_id=link.external_id),
        _("admin-login-row", login=visibility_status_text(link, locale)),
        "  ·  ".join(parts),
        _("admin-online-row", online=online),
    ]


async def _card(repo: Repo, tg_id: int, *, locale: str) -> tuple[str, InlineKeyboardMarkup]:
    _ = translator("admin", locale)
    user = await repo.get_user(tg_id)
    steam_link = await repo.get_platform_link(tg_id, Platform.STEAM)
    psn_link = await repo.get_platform_link(tg_id, Platform.PSN)
    # Used to bail out on `not user.xuid` alone (2026-09-05 follow-up) — a
    # A Steam-only person got a "user not found" result in the admin panel,
    # same class of gap /stats had before it learned to work without Xbox.
    if user is None or (not user.xuid and steam_link is None and psn_link is None):
        return _("admin-user-not-found"), _back_home(locale=locale)

    today_xbox, today_steam, today_psn = await repo.achievement_platform_breakdown(
        tg_id, today_cutoff_utc()
    )
    chats = await repo.chats_of_user(tg_id)

    # Telegram identity first (2026-09-08 user request), then one block per
    # connected platform in a fixed order (Xbox → Steam → PSN) — each block
    # groups everything about that platform together (nickname/id, status,
    # achievements, last online where it applies), five fixed lines each
    # (2026-09-08 restructure) instead of one crowded header line.
    lines = [_admin_tg_header(user, locale=locale), ""]
    if user.xuid:
        lines += await _xbox_admin_block(repo, user, today_xbox, locale=locale)
        lines.append("")
    if steam_link is not None:
        lines += await _steam_admin_block(repo, steam_link, today_steam, locale=locale)
        lines.append("")
    if psn_link is not None:
        lines += await _psn_admin_block(repo, psn_link, today_psn, locale=locale)
        lines.append("")

    # The combined cross-platform counters line that used to follow here
    # was dropped (2026-09-08, user request) — each platform block above
    # already has its own achievements line, and a combined total added
    # nothing beyond that.
    lines += [
        _(
            "admin-subscribed",
            chats=", ".join(f"«{c}»" for c in chats) if chats else _("admin-nowhere"),
        ),
    ]
    text = "\n".join(lines)
    if user.is_excluded:
        text += "\n\n" + _("admin-excluded")

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=_("admin-restore") if user.is_excluded else _("admin-exclude"),
            callback_data=f"a:excl:{tg_id}:{0 if user.is_excluded else 1}",
        )
    )
    if user.xuid:
        builder.row(
            InlineKeyboardButton(
                text=_("admin-refresh-xbox"), callback_data=f"a:sync:xbox:{tg_id}"
            ),
            InlineKeyboardButton(text=_("admin-reset-xbox"), callback_data=f"a:reset:xbox:{tg_id}"),
        )
    if steam_link is not None:
        builder.row(
            InlineKeyboardButton(
                text=_("admin-refresh-steam"), callback_data=f"a:sync:steam:{tg_id}"
            ),
            InlineKeyboardButton(
                text=_("admin-reset-steam"), callback_data=f"a:reset:steam:{tg_id}"
            ),
        )
    if psn_link is not None:
        builder.row(
            InlineKeyboardButton(text=_("admin-refresh-psn"), callback_data=f"a:sync:psn:{tg_id}"),
            InlineKeyboardButton(text=_("admin-reset-psn"), callback_data=f"a:reset:psn:{tg_id}"),
        )
    builder.row(InlineKeyboardButton(text=_("admin-back-to-users"), callback_data="a:users:0"))
    return text, builder.as_markup()


# Plain platform names for the confirm prompt's own sentence — distinct
# from the "🔄 Обновить X" / "🗑 Сброс X" button labels, which read wrong
# spliced into "Стереть базу <label> для...".
_RESET_PLATFORM_NAMES = {"xbox": "XBOX", "steam": "Steam", "psn": "PSN"}


@router.callback_query(F.data.startswith("a:reset:"))
async def reset_platform_confirm(callback: CallbackQuery, i18n: I18nContext) -> None:
    """ "Сброс базы" is destructive and not undoable (user request 2026-09-08)
    — same one-tap-confirm shape as /disconnect_steam's own prompt, not an
    instant action behind a single tap."""
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    _, _prefix, platform, tg_id_s = callback.data.split(":")
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=_("admin-reset-confirm-yes"), callback_data=f"a:resetok:{platform}:{tg_id_s}"
        ),
        InlineKeyboardButton(text=_("admin-cancel"), callback_data=f"a:u:{tg_id_s}"),
    )
    await _redraw(
        callback,
        _("admin-reset-confirm-prompt", platform=_RESET_PLATFORM_NAMES[platform]),
        builder.as_markup(),
    )


@router.callback_query(F.data.startswith("a:resetok:"))
async def reset_platform_confirmed(
    callback: CallbackQuery,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_fetcher: PsnFetcher,
    i18n: I18nContext,
) -> None:
    _ = translator("admin", i18n.locale)
    assert callback.data is not None
    _, platform, tg_id_s = callback.data.split(":")
    tg_id = int(tg_id_s)
    await callback.answer(_("admin-refreshing"))

    try:
        if platform == "xbox":
            user = await repo.get_user(tg_id)
            assert user is not None and user.xuid is not None
            await repo.reset_xbox_data(tg_id, user.xuid)
            await fetcher.backfill(tg_id, user.xuid)
        elif platform == "steam":
            link = await repo.get_platform_link(tg_id, Platform.STEAM)
            assert link is not None
            await repo.reset_steam_data(tg_id)
            await steam_fetcher.backfill(tg_id, link.external_id)
        else:
            link = await repo.get_platform_link(tg_id, Platform.PSN)
            assert link is not None
            await repo.reset_psn_data(tg_id, link.external_id)
            await psn_fetcher.backfill(tg_id, link.external_id)
    except Exception:
        log.exception("admin reset+resync of tg_id=%s platform=%s failed", tg_id, platform)
        await callback.answer(_("admin-refresh-failed"), show_alert=True)

    text, markup = await _card(repo, tg_id, locale=i18n.locale)
    await _redraw(callback, text, markup)


async def _chats(repo: Repo, *, locale: str) -> tuple[str, InlineKeyboardMarkup]:
    _ = translator("admin", locale)
    chats = await repo.admin_chats()
    if not chats:
        return _("admin-chats-empty"), _back_home(locale=locale)

    builder = InlineKeyboardBuilder()
    for chat in chats:
        mark = "" if chat.is_active else "⏸ "
        builder.row(
            InlineKeyboardButton(
                text=_(
                    "admin-chat-list-row",
                    mark=mark,
                    title=chat.title or chat.chat_id,
                    subscribers=chat.subscribers,
                ),
                callback_data=f"a:chat:{chat.chat_id}",
            )
        )
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data="a:home"))
    return _("admin-chats-header"), builder.as_markup()


async def _chat(repo: Repo, chat_id: int, *, locale: str) -> tuple[str, InlineKeyboardMarkup]:
    _ = translator("admin", locale)
    chat = await _find_chat(repo, chat_id)
    if chat is None:
        return _("admin-chat-not-found-period"), _back_home(locale=locale)

    names = await repo.chat_subscriber_names(chat_id)
    threshold_label = f"{chat.rare_threshold_percent:g}%"
    zone_label = format_offset(chat.tz_offset_min)
    flood_label = (
        _("admin-chat-flood-value", limit=chat.flood_limit, window=chat.flood_window_minutes)
        if chat.flood_limit > 0
        else _("admin-chat-flood-off")
    )
    text = _(
        "admin-chat-card",
        title=chat.title or chat_id,
        state=_("admin-active") if chat.is_active else _("admin-inactive"),
        subscribers=chat.subscribers,
        threshold=threshold_label,
        summary=_("admin-yes") if chat.daily_summary else _("admin-no"),
        time=chat.daily_summary_time,
        offset=zone_label,
        min_score=chat.min_gamerscore,
        flood=flood_label,
        names=(
            _("admin-subscribers-list", names=", ".join(names))
            if names
            else _("admin-no-subscribers")
        ),
    )
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=_("admin-chat-threshold-button", threshold=threshold_label),
            callback_data=f"a:crt:{chat_id}",
        )
    )
    # Daily summary's own on/off + time/tz share one row (2026-09-09
    # button-layout consolidation, user request — fewer rows, same "type a
    # number to tune it, tap to toggle it" split every pair here already has).
    builder.row(
        InlineKeyboardButton(
            text=_(
                "admin-chat-summary-button",
                state=_("admin-enabled") if chat.daily_summary else _("admin-disabled-state"),
            ),
            callback_data=f"a:cds:{chat_id}",
        ),
        InlineKeyboardButton(
            text=_("admin-chat-time-button", time=chat.daily_summary_time, offset=zone_label),
            callback_data=f"a:ctime:{chat_id}",
        ),
    )
    # Same idea for the anti-flood filter: on/off + its two tunables, one row.
    builder.row(
        InlineKeyboardButton(
            text=_(
                "admin-chat-flood-toggle-button",
                state=_("admin-enabled") if chat.flood_limit > 0 else _("admin-disabled-state"),
            ),
            callback_data=f"a:cfltoggle:{chat_id}",
        ),
        InlineKeyboardButton(
            text=_("admin-chat-flood-button", limit=chat.flood_limit),
            callback_data=f"a:cfl:{chat_id}",
        ),
        InlineKeyboardButton(
            text=_("admin-chat-flood-window-button", window=chat.flood_window_minutes),
            callback_data=f"a:cflw:{chat_id}",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin-disable-chat") if chat.is_active else _("admin-enable-chat"),
            callback_data=f"a:coff:{chat_id}",
        )
    )
    # The four delete/wipe actions share one row and one icon (2026-09-09,
    # user request) — used to be four separate rows, and the first alone
    # had 🗑 while the other three had 🧹, an inconsistency nobody meant.
    builder.row(
        InlineKeyboardButton(text=_("admin-delete-last"), callback_data=f"a:cdellast:{chat_id}"),
        InlineKeyboardButton(text=_("admin-wipe-bot-24h"), callback_data=f"a:cwipe:{chat_id}"),
        InlineKeyboardButton(text=_("admin-wipe-system-24h"), callback_data=f"a:cswipe:{chat_id}"),
        InlineKeyboardButton(
            text=_("admin-wipe-system-all"), callback_data=f"a:cswipeall:{chat_id}"
        ),
    )
    builder.row(InlineKeyboardButton(text=_("admin-back-to-chats"), callback_data="a:chats"))
    return text, builder.as_markup()


# ------------------------------------------------------------------- helpers


async def _find_chat(repo: Repo, chat_id: int) -> ChatTarget | None:
    return next((c for c in await repo.admin_chats() if c.chat_id == chat_id), None)


def _back_home(*, locale: str) -> InlineKeyboardMarkup:
    _ = translator("admin", locale)
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=_("admin-back"), callback_data="a:home")]]
    )


def _icon(user: AdminUserRow) -> str:
    """Platform dots (2026-09-05 follow-up, extended for M-PSN-1) plus
    Xbox's own login-status icon — Steam and PSN have no per-person token
    to expire (one shared service credential each), so there's nothing
    analogous to add for either beyond the dot itself."""
    if user.is_excluded:
        return "🚫"
    parts = []
    if user.xuid:
        parts.append("🟢" + STATUS_ICON.get(user.token_status or "", "—"))
    if user.steam_id:
        parts.append("⚫")
    if user.psn_account_id:
        parts.append("🔵")
    return "".join(parts)


def _note(user: AdminUserRow, *, locale: str) -> str:
    _ = translator("admin", locale)
    if user.is_excluded:
        return _("admin-note-excluded")
    if user.token_status == TokenStatus.INVALID:
        return _("admin-note-invalid")
    if user.token_status == TokenStatus.REVOKED:
        return _("admin-note-revoked")
    return ""


async def _redraw(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    """One message that redraws itself, not a new one per press (SPEC 6)."""
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=markup)
        except Exception:
            # Telegram refuses an edit that changes nothing — harmless.
            pass
    await callback.answer()
