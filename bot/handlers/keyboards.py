"""Inline keyboards shared by the connect flow and the panel — and, same as
format_offset/format_rarity below, small handler-side helpers with no other
natural home. safe_edit (2026-09-05 refactor) is one of those: imported by
panel.py, connect.py, steam.py and hltb.py alike, none of which import each
other back through this module, so it can live wherever without risking a
cycle — this file already sits underneath all of them.

Every function that renders user-facing text takes an I18nContext (SPEC
i18n migration, 2026-09-07) — strings live in
bot/locales/ru/LC_MESSAGES/keyboards.ftl, one file per shared-module the
same way hltb.py got its own.
"""

from __future__ import annotations

import contextlib

from aiogram import Bot
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram_i18n import I18nContext

from bot.constants import RarityMode
from bot.i18n import AVAILABLE_LOCALES, StaticI18nContext, gettext, static_i18n

# Re-exported (not redefined) — services/profile_links.py is the one place
# that builds these URLs (2026-09-06 follow-up: /stats' nickname links now
# need the exact same builders), this module just re-uses them for panel.py's
# own profile buttons below.
from bot.services.achievements import platform_label
from bot.services.profile_links import psn_profile_url, steam_profile_url, xbox_profile_url
from bot.services.relink import LinkPreview


async def safe_edit(
    callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None, **kwargs: object
) -> None:
    """Edit the callback's own message in place, tolerating the two routine
    failures every caller already needs to: the message isn't a real,
    editable Message (gone, or not accessible), or Telegram refuses an
    edit that changes nothing. Never calls callback.answer() itself —
    callers keep picking their own toast text, or none at all, same as
    before this existed."""
    if isinstance(callback.message, Message):
        with contextlib.suppress(Exception):
            await callback.message.edit_text(text, reply_markup=markup, **kwargs)


# Offsets, not zone names: MSK and CST are ambiguous, +03:00 is not (SPEC 6.1.1).
COMMON_OFFSETS_HOURS: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 9, 10)
ALL_OFFSETS_HOURS: tuple[int, ...] = tuple(range(-12, 15))

TZ_SET = "tz:set"
TZ_MORE = "tz:more"
TZ_SKIP = "tz:skip"
TZ_MANUAL = "tz:manual"


def _text(i18n: I18nContext | None, key: str, **kwargs: object) -> str:
    return i18n.get(key, **kwargs) if i18n is not None else gettext("keyboards", key, **kwargs)


def format_offset(minutes: int | None, i18n: I18nContext | None = None) -> str:
    if minutes is None:
        return _text(i18n, "kb-default")
    hours, rest = divmod(abs(minutes), 60)
    sign = "+" if minutes >= 0 else "−"
    return f"UTC{sign}{hours}" if rest == 0 else f"UTC{sign}{hours}:{rest:02d}"


def _offset_button(hours: int, i18n: I18nContext) -> InlineKeyboardButton:
    minutes = hours * 60
    return InlineKeyboardButton(
        text=format_offset(minutes, i18n), callback_data=f"{TZ_SET}:{minutes}"
    )


def timezone_keyboard(
    i18n: I18nContext, *, full: bool = False, skippable: bool = True
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    offsets = ALL_OFFSETS_HOURS if full else COMMON_OFFSETS_HOURS
    for hours in offsets:
        builder.add(_offset_button(hours, i18n))
    builder.adjust(4)

    if not full:
        builder.row(InlineKeyboardButton(text=i18n.get("kb-tz-other"), callback_data=TZ_MORE))
    # Faster than scrolling the full −12..+14 grid, and the only way to enter
    # a half-hour offset like +5:30 at all — the button grid only has whole
    # hours (SPEC 6.1.1).
    builder.row(InlineKeyboardButton(text=i18n.get("kb-tz-manual"), callback_data=TZ_MANUAL))
    if skippable:
        builder.row(InlineKeyboardButton(text=i18n.get("kb-tz-skip"), callback_data=TZ_SKIP))
    return builder.as_markup()


def connect_keyboard(url: str, i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=i18n.get("kb-connect-xbox"), url=url)]]
    )


