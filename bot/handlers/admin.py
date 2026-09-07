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
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import BaseFilter, Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
    TelegramObject,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import Settings
from bot.constants import Platform, PresenceState, RarityMode, SettingKey, TokenStatus
from bot.db.repo import AdminUserRow, ChatTarget, Repo
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
from bot.i18n import gettext
from bot.poller.daily import DEFAULT_TABLE_TOP, TOP_LIMIT_KEY
from bot.poller.fetcher import Fetcher
from bot.poller.message_cleanup import DEFAULT_TTL_MINUTES as DEFAULT_SYSTEM_MESSAGE_TTL_MIN
from bot.poller.message_cleanup import TTL_SETTING_KEY as SYSTEM_MESSAGE_TTL_KEY
from bot.poller.online_refresh import DEFAULT_REFRESH_INTERVAL_MIN as DEFAULT_ONLINE_REFRESH_MIN
from bot.poller.online_refresh import DEFAULT_TTL_HOURS as DEFAULT_ONLINE_REFRESH_TTL_HOURS
from bot.poller.online_refresh import REFRESH_INTERVAL_KEY as ONLINE_REFRESH_INTERVAL_KEY
from bot.poller.online_refresh import TTL_HOURS_KEY as ONLINE_REFRESH_TTL_KEY
from bot.poller.service_health import (
    DEFAULT_KEY_CHECK_INTERVAL_MIN,
    KEY_CHECK_INTERVAL_KEY,
)
from bot.poller.steam_fetcher import SteamFetcher
from bot.services.achievements import trophy_tier_badge
from bot.services.admin_view import render_admin_home
from bot.services.psn.auth import STATUS_NOT_CONFIGURED as PSN_NOT_CONFIGURED
from bot.services.psn.auth import PsnAuth
from bot.services.psn.client import (
    PsnApiError,
    PsnClientSetupError,
    PsnPrivateProfileError,
    PsnTokenDeadError,
    account_trophy_overview,
    recent_earned_trophies,
    resolve_profile,
)
from bot.services.psn.view import render_psn_trophy_table
from bot.services.stats import counters_for, month_cutoff_utc, today_cutoff_utc
from bot.services.tables import truncate_name
from bot.util import humanize_ago, parse_utc_offset, utcnow

log = logging.getLogger(__name__)

router = Router(name="admin")

_ = lambda key, **kwargs: gettext("admin", key, **kwargs)  # noqa: E731

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
    admin_id: int,
    prefix: str = "",
) -> None:
    """Sends a fresh /admin home screen as a brand-new message, replacing
    whatever this admin had open before, and (re)arms the auto-refresh job
    for it (Follow-up 2026-09-06) — shared by the bare /admin command and
    every flow that confirms a change and redraws home as a new message
    rather than editing the current one in place (a:home's own callback
    does the latter, so it never needs this)."""
    text, markup = await render_admin_home(repo, fetcher, steam_fetcher, psn_auth)
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
    bot: Bot,
) -> None:
    _awaiting_input.pop(message.from_user.id, None)  # a fresh /admin cancels any pending flow
    await _replace_admin_home(bot, repo, fetcher, steam_fetcher, psn_auth, message.chat.id)


@router.callback_query(F.data == "a:home")
async def admin_home(
    callback: CallbackQuery,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_auth: PsnAuth,
) -> None:
    _awaiting_input.pop(callback.from_user.id, None)
    await _redraw(callback, *await render_admin_home(repo, fetcher, steam_fetcher, psn_auth))


# ------------------------------------------------------------- PSN (test)

# A live, uncached lookup screen (SPEC 1.5's cache-only rule carve-out, same
# one the "Обновить данные" sync buttons already use) — for obtaining/testing
# the service NPSSO and eyeballing what a real trophy list looks like
# (name/tier/rarity/hidden/icon) before any of it is wired into /stats
# (SPEC 9, M-PSN-1). Registered before the free-text numeric/timezone
# handlers below on purpose: aiogram tries message handlers in registration
# order and stops at the first whose filter matches, so an admin's answer
# here (which can be almost any text, including a bare number if someone's
# PSN Online ID happens to be all digits) must be claimed by this filter
# before the generic ones get a chance at it.
PSN_NPSSO_KEY = "psn_npsso"
PSN_LOOKUP_KEY = "psn_trophy_lookup"


