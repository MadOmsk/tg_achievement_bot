"""The super-admin's settings screens, drawn from the registry (#176,
`services/admin_registry.py`) — the Mini App draws the same rows.

- **Global**: «⚙️ Настройки» lists the groups; a group lists its settings,
  each a button "Label: value ▸".
- **A chat**: the chat card's groups, each listing that chat's settings under
  the card's text.

A setting's button: on/off flips at once; a pick-one opens its choices; a
number asks to be typed (the handler keeps that state).
"""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.i18n import translator
from bot.services.admin_registry import (
    GROUPS,
    Kind,
    Scope,
    Setting,
    group_label,
    hint,
    label,
    settings_of,
    value_label,
)
from bot.views import Screen

# How many option buttons share a row, by kind.
_PER_ROW = {Kind.HOUR: 6, Kind.TZ: 4}


def _set_data(scope: Scope, key: str, chat_id: int | None) -> str:
    return f"a:s:{key}" if scope == "global" else f"a:cs:{chat_id}:{key}"


def _group_data(scope: Scope, group: str, chat_id: int | None) -> str:
    return f"a:sg:{group}" if scope == "global" else f"a:cg:{chat_id}:{group}"


def render_settings_home(*, locale: str) -> Screen:
    _ = translator("admin", locale)
    builder = InlineKeyboardBuilder()
    for group in GROUPS["global"]:
        builder.row(
            InlineKeyboardButton(
                text=f"{group_label('global', group, locale=locale)} ▸",
                callback_data=_group_data("global", group, None),
            )
        )
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data="a:home"))
    return Screen(_("admin-settings-title"), builder.as_markup())


def setting_rows(
    scope: Scope, group: str, current: dict[str, Any], *, locale: str, chat_id: int | None = None
) -> list[list[InlineKeyboardButton]]:
    """One button per setting of a group: "Label: value ▸"."""
    _ = translator("admin", locale)
    return [
        [
            InlineKeyboardButton(
                text=_(
                    "admin-settings-row",
                    label=label(setting, locale=locale),
                    value=value_label(setting, current[setting.key], locale=locale),
                ),
                callback_data=_set_data(scope, setting.key, chat_id),
            )
        ]
        for setting in settings_of(scope, group)
    ]


def render_settings_group(
    group: str, current: dict[str, Any], *, locale: str, prefix: str = ""
) -> Screen:
    _ = translator("admin", locale)
    rows = setting_rows("global", group, current, locale=locale)
    rows.append([InlineKeyboardButton(text=_("admin-back"), callback_data="a:set")])
    text = _("admin-settings-group-title", group=group_label("global", group, locale=locale))
    return Screen(
        f"{prefix}\n\n{text}" if prefix else text, InlineKeyboardMarkup(inline_keyboard=rows)
    )


def render_setting_choices(
    setting: Setting, current: Any, *, locale: str, back: str, chat_id: int | None = None
) -> Screen:
    """The values of a pick-one setting, the current one marked."""
    _ = translator("admin", locale)
    builder = InlineKeyboardBuilder()
    prefix = "a:sv" if setting.scope == "global" else f"a:csv:{chat_id}"
    for index, option in enumerate(setting.options()):
        mark = "• " if option == current else ""
        builder.add(
            InlineKeyboardButton(
                text=f"{mark}{value_label(setting, option, locale=locale)}",
                callback_data=f"{prefix}:{setting.key}:{index}",
            )
        )
    builder.adjust(_PER_ROW.get(setting.kind, 4))
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data=back))
    text = _("admin-settings-pick", label=label(setting, locale=locale))
    note = hint(setting, locale=locale)
    return Screen(f"{text}\n{note}" if note else text, builder.as_markup())


def render_setting_prompt(setting: Setting, current: Any, *, locale: str, back: str) -> Screen:
    """A number to type, its bounds and what a 0 means."""
    _ = translator("admin", locale)
    zero_hint = (
        _("admin-settings-zero-hint", meaning=_(setting.zero_label))
        if setting.zero_label and setting.min == 0
        else ""
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=_("admin-back"), callback_data=back))
    note = hint(setting, locale=locale)
    return Screen(
        _(
            "admin-settings-type",
            label=label(setting, locale=locale),
            current=value_label(setting, current, locale=locale),
            minimum=f"{setting.min:g}",
            maximum=f"{setting.max:g}",
            zero_hint=zero_hint,
        )
        + (f"\n{note}" if note else ""),
        builder.as_markup(),
    )


def back_to_group(setting: Setting, chat_id: int | None = None) -> str:
    return _group_data(setting.scope, setting.group, chat_id)