# "Never digest" is stored as a number rather than NULL so the publisher stays
# a single comparison: any real session is smaller than this.
DIGEST_NEVER = 99
DIGEST_CHOICES = (2, 3, 4, 5, 6, 8, 10, DIGEST_NEVER)


def format_digest(threshold: int, i18n: I18nContext) -> str:
    if threshold >= DIGEST_NEVER:
        return i18n.get("kb-digest-never")
    return i18n.get("kb-digest-from-n", threshold=threshold)


# One mode governs every connected platform at once within a given chat
# (SPEC 9, M-Steam-2e and its follow-up — per chat now, not one shared
# value for all of them, panel.py's "Мои чаты" chat card) — show
# everything, show only the rare ones, or nothing. A click cycles to the
# next one rather than opening a submenu — one tap, not two, for a
# three-way toggle. Used to have a separate Xbox 360 show/hide switch next
# to this one; folded in here instead of growing a second platform-specific
# toggle when Steam arrived (services/achievements.py::passes_filters).
RARITY_CHOICES = (RarityMode.ALL, RarityMode.RARE, RarityMode.HIDDEN)


def format_rarity(mode: str, i18n: I18nContext | None = None) -> str:
    if mode == RarityMode.HIDDEN:
        return _text(i18n, "kb-rarity-hidden")
    if mode == RarityMode.RARE:
        # No percentage here on purpose: the threshold is per-chat now (SPEC
        # 5.5), and this panel is not chat-scoped — a single number here
        # would only ever be right for one of possibly several chats.
        return _text(i18n, "kb-rarity-rare")
    return _text(i18n, "kb-rarity-all")


#  Language names are endonyms, always written in their own language and
#  never translated (#48) — the whole point of a language picker is that
#  someone who cannot read the current interface can still find their own
#  language in it. Same reasoning as platform brand names, so these live
#  here rather than in a .ftl.
LOCALE_NAMES = {"ru": "Русский", "en": "English"}


def next_locale(current: str) -> str:
    """Cycles through the shipped locales, same shape as next_rarity_mode
    below. Two today, so this is a plain toggle; it stays correct as a cycle
    if a third ever lands, at which point the button should probably become
    a submenu instead."""
    order = list(AVAILABLE_LOCALES)
    index = order.index(current) if current in order else 0
    return order[(index + 1) % len(order)]


def locale_name(locale: str) -> str:
    return LOCALE_NAMES.get(locale, locale)


def next_rarity_mode(current: str) -> str:
    index = RARITY_CHOICES.index(current) if current in RARITY_CHOICES else 0
    return RARITY_CHOICES[(index + 1) % len(RARITY_CHOICES)]


def disconnect_prompt_keyboard(
    i18n: I18nContext, *, from_panel: bool = False
) -> InlineKeyboardMarkup:
    # Cancelling from the panel must restore the panel in place, not just
    # vanish — it needs its own callback so the handler knows to re-render
    # rather than delete the (only) message.
    cancel_data = "panel:disconnect:no" if from_panel else "disconnect:no"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("kb-disconnect-confirm"), callback_data="disconnect:yes"
                )
            ],
            [InlineKeyboardButton(text=i18n.get("kb-cancel"), callback_data=cancel_data)],
        ]
    )


def steam_disconnect_button(i18n: I18nContext) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=i18n.get("kb-steam-disconnect"), callback_data="steam:disconnectprompt"
    )


def psn_disconnect_button(i18n: I18nContext) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=i18n.get("kb-psn-disconnect"), callback_data="psn:disconnectprompt"
    )