class AwaitingPsnAdminInput(BaseFilter):
    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        if user is None:
            return False
        pending = _awaiting_input.get(user.id)
        return pending is not None and pending[0] in (PSN_NPSSO_KEY, PSN_LOOKUP_KEY)


@router.callback_query(F.data == "a:psntest")
async def psn_test_menu(callback: CallbackQuery, psn_auth: PsnAuth) -> None:
    await _redraw(callback, *await _psn_test_screen(callback.from_user.id, psn_auth))


@router.callback_query(F.data == "a:psnnpsso")
async def psn_test_change_npsso(callback: CallbackQuery) -> None:
    """Re-enter the NPSSO even when PSN is already configured — for when it
    dies (SPEC 9, M-PSN-1's "мониторинг живости" paragraph) and the admin
    needs to paste a fresh one."""
    _awaiting_input[callback.from_user.id] = (PSN_NPSSO_KEY, None)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data="a:psntest"))
    await _redraw(
        callback,
        _("admin-psn-npsso-prompt"),
        builder.as_markup(),
    )


async def _psn_test_screen(admin_id: int, psn_auth: PsnAuth) -> tuple[str, InlineKeyboardMarkup]:
    builder = InlineKeyboardBuilder()
    if await psn_auth.status() == PSN_NOT_CONFIGURED:
        _awaiting_input[admin_id] = (PSN_NPSSO_KEY, None)
        builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data="a:home"))
        return (
            _("admin-psn-test-unconfigured"),
            builder.as_markup(),
        )
    _awaiting_input[admin_id] = (PSN_LOOKUP_KEY, None)
    builder.row(InlineKeyboardButton(text=_("admin-psn-change"), callback_data="a:psnnpsso"))
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data="a:home"))
    return (
        _("admin-psn-test-prompt"),
        builder.as_markup(),
    )


def _cancel_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("admin-cancel"), callback_data="a:psncancel")]
        ]
    )


@router.callback_query(F.data == "a:psncancel")
async def psn_admin_input_cancel(
    callback: CallbackQuery,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_auth: PsnAuth,
) -> None:
    """The way out of a still-armed NPSSO retry (Follow-up 2026-09-06,
    found live: a stray later message got misread as the next answer once
    nobody explicitly cancelled) — drops back to the admin home screen."""
    _awaiting_input.pop(callback.from_user.id, None)
    await _redraw(callback, *await render_admin_home(repo, fetcher, steam_fetcher, psn_auth))


