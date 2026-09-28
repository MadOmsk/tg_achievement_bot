"""Interactive test panel views for user PM panel (#10, #20, #126, #141).

Renders the user PM panel and its submenus (accounts, chats, timezone)
for testing UX, submenus, toggle switches, and navigation during development.
Separated from handlers according to architectural rule #63.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape as html_escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


@dataclass
class MockPanelState:
    __test__ = False
    rarity_mode: str = "all"  # "all", "rare", "hidden"
    tz_offset_min: int = 120  # UTC+2
    show_secrets: bool = True
    xbox_publishes: bool = True
    steam_publishes: bool = True
    psn_accounts: list[dict] = field(
        default_factory=lambda: [
            {
                "id": "1",
                "name": "SuperOmsk",
                "publishes": True,
                "level": 6,
                "trophies": 19,
                "platinum": 1,
            },
            {
                "id": "2",
                "name": "Omsk2",
                "publishes": True,
                "level": 12,
                "trophies": 45,
                "platinum": 2,
            },
        ]
    )
    chats: list[dict] = field(
        default_factory=lambda: [
            {"id": 101, "title": "Dev Igor and Igorr", "subscribed": True, "digest": 5},
            {"id": 102, "title": "test chat", "subscribed": False, "digest": 3},
        ]
    )


def _rarity_title(mode: str) -> str:
    if mode == "rare":
        return "Редкие"
    if mode == "hidden":
        return "Никакие"
    return "Все"


def _format_offset(minutes: int) -> str:
    sign = "+" if minutes >= 0 else "−"
    abs_m = abs(minutes)
    h = abs_m // 60
    m = abs_m % 60
    return f"UTC{sign}{h}:{m:02d}" if m else f"UTC{sign}{h}"


def render_screen(
    screen: str, state: MockPanelState, extra: dict | None = None
) -> tuple[str, InlineKeyboardMarkup]:
    extra = extra or {}
    builder = InlineKeyboardBuilder()

    # =========================================================================
    # 1. User Panel Home (/panel)
    # =========================================================================
    if screen == "home" or screen == "panel":
        is_multi_psn = len(state.psn_accounts) > 1
        lines = [
            "👤 Igor",
            "🟢 XBOX: Mad Omsk  ·  7 478 достижений  ·  9 🌀  ·  152 604 G",
        ]
        if state.psn_accounts:
            total_trophies = sum(a["trophies"] for a in state.psn_accounts)
            total_plat = sum(a["platinum"] for a in state.psn_accounts)
            first_name = state.psn_accounts[0]["name"]
            extra_cnt = len(state.psn_accounts) - 1
            name_str = f"{first_name} (+{extra_cnt})" if is_multi_psn else first_name
            lvl = state.psn_accounts[0]["level"]
            lines.append(
                f"🔵 PlayStation: {name_str}  ·  {total_trophies} трофеев  ·  "
                f"{total_plat} 💠  ·  уровень {lvl}"
            )
        lines.append("⚫️ Steam: Mad Omsk  ·  1 747 достижений  ·  6 👾")
        lines.append("")
        lines.append("Вход XBOX:   ⚠️ требуется повторный вход")
        lines.append(
            "Вход Steam:  Mad Omsk  ·  "
            "⚠️ требуется изменить настройки приватности  ·  4 дн назад"
        )
        for idx, a in enumerate(state.psn_accounts, 1):
            prefix = f"PSN{idx}" if is_multi_psn else "PSN"
            name_esc = html_escape(a["name"])
            lines.append(f"Вход {prefix}:  {name_esc}  ·  ✅ ачивки видны  ·  4 дн назад")

        pub_chats = []
        for c in state.chats:
            icon = "✅" if c["subscribed"] else "🔇"
            pub_chats.append(f"{icon} «{html_escape(c['title'])}»")
        pub_str = ", ".join(pub_chats) if pub_chats else "— не подписан ни в одном чате"
        lines.append(f"Публикация:  {pub_str}")
        lines.append(f"Часовой пояс: {_format_offset(state.tz_offset_min)}")
        lines.append("")
        lines.append("⚠️ Доступ к XBOX истёк — необходимо выполнить повторный вход")
        lines.append(
            "⚠️ Ваши достижения Steam скрыты настройками приватности — "
            "необходимо изменить настройки приватности Steam"
        )

        text = "\n".join(lines)

        # Keyboard matching real panel_keyboard (#10, #20, #126)
        builder.row(
            InlineKeyboardButton(
                text=f"⏱ Часовой пояс: {_format_offset(state.tz_offset_min)} ▸",
                callback_data="tp:tz",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=f"💬 Мои чаты ({len(state.chats)}) ▸",
                callback_data="tp:chats",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=f"🎯 Публиковать достижения: {_rarity_title(state.rarity_mode)}",
                callback_data="tp:cycle_rarity",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🌐 Язык: Русский ▸",
                callback_data="tp:noop:locale",
            )
        )

        # Platforms in fixed order (Xbox -> PSN -> Steam)
        builder.row(
            InlineKeyboardButton(text="🟢 XBOX ▸", callback_data="tp:acc:xbox"),
            InlineKeyboardButton(
                text="🔔 Публикуется" if state.xbox_publishes else "🔇 Не публикуется",
                callback_data="tp:pub:xbox",
            ),
        )

        any_psn_pub = any(a["publishes"] for a in state.psn_accounts)
        all_psn_pub = (
            all(a["publishes"] for a in state.psn_accounts) if state.psn_accounts else False
        )
        if all_psn_pub:
            psn_pub_label = "🔔 Публикуется"
        elif any_psn_pub:
            psn_pub_label = "🔔 Частично"
        else:
            psn_pub_label = "🔇 Не публикуется"

        psn_count_label = (
            f"🔵 PSN ({len(state.psn_accounts)}) ▸" if is_multi_psn else "🔵 PSN ▸"
        )
        builder.row(
            InlineKeyboardButton(text=psn_count_label, callback_data="tp:acc:psn"),
            InlineKeyboardButton(text=psn_pub_label, callback_data="tp:pub:psn"),
        )

        builder.row(
            InlineKeyboardButton(text="⚫️ Steam ▸", callback_data="tp:acc:steam"),
            InlineKeyboardButton(
                text="🔔 Публикуется" if state.steam_publishes else "🔇 Не публикуется",
                callback_data="tp:pub:steam",
            ),
        )

        builder.row(
            InlineKeyboardButton(text="🗑 Удалить аккаунт", callback_data="tp:noop:del_acc")
        )
        builder.row(
            InlineKeyboardButton(text="🔄 Синхронизировать", callback_data="tp:noop:sync")
        )
        builder.row(
            InlineKeyboardButton(text="🔄 Сброс настроек", callback_data="tp:reset"),
        )
        return text, builder.as_markup()

    # =========================================================================
    # 2. Platform Submenus (PSN, Xbox, Steam)
    # =========================================================================
    if screen == "acc:psn":
        is_multi_psn = len(state.psn_accounts) > 1
        lines = [
            f"🎮 <b>PlayStation Network ({len(state.psn_accounts)} из 3 аккаунтов)</b>\n"
        ]
        for idx, a in enumerate(state.psn_accounts, 1):
            prefix = f"PSN{idx}" if is_multi_psn else "PSN"
            t_plat = a["platinum"]
            lines.append(
                f"<b>{prefix}: {html_escape(a['name'])}</b> · {a['level']} ур. · "
                f"{a['trophies']} 🏆 ({t_plat} 💠)"
            )
            lines.append("Видимость: открытый профиль")
            lines.append(
                f"Публикация: {'🔔 Публикуется' if a['publishes'] else '🔇 Заглушен'}\n"
            )

        for idx, a in enumerate(state.psn_accounts, 1):
            prefix = f"PSN{idx}" if is_multi_psn else "PSN"
            builder.row(
                InlineKeyboardButton(
                    text=f"👤 Профиль: {prefix} ({a['name']})", callback_data="tp:noop:profile"
                )
            )
            builder.row(
                InlineKeyboardButton(
                    text="🔔 Публикуется" if a["publishes"] else "🔇 Не публикуется",
                    callback_data=f"tp:toggle_psn_pub:{a['id']}",
                ),
                InlineKeyboardButton(
                    text=f"🔌 Отвязать {prefix}", callback_data=f"tp:unlink_confirm:psn:{a['id']}"
                ),
            )

        if len(state.psn_accounts) < 3:
            builder.row(
                InlineKeyboardButton(
                    text=f"➕ Добавить аккаунт ({len(state.psn_accounts) + 1}/3)",
                    callback_data="tp:psn_add",
                )
            )
        builder.row(
            InlineKeyboardButton(text="◀️ Назад в панель", callback_data="tp:home"),
        )
        return "\n".join(lines).strip(), builder.as_markup()

    if screen == "acc:xbox":
        text = (
            "🟢 <b>XBOX</b>\n\n"
            "MajorNelson  ·  152 604 G  ·  7 478 достижений  ·  9 🌀\n"
            "Вход: активен, проверен 4 мин назад\n"
            f"Публикация: {'🔔 Публикуется' if state.xbox_publishes else '🔇 Не публикуется'}"
        )
        builder.row(
            InlineKeyboardButton(text="👤 Профиль: MajorNelson", callback_data="tp:noop:profile")
        )
        builder.row(
            InlineKeyboardButton(
                text="🔔 Публикуется" if state.xbox_publishes else "🔇 Не публикуется",
                callback_data="tp:pub:xbox",
            )
        )
        builder.row(
            InlineKeyboardButton(text="🔌 Отвязать XBOX", callback_data="tp:unlink_confirm:xbox:0")
        )
        builder.row(
            InlineKeyboardButton(text="◀️ Назад в панель", callback_data="tp:home"),
        )
        return text, builder.as_markup()

    if screen == "acc:steam":
        text = (
            "⚫️ <b>Steam</b>\n\n"
            "Mad Omsk  ·  1 747 достижений  ·  6 👾\n"
            "Видимость: ⚠️ требуется изменить настройки приватности  ·  4 дн назад\n"
            f"Публикация: {'🔔 Публикуется' if state.steam_publishes else '🔇 Не публикуется'}"
        )
        builder.row(
            InlineKeyboardButton(text="👤 Профиль: Mad Omsk", callback_data="tp:noop:profile")
        )
        builder.row(
            InlineKeyboardButton(
                text="🔔 Публикуется" if state.steam_publishes else "🔇 Не публикуется",
                callback_data="tp:pub:steam",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🔌 Отвязать Steam", callback_data="tp:unlink_confirm:steam:0"
            )
        )
        builder.row(
            InlineKeyboardButton(text="◀️ Назад в панель", callback_data="tp:home"),
        )
        return text, builder.as_markup()

    if screen == "psn_add":
        text = (
            "➕ <b>Подключение дополнительного аккаунта PSN (#10)</b>\n\n"
            "Для подключения нового аккаунта отправьте ваш PSN Online ID или NPSSO токен.\n\n"
            "<i>(В тестовом режиме нажатие кнопки ниже добавит аккаунт-заглушку)</i>"
        )
        builder.row(
            InlineKeyboardButton(
                text="➕ Добавить аккаунт (демо)", callback_data="tp:do_psn_add"
            )
        )
        builder.row(InlineKeyboardButton(text="◀️ Назад к PSN", callback_data="tp:acc:psn"))
        return text, builder.as_markup()

    if screen == "unlink_confirm":
        plat = extra.get("platform", "xbox")
        acc_id = extra.get("acc_id", "0")
        name = "XBOX (MajorNelson)"
        if plat == "psn":
            found = next((a for a in state.psn_accounts if a["id"] == acc_id), None)
            name = f"PSN ({found['name']})" if found else "PSN"
        elif plat == "steam":
            name = "Steam (Mad Omsk)"

        text = (
            "🔌 <b>Отключение платформы</b>\n\n"
            f"Вы уверены, что хотите отключить {html_escape(name)}?\n"
            "<i>(В демо-режиме аккаунт будет просто убран из тестового списка)</i>"
        )
        back_cb = "tp:acc:psn" if plat == "psn" else f"tp:acc:{plat}"
        builder.row(
            InlineKeyboardButton(
                text="⚠️ Да, отключить", callback_data=f"tp:do_unlink:{plat}:{acc_id}"
            )
        )
        builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data=back_cb))
        return text, builder.as_markup()

    # =========================================================================
    # 3. Chats and Chat Detail
    # =========================================================================
    if screen == "chats":
        text = (
            "💬 <b>Мои чаты</b>\n\n"
            "Чаты, где бот состоит вместе с вами. Редкость публикаций теперь берётся "
            "из вашего профиля, а здесь переключается только факт публикации (#126)."
        )
        for c in state.chats:
            mark = "✅" if c["subscribed"] else "⚪"
            builder.row(
                InlineKeyboardButton(
                    text=f"{mark} {c['title']} ▸", callback_data=f"tp:chat:{c['id']}"
                )
            )
        builder.row(
            InlineKeyboardButton(text="◀️ Назад в панель", callback_data="tp:home"),
        )
        return text, builder.as_markup()

    if screen == "chat_detail":
        chat_id = extra.get("chat_id", 101)
        chat = next((c for c in state.chats if c["id"] == chat_id), None)
        if not chat and state.chats:
            chat = state.chats[0]
        if not chat:
            return "Чаты отсутствуют", builder.as_markup()

        pub_text = "✅ включена" if chat["subscribed"] else "⏸ выключена"
        text = (
            f"💬 <b>Чат: {html_escape(chat['title'])}</b>\n\n"
            f"Публикация: <b>{pub_text}</b>\n"
            f"Редкость: из вашего профиля (<b>{_rarity_title(state.rarity_mode)}</b>)\n"
            f"Порог дайджеста группы (#126): <b>{chat['digest']}</b> ачивок"
        )
        if chat["subscribed"]:
            builder.row(
                InlineKeyboardButton(
                    text="🔕 Отписаться", callback_data=f"tp:toggle_sub:{chat['id']}"
                )
            )
        else:
            builder.row(
                InlineKeyboardButton(
                    text="🔔 Подписаться", callback_data=f"tp:toggle_sub:{chat['id']}"
                )
            )
            builder.row(
                InlineKeyboardButton(
                    text="🗑️ Удалить из списка", callback_data=f"tp:del_chat_prompt:{chat['id']}"
                )
            )
        builder.row(
            InlineKeyboardButton(text="◀️ К списку чатов", callback_data="tp:chats"),
        )
        return text, builder.as_markup()

    if screen == "chat_del_confirm":
        chat_id = extra.get("chat_id", 101)
        chat = next((c for c in state.chats if c["id"] == chat_id), None)
        title = chat["title"] if chat else f"ID {chat_id}"
        text = (
            f"🗑️ <b>Удаление чата</b>\n\n"
            f"Убрать «{html_escape(title)}» из списка? "
            "Как будто вас там никогда не было — не бан, снова окажетесь в списке, "
            "если подпишетесь или напишете туда."
        )
        builder.row(
            InlineKeyboardButton(text="⚠️ Да, удалить", callback_data=f"tp:do_chat_del:{chat_id}")
        )
        builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data=f"tp:chat:{chat_id}"))
        return text, builder.as_markup()

    if screen == "tz":
        text = (
            "⏱ <b>Часовой пояс</b>\n\n"
            f"Текущее смещение: <b>{_format_offset(state.tz_offset_min)}</b>\n"
            "Используется для расчёта суточных окон и дайджестов."
        )
        offsets = [-480, -300, 0, 60, 120, 180, 240, 300, 360, 420, 480, 600]
        row_buttons = []
        for off in offsets:
            mark = "• " if state.tz_offset_min == off else ""
            row_buttons.append(
                InlineKeyboardButton(
                    text=f"🌐 {mark}{_format_offset(off)}", callback_data=f"tp:set_tz:{off}"
                )
            )
            if len(row_buttons) == 4:
                builder.row(*row_buttons)
                row_buttons = []
        if row_buttons:
            builder.row(*row_buttons)
        builder.row(
            InlineKeyboardButton(text="◀️ Назад в панель", callback_data="tp:home"),
        )
        return text, builder.as_markup()

    # Fallback to home
    return render_screen("home", state, extra)