def _platform_row(
    i18n: I18nContext | StaticI18nContext,
    *,
    connected: bool,
    connect_key: str,
    connect_cb: str,
    profile_url: str | None,
    disconnect_btn: InlineKeyboardButton,
) -> list[InlineKeyboardButton]:
    """One platform's row in /panel (#33) — always the same shape and
    position: `[👤 Профиль, 🔕 Отключить]` when connected (Профиль only once
    there is something to link to — the id can be missing pre-first-sync),
    or a single wide "🎮 Подключить X" when not."""
    if not connected:
        return [InlineKeyboardButton(text=i18n.get(connect_key), callback_data=connect_cb)]
    row: list[InlineKeyboardButton] = []
    if profile_url:
        row.append(InlineKeyboardButton(text=i18n.get("kb-profile"), url=profile_url))
    row.append(disconnect_btn)
    return row


def panel_keyboard(
    tz_offset_min: int | None,
    i18n: I18nContext | StaticI18nContext | None = None,
    *,
    connected: bool = True,
    needs_reconnect: bool = False,
    steam_connected: bool = False,
    psn_connected: bool = False,
    gamertag: str | None = None,
    steam_id: str | None = None,
    psn_id: str | None = None,
    show_profile_links: bool = False,
) -> InlineKeyboardMarkup:
    i18n = i18n or static_i18n("keyboards")

    # One row per platform, xbox -> steam -> psn, in the same shape and
    # position whether or not the person has that platform connected (#33) —
    # no more connect buttons at the top and profile/disconnect rows at the
    # bottom for the same platform.
    platform_rows = [
        _platform_row(
            i18n,
            connected=connected,
            connect_key="kb-panel-connect-xbox",
            connect_cb="relogin",
            profile_url=xbox_profile_url(gamertag) if gamertag else None,
            disconnect_btn=InlineKeyboardButton(
                text=i18n.get("kb-xbox-disconnect"), callback_data="panel:disconnect"
            ),
        ),
        _platform_row(
            i18n,
            connected=steam_connected,
            connect_key="kb-panel-connect-steam",
            connect_cb="steam:connect",
            profile_url=steam_profile_url(steam_id) if steam_id else None,
            disconnect_btn=steam_disconnect_button(i18n),
        ),
        _platform_row(
            i18n,
            connected=psn_connected,
            connect_key="kb-panel-connect-psn",
            connect_cb="psn:connect",
            profile_url=psn_profile_url(psn_id) if psn_id else None,
            disconnect_btn=psn_disconnect_button(i18n),
        ),
    ]

    # Every row below applies regardless of which platforms are connected —
    # timezone, chat list, sync, and the profile-links toggle are person-wide
    # settings, not Xbox-specific ones (2026-09-09, confirmed live: this used
    # to hard-gate the entire config section on `connected` — Xbox
    # specifically — so a Steam/PSN-only person saw nothing but the platform
    # rows at all, a leftover from before Steam/PSN existed). "Синхронизировать"
    # stays visible too: it is genuinely Xbox-only (panel_sync's own
    # implementation), but it already answers that gracefully with a toast
    # rather than crashing, the same way clicking "Профиль" for an
    # unconnected platform would.
    rows: list[list[InlineKeyboardButton]] = []
    if needs_reconnect:
        # A dead-login nudge — the account is still linked, its token just
        # went stale — distinct from the "🎮 Подключить" button.
        rows.append(
            [InlineKeyboardButton(text=i18n.get("kb-xbox-reconnect"), callback_data="relogin")]
        )
    rows += [
        [
            InlineKeyboardButton(
                text=i18n.get("kb-timezone-row", offset=format_offset(tz_offset_min, i18n)),
                callback_data="panel:tz",
            )
        ],
        [InlineKeyboardButton(text=i18n.get("kb-my-chats"), callback_data="panel:chatlist")],
        [InlineKeyboardButton(text=i18n.get("kb-sync"), callback_data="panel:sync")],
        # Off by default (Follow-up 2026-09-06) — gates the clickable link
        # /stats and /who put in this person's nickname; the panel's own
        # "👤 Профиль" buttons below stay visible regardless (this screen is
        # only ever shown to its owner).
        [
            InlineKeyboardButton(
                text=i18n.get(
                    "kb-profile-visible",
                    visible=i18n.get(
                        "kb-profile-visible-yes" if show_profile_links else "kb-profile-visible-no"
                    ),
                ),
                callback_data="panel:linkstoggle",
            )
        ],
        # Personal, and only ever applies to DMs — a group follows its own
        # chat_settings.locale, which no individual member can move (#48).
        [
            InlineKeyboardButton(
                text=i18n.get("kb-locale", name=locale_name(i18n.locale)),
                callback_data="panel:locale",
            )
        ],
    ]
    rows += platform_rows
    rows.append([InlineKeyboardButton(text=i18n.get("kb-refresh"), callback_data="panel:refresh")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def digest_keyboard(current: int, chat_id: int, i18n: I18nContext) -> InlineKeyboardMarkup:
    """Per chat now, not the main panel screen (Follow-up, 2026-09-05, same
    move as rarity_mode before it) — "Назад" goes back to that chat's own
    card, not the panel root."""
    builder = InlineKeyboardBuilder()
    for value in DIGEST_CHOICES:
        mark = "• " if value == current else ""
        label = i18n.get("kb-digest-never") if value >= DIGEST_NEVER else str(value)
        builder.add(
            InlineKeyboardButton(
                text=f"{mark}{label}", callback_data=f"panel:cdigestset:{chat_id}:{value}"
            )
        )
    builder.adjust(4)
    builder.row(
        InlineKeyboardButton(text=i18n.get("kb-back"), callback_data=f"panel:chat:{chat_id}")
    )
    return builder.as_markup()


def deep_link_keyboard(url: str, i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=i18n.get("kb-open"), url=url)]]
    )