@router.message(F.chat.type == ChatType.PRIVATE, AwaitingPsnAdminInput())
async def psn_admin_input(message: Message, psn_auth: PsnAuth, bot: Bot) -> None:
    assert message.from_user is not None and message.text is not None
    pending = _awaiting_input.get(message.from_user.id)
    assert pending is not None
    key = pending[0]
    raw = message.text.strip()

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
                reply_markup=_cancel_input_keyboard(),
            )
            return
        except PsnClientSetupError as exc:
            # Found live 2026-09-06: psnawp couldn't even construct its own
            # client (a sandboxed temp dir) and the admin got no reply at
            # all — this is deliberately a different message from the one
            # above, so a real bug doesn't get blamed on the NPSSO itself.
            log.exception("psn_admin_input: could not set up the PSN client")
            await message.answer(
                _("admin-psn-client-error", error=exc),
                reply_markup=_cancel_input_keyboard(),
            )
            return
        _awaiting_input[message.from_user.id] = (PSN_LOOKUP_KEY, None)
        await message.answer(_("admin-psn-configured-prompt"))
        return

    del _awaiting_input[message.from_user.id]
    try:
        client = await psn_auth.get_client()
        profile = await resolve_profile(client, raw)
        overview = await account_trophy_overview(client, profile.account_id)
        trophies = await recent_earned_trophies(client, profile.account_id, limit=10)
    except PsnTokenDeadError:
        await message.answer(_("admin-psn-token-dead"))
        return
    except PsnPrivateProfileError:
        await message.answer(_("admin-psn-private"))
        return
    except PsnApiError as exc:
        await message.answer(_("admin-psn-not-found", error=exc))
        return

    # Separate table (Follow-up 2026-09-06) — deliberately different from
    # the /stats game list: first validate its standalone presentation,
    # then decide whether it should be merged with the standard view.
    await message.answer(render_psn_trophy_table(overview), parse_mode=ParseMode.HTML)

    if not trophies:
        await message.answer(_("admin-psn-no-trophies", online_id=profile.online_id))
        return

    lines = [_("admin-psn-recent-header", online_id=profile.online_id, count=len(trophies))]
    for trophy in trophies:
        badge = trophy_tier_badge(trophy.trophy_type.value)
        rarity = (
            _("admin-psn-rarity", percent=f"{trophy.trophy_earn_rate:.1f}")
            if trophy.trophy_earn_rate is not None
            else ""
        )
        secret = _("admin-psn-hidden") if trophy.trophy_hidden else ""
        lines.append(
            _(
                "admin-psn-trophy-row",
                badge=badge,
                name=trophy.trophy_name,
                secret=secret,
                title=trophy.title_name,
                rarity=rarity,
            )
        )
        if trophy.trophy_detail:
            lines.append(_("admin-psn-detail", detail=trophy.trophy_detail))
    await message.answer("\n".join(lines))

    photos = [
        InputMediaPhoto(media=trophy.trophy_icon_url, caption=trophy.trophy_name[:200])
        for trophy in trophies
        if trophy.trophy_icon_url
    ][:10]
    if photos:
        with contextlib.suppress(Exception):
            await bot.send_media_group(message.chat.id, photos)


@router.callback_query(F.data == "a:newusers")
async def new_user_defaults_menu(callback: CallbackQuery, repo: Repo) -> None:
    await _redraw(callback, *await _new_user_defaults(repo))


@router.callback_query(F.data == "a:defaultrarity")
async def default_rarity_cycle(callback: CallbackQuery, repo: Repo) -> None:
    current = await repo.get_app_setting(DEFAULT_RARITY_MODE_KEY, DEFAULT_RARITY_MODE_DEFAULT)
    assert current is not None
    mode = next_rarity_mode(current)
    await repo.set_app_setting(DEFAULT_RARITY_MODE_KEY, mode, callback.from_user.id)
    await _redraw(callback, *await _new_user_defaults(repo))


@router.callback_query(F.data == "a:defaultlinks")
async def default_show_links_toggle(callback: CallbackQuery, repo: Repo) -> None:
    current = await repo.get_int_setting(DEFAULT_SHOW_LINKS_KEY, int(DEFAULT_SHOW_LINKS_DEFAULT))
    await repo.set_app_setting(
        DEFAULT_SHOW_LINKS_KEY, "0" if current else "1", callback.from_user.id
    )
    await _redraw(callback, *await _new_user_defaults(repo))


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

UNLIMITED_LABEL = _("admin-unlimited")

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


def _format_limit(key: str, value: str) -> str:
    spec = NUMERIC_SETTINGS[key]
    return _(spec.zero_label) if value == "0" else value


def _setting_label(spec: NumericSetting) -> str:
    return _(spec.label)


@router.callback_query(F.data == "a:limits")
async def limits_menu(callback: CallbackQuery, repo: Repo) -> None:
    builder = InlineKeyboardBuilder()
    for key, spec in NUMERIC_SETTINGS.items():
        current = await repo.get_app_setting(key, str(spec.default))
        builder.row(
            InlineKeyboardButton(
                text=f"{_setting_label(spec)}: {_format_limit(key, current)} ▸",
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
async def limit_menu(callback: CallbackQuery, repo: Repo) -> None:
    assert callback.data is not None
    key = callback.data.rsplit(":", 1)[1]
    spec = NUMERIC_SETTINGS[key]
    current = await repo.get_app_setting(key, str(spec.default))
    _awaiting_input[callback.from_user.id] = (key, None)
    zero_hint = f" (0 — {_format_limit(key, '0')})" if spec.min == 0 else ""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data="a:limits"))
    await _redraw(
        callback,
        _(
            "admin-limit-prompt",
            label=_setting_label(spec),
            current=_format_limit(key, current),
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
    bot: Bot,
) -> None:
    assert message.from_user is not None and message.text is not None
    pending = _awaiting_input.get(message.from_user.id)
    if pending is None:
        return  # a plain number from an admin who isn't in this flow — ignore
    key, chat_id = pending
    if key not in NUMERIC_SETTINGS and key != "rare_threshold_percent":
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
        reply_text, markup = await _chat(repo, chat_id)
        await message.answer(
            _("admin-threshold-saved", value=f"{value:g}", text=reply_text),
            reply_markup=markup,
        )
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
    confirm = f"{_setting_label(spec)}: {_format_limit(key, stored)}"

    del _awaiting_input[message.from_user.id]
    await repo.set_app_setting(key, stored, message.from_user.id)
    await _replace_admin_home(
        bot, repo, fetcher, steam_fetcher, psn_auth, message.from_user.id, prefix=confirm
    )


# ------------------------------------------------------- per-chat settings

# Rare threshold, daily-summary time and its timezone are always explicit
# per chat (SPEC 5.5, 5.7) — no global screen any more, editing always
# happens from a chat's own card.


def _hour_grid_markup(
    current: str, set_prefix: str, tz_callback: str, back_callback: str
) -> InlineKeyboardMarkup:
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
    current_minutes: int, set_prefix: str, manual_callback: str, back_callback: str
) -> InlineKeyboardMarkup:
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
async def chat_rare_menu(callback: CallbackQuery, repo: Repo) -> None:
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


@router.callback_query(F.data.startswith("a:ctime:"))
async def chat_time_menu(callback: CallbackQuery, repo: Repo) -> None:
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
            chat.daily_summary_time, f"a:ctimes:{chat_id}:", f"a:ctz:{chat_id}", f"a:chat:{chat_id}"
        ),
    )


@router.callback_query(F.data.startswith("a:ctimes:"))
async def chat_time_set(callback: CallbackQuery, repo: Repo) -> None:
    assert callback.data is not None
    _, _, chat_id_raw, hour_raw = callback.data.split(":")
    chat_id, hour = int(chat_id_raw), int(hour_raw)
    await repo.update_chat_settings(chat_id, daily_summary_time=f"{hour:02d}:00")
    await callback.answer(_("admin-chat-time-saved", time=f"{hour:02d}:00"))
    await _redraw(callback, *await _chat(repo, chat_id))


@router.callback_query(F.data.startswith("a:ctz:"))
async def chat_zone_menu(callback: CallbackQuery, repo: Repo) -> None:
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
            chat.tz_offset_min, f"a:ctzs:{chat_id}:", f"a:ctzm:{chat_id}", f"a:ctime:{chat_id}"
        ),
    )


@router.callback_query(F.data.startswith("a:ctzs:"))
async def chat_zone_set(callback: CallbackQuery, repo: Repo) -> None:
    assert callback.data is not None
    _, _, chat_id_raw, minutes_raw = callback.data.split(":")
    chat_id, minutes = int(chat_id_raw), int(minutes_raw)
    await repo.update_chat_settings(chat_id, tz_offset_min=minutes)
    await callback.answer(format_offset(minutes))
    await _redraw(callback, *await _chat(repo, chat_id))


@router.callback_query(F.data.startswith("a:ctzm:"))
async def chat_zone_manual_prompt(callback: CallbackQuery, repo: Repo) -> None:
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
async def chat_timezone_input(message: Message, repo: Repo) -> None:
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
    reply_text, markup = await _chat(repo, chat_id)
    await message.answer(
        _("admin-timezone-saved", offset=format_offset(minutes), text=reply_text),
        reply_markup=markup,
    )


# --------------------------------------------------------------------- users