def switch_keyboard(platform: str, i18n: I18nContext | StaticI18nContext) -> InlineKeyboardMarkup:
    """Yes/no for "you already have a different account linked" (#52).
    One shape for every platform: the question is the same everywhere, only
    the callback prefix differs."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("connect-switch-yes"),
                    callback_data=f"{platform}:switch:yes",
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("connect-switch-cancel"),
                    callback_data=f"{platform}:switch:no",
                )
            ],
        ]
    )


def switch_prompt(
    preview: LinkPreview,
    platform_name: str,
    incoming_name: str,
    i18n: I18nContext | StaticI18nContext,
) -> str:
    """What changes, in numbers, before anything changes (#52).

    The second paragraph only appears when the incoming account is already
    known — it is the difference between "this will take a while" and "this
    is instant", and staying quiet about it would make a cheap operation
    look expensive.
    """
    current = preview.current.display_name if preview.current else "—"
    text = i18n.get(
        "connect-switch-confirm",
        platform=platform_name,
        current=current,
        incoming=incoming_name,
        current_count=preview.current_achievements,
    )
    if preview.incoming_achievements:
        text += "\n\n" + i18n.get(
            "connect-switch-incoming-known",
            incoming=incoming_name,
            incoming_count=preview.incoming_achievements,
        )
    return text


async def notify_previous_owner(
    bot: Bot, tg_id: int, platform: str, name: str, *, locale: str
) -> None:
    """Tell whoever just lost an account that they lost it (#52, owner
    decision) — deliberately without naming who took it: that is somebody
    else's Telegram identity, and the person who lost the account can sort
    it out with the account itself, not with a name we volunteered.

    Best-effort: they may have blocked the bot, and a failed notice must not
    fail the linking that triggered it.
    """
    with contextlib.suppress(Exception):
        await bot.send_message(
            tg_id,
            gettext(
                "connect",
                "connect-account-taken",
                locale=locale,
                platform=platform_label(platform, locale),
                name=name,
            ),
        )