@router.callback_query(F.data.startswith("a:users:"))
async def users_page(callback: CallbackQuery, repo: Repo) -> None:
    assert callback.data is not None
    page = int(callback.data.rsplit(":", 1)[1])
    await _redraw(callback, *await _users(repo, page))


@router.callback_query(F.data.startswith("a:u:"))
async def user_card(callback: CallbackQuery, repo: Repo) -> None:
    assert callback.data is not None
    tg_id = int(callback.data.rsplit(":", 1)[1])
    await _redraw(callback, *await _card(repo, tg_id))


@router.callback_query(F.data.startswith("a:excl:"))
async def user_exclude(callback: CallbackQuery, repo: Repo) -> None:
    assert callback.data is not None
    _, _, raw_id, raw_flag = callback.data.split(":")
    tg_id, excluded = int(raw_id), raw_flag == "1"
    await repo.set_excluded(tg_id, excluded, callback.from_user.id)
    await callback.answer(_("admin-user-excluded") if excluded else _("admin-user-restored"))
    await _redraw(callback, *await _card(repo, tg_id))


@router.callback_query(F.data.startswith("a:sync:"))
async def user_refresh(callback: CallbackQuery, repo: Repo, fetcher: Fetcher) -> None:
    """The only place in the whole interface that may call the API on demand
    (SPEC 1.5)."""
    assert callback.data is not None
    tg_id = int(callback.data.rsplit(":", 1)[1])
    user = await repo.get_user(tg_id)
    if user is None or not user.xuid:
        await callback.answer(_("admin-user-not-connected"), show_alert=True)
        return

    await callback.answer(_("admin-refreshing"))
    try:
        summary = await fetcher.refresh_user(
            tg_id, user.xuid, user.gamertag or _("admin-default-player")
        )
    except Exception:
        log.exception("admin refresh of tg_id=%s failed", tg_id)
        await callback.answer(_("admin-refresh-failed"), show_alert=True)
        return
    text, markup = await _card(repo, tg_id)
    await _redraw(callback, f"{text}\n\n{summary}", markup)


@router.callback_query(F.data.startswith("a:syncsteam:"))
async def user_refresh_steam(
    callback: CallbackQuery, repo: Repo, steam_fetcher: SteamFetcher
) -> None:
    """Steam's counterpart of user_refresh above (2026-09-05 follow-up) —
    the admin panel never had a way to poll one Steam account on demand."""
    assert callback.data is not None
    tg_id = int(callback.data.rsplit(":", 1)[1])
    link = await repo.get_platform_link(tg_id, Platform.STEAM)
    if link is None:
        await callback.answer(_("admin-steam-not-connected"), show_alert=True)
        return

    await callback.answer(_("admin-refreshing"))
    try:
        summary = await steam_fetcher.refresh_user(
            tg_id, link.external_id, link.display_name or link.external_id
        )
    except Exception:
        log.exception("admin steam refresh of tg_id=%s failed", tg_id)
        await callback.answer(_("admin-refresh-failed"), show_alert=True)
        return
    text, markup = await _card(repo, tg_id)
    await _redraw(callback, f"{text}\n\n{summary}", markup)


# --------------------------------------------------------------------- chats


@router.callback_query(F.data == "a:chats")
async def chats_list(callback: CallbackQuery, repo: Repo) -> None:
    await _redraw(callback, *await _chats(repo))


@router.callback_query(F.data.startswith("a:chat:"))
async def chat_card(callback: CallbackQuery, repo: Repo) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    await _redraw(callback, *await _chat(repo, chat_id))


@router.callback_query(F.data.startswith("a:cds:"))
async def chat_daily(callback: CallbackQuery, repo: Repo) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await _find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    await repo.update_chat_settings(chat_id, daily_summary=0 if chat.daily_summary else 1)
    await callback.answer()
    await _redraw(callback, *await _chat(repo, chat_id))


@router.callback_query(F.data.startswith("a:coff:"))
async def chat_toggle_active(callback: CallbackQuery, repo: Repo) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await _find_chat(repo, chat_id)
    if chat is None:
        await callback.answer(_("admin-chat-not-found"), show_alert=True)
        return
    await repo.set_chat_active(chat_id, not chat.is_active)
    await callback.answer(_("admin-chat-disabled") if chat.is_active else _("admin-chat-enabled"))
    await _redraw(callback, *await _chat(repo, chat_id))


@router.callback_query(F.data.startswith("a:cdellast:"))
async def chat_delete_last(callback: CallbackQuery, repo: Repo, bot: Bot) -> None:
    """The admin panel's own way in to /delete_last's logic (chat.py) —
    found live: an admin looking to undo the bot's last message in a chat
    went looking for it here first, not the group chat itself. Same target
    (the last *non-system* message, 2026-09-05) and same "expected failure,
    forget the row either way" handling, just reached from the chat card
    instead of typed into the chat."""
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    message_id = await repo.last_non_system_bot_message(chat_id)
    if message_id is None:
        await callback.answer(_("admin-no-bot-messages"), show_alert=True)
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        log.info("admin delete_last failed for chat %s message %s", chat_id, message_id)
        await repo.forget_bot_messages(chat_id, [message_id])
        await callback.answer(_("admin-delete-old-failed"), show_alert=True)
        return
    await repo.forget_bot_messages(chat_id, [message_id])
    await callback.answer(_("admin-deleted-last"))


WIPE_WINDOW_HOURS = 24


@router.callback_query(F.data.startswith("a:cwipe:"))
async def chat_wipe_prompt(callback: CallbackQuery, repo: Repo) -> None:
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
    callback: CallbackQuery, repo: Repo, bot: Bot, chat_id: int, ids: list[int]
) -> None:
    """Shared tail of every wipe variant below: delete what the caller
    already decided on, forget the log rows either way (Telegram silently
    skips ids it can no longer delete — too old, already gone — and
    retrying those later would not help), report, redraw the chat card."""
    ok = await _bulk_delete_messages(bot, chat_id, ids)
    await repo.forget_bot_messages(chat_id, ids)
    await callback.answer(_("admin-wipe-done") if ok else _("admin-wipe-partial"))
    await _redraw(callback, *await _chat(repo, chat_id))


@router.callback_query(F.data.startswith("a:cwipey:"))
async def chat_wipe_confirm(callback: CallbackQuery, repo: Repo, bot: Bot) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    ids = await repo.bot_messages_since(chat_id, utcnow() - timedelta(hours=WIPE_WINDOW_HOURS))
    await _wipe_confirm(callback, repo, bot, chat_id, ids)


# A narrower sibling of the unconditional wipe above (2026-09-05 follow-up,
# "system message" auto-delete): these two leave published achievements,
# stats and summaries untouched, so they're safe as a routine cleanup, not
# just a "just in case" tool — one bounded to 24h, one with no time limit
# at all for whenever that isn't enough.


async def _system_wipe_prompt(
    callback: CallbackQuery, repo: Repo, chat_id: int, ids: list[int], confirm_callback: str
) -> None:
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
async def chat_system_wipe_prompt(callback: CallbackQuery, repo: Repo) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    since = utcnow() - timedelta(hours=WIPE_WINDOW_HOURS)
    ids = await repo.system_bot_messages_since(chat_id, since)
    await _system_wipe_prompt(callback, repo, chat_id, ids, f"a:cswipey:{chat_id}")


@router.callback_query(F.data.startswith("a:cswipey:"))
async def chat_system_wipe_confirm(callback: CallbackQuery, repo: Repo, bot: Bot) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    since = utcnow() - timedelta(hours=WIPE_WINDOW_HOURS)
    ids = await repo.system_bot_messages_since(chat_id, since)
    await _wipe_confirm(callback, repo, bot, chat_id, ids)


@router.callback_query(F.data.startswith("a:cswipeall:"))
async def chat_system_wipe_all_prompt(callback: CallbackQuery, repo: Repo) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    ids = await repo.all_system_bot_messages(chat_id)
    await _system_wipe_prompt(callback, repo, chat_id, ids, f"a:cswipeally:{chat_id}")


@router.callback_query(F.data.startswith("a:cswipeally:"))
async def chat_system_wipe_all_confirm(callback: CallbackQuery, repo: Repo, bot: Bot) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    ids = await repo.all_system_bot_messages(chat_id)
    await _wipe_confirm(callback, repo, bot, chat_id, ids)


# ------------------------------------------------------------------- screens


async def _new_user_defaults(repo: Repo) -> tuple[str, InlineKeyboardMarkup]:
    """Settings that only ever apply at the moment someone new subscribes —
    grouped on their own screen (2026-09-05 follow-up) rather than sitting
    on the home screen forever, since none of them affect anyone already
    subscribed. Just default_rarity_mode for now (SPEC 9, M-Steam-2e's own
    Repo.subscribe reads it) — the natural home for anything else of the
    same shape added later."""
    default_rarity_mode = await repo.get_app_setting(
        DEFAULT_RARITY_MODE_KEY, DEFAULT_RARITY_MODE_DEFAULT
    )
    assert default_rarity_mode is not None  # a default was given above
    default_show_links = await repo.get_int_setting(
        DEFAULT_SHOW_LINKS_KEY, int(DEFAULT_SHOW_LINKS_DEFAULT)
    )

    text = (_("admin-new-users-screen"),)
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


async def _users(repo: Repo, page: int) -> tuple[str, InlineKeyboardMarkup]:
    users = await repo.admin_users()
    if not users:
        return _("admin-users-empty"), _back_home()

    # By tg_id, not xuid (2026-09-05 follow-up) — the old xuid-keyed lookup
    # showed 0 for a Steam-only person's achievements, and only the Xbox
    # half of the count for someone with both platforms.
    today = await repo.achievement_counts_by_tg_id(today_cutoff_utc())
    month = await repo.achievement_counts_by_tg_id(month_cutoff_utc())

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
                ago=humanize_ago(user.last_online_at),
                today=today.get(user.tg_id, (0, 0))[0],
                month=month.get(user.tg_id, (0, 0))[0],
                note=_note(user),
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


async def _card(repo: Repo, tg_id: int) -> tuple[str, InlineKeyboardMarkup]:
    user = await repo.get_user(tg_id)
    steam_link = await repo.get_platform_link(tg_id, Platform.STEAM)
    psn_link = await repo.get_platform_link(tg_id, Platform.PSN)
    # Used to bail out on `not user.xuid` alone (2026-09-05 follow-up) — a
    # A Steam-only person got a "user not found" result in the admin panel,
    # same class of gap /stats had before it learned to work without Xbox.
    if user is None or (not user.xuid and steam_link is None and psn_link is None):
        return _("admin-user-not-found"), _back_home()

    counters = await counters_for(repo, tg_id)
    chats = await repo.chats_of_user(tg_id)
    display_name = user.gamertag or (steam_link.display_name if steam_link else None)

    lines = [_("admin-user-header", name=display_name or _("admin-no-name")), ""]

    if user.xuid:
        token = await repo.get_token(tg_id)
        presence = await repo.presence_of(user.xuid)
        login = _("admin-login-not-connected")
        if token is not None:
            login = {
                TokenStatus.ACTIVE: _(
                    "admin-login-active", ago=humanize_ago(token.last_refresh_at)
                ),
                TokenStatus.INVALID: _("admin-login-invalid"),
                TokenStatus.REVOKED: _("admin-login-revoked"),
            }.get(token.status, token.status)

        online = _("admin-no-data")
        if presence is not None:
            # Presence gives no name for PC titles, so fall back to the
            # cache the poller fills — an id in the card tells the admin
            # nothing.
            game = presence.title_name or ""
            if not game and presence.title_id:
                game = await repo.title_name(presence.title_id) or presence.title_id
            game = game or _("admin-no-game")
            online = (
                _("admin-online-playing", ago=humanize_ago(presence.updated_at), game=game)
                if presence.state == PresenceState.ONLINE
                else humanize_ago(presence.updated_at)
            )
        lines += [
            _("admin-xbox-line", xuid=user.xuid, score=user.gamerscore or 0),
            _("admin-xbox-login", login=login),
            _("admin-xbox-online", online=online),
        ]

    if steam_link is not None:
        steam_presence = await repo.steam_presence_of(steam_link.external_id)
        steam_online = _("admin-no-data")
        if steam_presence is not None:
            game = steam_presence.game_name or (_("admin-no-game") if steam_presence.gameid else "")
            is_online = (steam_presence.persona_state or 0) != 0
            steam_online = (
                _("admin-online-playing", ago=humanize_ago(steam_presence.updated_at), game=game)
                if is_online and game
                else (
                    _("admin-online-idle") if is_online else humanize_ago(steam_presence.updated_at)
                )
            )
        lines += [
            _("admin-steam-line", external_id=steam_link.external_id),
            _("admin-display-name", name=steam_link.display_name),
            _("admin-steam-online", online=steam_online),
        ]

    if psn_link is not None:
        # No presence/sync yet — M-PSN-1 is link-only, polling is a later
        # step (SPEC 9, M-PSN-2+), so there's nothing to show beyond the
        # link itself.
        lines += [
            _("admin-psn-line", external_id=psn_link.external_id),
            _("admin-display-name", name=psn_link.display_name),
        ]

    lines += [
        "",
        _(
            "admin-subscribed",
            chats=", ".join(f"«{c}»" for c in chats) if chats else _("admin-nowhere"),
        ),
        # No lifetime total here: seen_achievements is permanently
        # best-effort (SPEC 5.4), unlike these two date-bounded counters.
        # Sums both platforms (counters_for, SPEC 9 M-Steam-2e).
        _("admin-counters", today=counters.today, month=counters.month),
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
            InlineKeyboardButton(text=_("admin-refresh-xbox"), callback_data=f"a:sync:{tg_id}")
        )
    if steam_link is not None:
        builder.row(
            InlineKeyboardButton(
                text=_("admin-refresh-steam"), callback_data=f"a:syncsteam:{tg_id}"
            )
        )
    builder.row(InlineKeyboardButton(text=_("admin-back-to-users"), callback_data="a:users:0"))
    return text, builder.as_markup()


async def _chats(repo: Repo) -> tuple[str, InlineKeyboardMarkup]:
    chats = await repo.admin_chats()
    if not chats:
        return _("admin-chats-empty"), _back_home()

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


async def _chat(repo: Repo, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    chat = await _find_chat(repo, chat_id)
    if chat is None:
        return _("admin-chat-not-found-period"), _back_home()

    names = await repo.chat_subscriber_names(chat_id)
    threshold_label = f"{chat.rare_threshold_percent:g}%"
    zone_label = format_offset(chat.tz_offset_min)
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
    builder.row(
        InlineKeyboardButton(
            text=_(
                "admin-chat-summary-button",
                state=_("admin-enabled") if chat.daily_summary else _("admin-disabled-state"),
            ),
            callback_data=f"a:cds:{chat_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin-chat-time-button", time=chat.daily_summary_time, offset=zone_label),
            callback_data=f"a:ctime:{chat_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin-disable-chat") if chat.is_active else _("admin-enable-chat"),
            callback_data=f"a:coff:{chat_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(text=_("admin-delete-last"), callback_data=f"a:cdellast:{chat_id}")
    )
    builder.row(
        InlineKeyboardButton(text=_("admin-wipe-bot-24h"), callback_data=f"a:cwipe:{chat_id}")
    )
    builder.row(
        InlineKeyboardButton(text=_("admin-wipe-system-24h"), callback_data=f"a:cswipe:{chat_id}")
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin-wipe-system-all"), callback_data=f"a:cswipeall:{chat_id}"
        )
    )
    builder.row(InlineKeyboardButton(text=_("admin-back-to-chats"), callback_data="a:chats"))
    return text, builder.as_markup()


# ------------------------------------------------------------------- helpers


async def _find_chat(repo: Repo, chat_id: int) -> ChatTarget | None:
    return next((c for c in await repo.admin_chats() if c.chat_id == chat_id), None)


def _back_home() -> InlineKeyboardMarkup:
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


def _note(user: AdminUserRow) -> str:
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
