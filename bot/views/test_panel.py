"""Interactive test panel views (#10, #20, #126).

Renders screens for testing UX, submenus, toggle switches, navigation,
and showcases all bot screens in one place for admin review.
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
    hub_publishes: bool = True
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
    default_rarity: str = "all"
    default_links: bool = True  # Project-wide admin setting, default: True
    admin_chat_digest: int = 5


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
    # 0. Showcase Catalog (Витрина всех экранов)
    # =========================================================================
    if screen == "showcase":
        text = (
            "🧭 <b>Витрина экранов и интерактивного тестирования</b>\n\n"
            "Выберите экран для демонстрации и проверки отображения в Telegram:\n\n"
            "• 👤 <b>Панель игрока</b> — настройки аккаунтов, редкости, чатов\n"
            "• ⚙️ <b>Панель админа</b> — управление проектом, дайджестами и ссылками\n"
            "• 💬 <b>Хаб в чате</b> — меню управления и список игроков в группе\n"
            "• 📊 <b>Статистика</b> — карточка профиля игрока со всеми платформами\n"
            "• 📅 <b>Итоги дня</b> — дневное саммари с таблицей лидеров\n"
            "• 🗓️ <b>Итоги месяца</b> — календарный отчёт за месяц\n"
            "• 🏆 <b>Уведомление об ачивке</b> — одиночная карточка достижения\n"
            "• 📚 <b>Дайджест ачивок</b> — групповая карточка за игровую сессию\n"
            "• 🟢 <b>Кто в сети</b> — онлайн-таблица с текущими играми\n"
            "• ⏳ <b>Недавние</b> — лента последних полученных достижений"
        )
        builder.row(
            InlineKeyboardButton(text="👤 Панель игрока (/panel)", callback_data="tp:screen:panel"),
            InlineKeyboardButton(text="⚙️ Панель админа (/admin)", callback_data="tp:screen:admin"),
        )
        builder.row(
            InlineKeyboardButton(text="💬 Хаб в чате (Меню)", callback_data="tp:screen:chat_hub"),
            InlineKeyboardButton(text="📊 Статистика (/stats)", callback_data="tp:screen:stats"),
        )
        builder.row(
            InlineKeyboardButton(text="📅 Итоги дня (Саммари)", callback_data="tp:screen:sum_day"),
            InlineKeyboardButton(
                text="🗓️ Итоги месяца (Саммари)", callback_data="tp:screen:sum_month"
            ),
        )
        builder.row(
            InlineKeyboardButton(text="🏆 Уведомление об ачивке", callback_data="tp:screen:single"),
            InlineKeyboardButton(text="📚 Дайджест ачивок", callback_data="tp:screen:digest"),
        )
        builder.row(
            InlineKeyboardButton(text="🟢 Кто в сети (/online)", callback_data="tp:screen:online"),
            InlineKeyboardButton(text="⏳ Недавние (/recent)", callback_data="tp:screen:recent"),
        )
        builder.row(
            InlineKeyboardButton(text="🔄 Сбросить состояние заглушек", callback_data="tp:reset")
        )
        return text, builder.as_markup()

    # =========================================================================
    # 1. User Panel Home (/panel)
    # =========================================================================
    if screen == "home":
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
            InlineKeyboardButton(text="🧭 Каталог экранов", callback_data="tp:showcase"),
            InlineKeyboardButton(text="🔄 Сброс заглушек", callback_data="tp:reset"),
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
            InlineKeyboardButton(text="🧭 В каталог", callback_data="tp:showcase"),
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
            InlineKeyboardButton(text="🧭 В каталог", callback_data="tp:showcase"),
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
            InlineKeyboardButton(text="🧭 В каталог", callback_data="tp:showcase"),
        )
        return text, builder.as_markup()

    if screen == "psn_add":
        text = (
            "➕ <b>Подключение дополнительного аккаунта PSN (#10)</b>\n\n"
            "Лимит: до 3 аккаунтов на одного пользователя.\n"
            "В рабочем режиме бот запросит PSN Online ID или ссылку на профиль, "
            "проверит настройки видимости трофеев и подключит аккаунт.\n\n"
            "<i>(Нажмите кнопку ниже, чтобы симулировать добавление 3-го аккаунта)</i>"
        )
        builder.row(
            InlineKeyboardButton(
                text="✅ Симулировать подключение 'Hunter3'", callback_data="tp:do_psn_add"
            )
        )
        builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="tp:acc:psn"))
        return text, builder.as_markup()

    if screen == "unlink_confirm":
        plat = extra.get("platform", "psn")
        acc_id = extra.get("id", "0")
        name = "аккаунт"
        is_multi_psn = len(state.psn_accounts) > 1
        if plat == "psn":
            acc = next((a for a in state.psn_accounts if a["id"] == acc_id), None)
            if acc:
                idx = next((i for i, x in enumerate(state.psn_accounts, 1) if x["id"] == acc_id), 1)
                prefix = f"PSN{idx}" if is_multi_psn else "PSN"
                name = f"{prefix} '{acc['name']}'"
        elif plat == "xbox":
            name = "XBOX 'MajorNelson'"
        elif plat == "steam":
            name = "Steam 'Mad Omsk'"

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
            InlineKeyboardButton(text="🧭 В каталог", callback_data="tp:showcase"),
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
            InlineKeyboardButton(text="🧭 В каталог", callback_data="tp:showcase"),
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
            InlineKeyboardButton(text="🧭 В каталог", callback_data="tp:showcase"),
        )
        return text, builder.as_markup()

    # =========================================================================
    # 4. Admin Panel (/admin)
    # =========================================================================
    if screen == "admin":
        text = (
            "⚙️ Администрирование  ·  обновлено 14:00\n\n"
            "Пользователей: 4 (исключено: 0)\n"
            "  XBOX:  2 (вход активен: 1, без входа: 1)\n"
            "  PSN:   3\n"
            "  Steam: 2\n"
            "Чатов:          2\n"
            "API XBOX (достижения):  12/30 за 5 мин\n"
            "API Steam (достижения): нет данных\n"
            "Ключ PSN:   ✅ жив, проверен 4 мин назад\n"
            "Ключ Steam: ✅ жив, проверен 4 мин назад\n"
            "Запросов к PSN за сутки: 18"
        )
        builder.row(
            InlineKeyboardButton(
                text="👤 Новые пользователи ▸", callback_data="tp:adm_newusers"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="⚙️ Глобальные настройки ▸", callback_data="tp:adm_limits"
            )
        )
        builder.row(
            InlineKeyboardButton(text="Пользователи ▸", callback_data="tp:adm_usercard")
        )
        builder.row(
            InlineKeyboardButton(text="Чаты ▸", callback_data="tp:adm_chats")
        )
        builder.row(
            InlineKeyboardButton(text="🔑 Ключи платформ ▸", callback_data="tp:adm_keys")
        )
        builder.row(
            InlineKeyboardButton(text="🧭 В каталог экранов", callback_data="tp:showcase"),
            InlineKeyboardButton(text="🔄 Сброс настроек", callback_data="tp:reset"),
        )
        return text, builder.as_markup()

    if screen == "adm_newusers":
        text = (
            "👤 <b>Настройки новых пользователей</b>\n\n"
            "Эти настройки применяются только в момент, когда новый пользователь впервые "
            "подписывается на бота.\n\n"
            f"• Редкость по умолчанию: <b>{_rarity_title(state.default_rarity)}</b>\n"
            f"• Ссылки на профили для всех: <b>{'Да' if state.default_links else 'Нет'}</b>"
        )
        builder.row(
            InlineKeyboardButton(
                text=f"🎯 Редкость новичков: {_rarity_title(state.default_rarity)}",
                callback_data="tp:adm_cycle_rarity",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=f"🔗 Ссылки на профили: {'✅ Да' if state.default_links else '⚪ Нет'}",
                callback_data="tp:adm_toggle_links",
            )
        )
        builder.row(
            InlineKeyboardButton(text="◀️ Назад в админку", callback_data="tp:admin"),
            InlineKeyboardButton(text="🧭 В каталог", callback_data="tp:showcase"),
        )
        return text, builder.as_markup()

    if screen == "adm_limits":
        text = (
            "⚙️ <b>Глобальные настройки</b>\n\n"
            "Числовые лимиты и пороги группировки для всего бота.\n\n"
            f"• Порог дайджеста чата: <b>{state.admin_chat_digest}</b> ачивок"
        )
        builder.row(
            InlineKeyboardButton(
                text=f"📊 Порог дайджеста чата: {state.admin_chat_digest}",
                callback_data="tp:adm_digest",
            )
        )
        builder.row(
            InlineKeyboardButton(text="◀️ Назад в админку", callback_data="tp:admin"),
            InlineKeyboardButton(text="🧭 В каталог", callback_data="tp:showcase"),
        )
        return text, builder.as_markup()

    if screen == "adm_digest":
        text = (
            "📊 <b>Порог дайджеста чата (#126)</b>\n\n"
            "Если за одно сканирование получено несколько достижений:\n"
            "• от 2 до 20 — собирать в одну аккуратную карточку\n"
            "• 0 или Никогда — слать каждое отдельным сообщением"
        )
        choices = [2, 3, 5, 10, 20, 99]
        row_buttons = []
        for c in choices:
            label = "Никогда" if c >= 99 else str(c)
            mark = "• " if state.admin_chat_digest == c else ""
            row_buttons.append(
                InlineKeyboardButton(text=f"🔢 {mark}{label}", callback_data=f"tp:set_digest:{c}")
            )
            if len(row_buttons) == 3:
                builder.row(*row_buttons)
                row_buttons = []
        if row_buttons:
            builder.row(*row_buttons)
        builder.row(
            InlineKeyboardButton(text="◀️ Назад в настройки", callback_data="tp:adm_limits"),
            InlineKeyboardButton(text="🧭 В каталог", callback_data="tp:showcase"),
        )
        return text, builder.as_markup()

    if screen == "adm_usercard":
        is_multi_psn = len(state.psn_accounts) > 1
        psn_blocks = []
        for idx, a in enumerate(state.psn_accounts, 1):
            prefix = f"PSN{idx}" if is_multi_psn else "PSN"
            muted = "" if a["publishes"] else "\n   🔇 <i>Публикация отключена</i>"
            name = html_escape(a["name"])
            trophies = a["trophies"]
            plat = a["platinum"]
            psn_blocks.append(
                f"🔵 <b>PlayStation: {name}</b> ({prefix})\n"
                f"   psnid: 123456789012345678{a['id']}\n"
                "   Видимость: открытый профиль\n"
                f"   {trophies} трофеев  ·  {plat} 💠  ·  уровень {a['level']}\n"
                "   В сети: играет [<i>PS5</i>] — God of War Ragnarök"
                f"{muted}"
            )
        psn_text = "\n\n".join(psn_blocks)

        xb_muted = (
            "\n   🔇 <i>Публикация отключена</i>" if not state.xbox_publishes else ""
        )
        st_muted = (
            "\n   🔇 <i>Публикация отключена</i>" if not state.steam_publishes else ""
        )

        text = (
            "👤 <b>Пользователь: @GamerAdmin (Igor)</b>  [ID: 188022193]\n\n"
            "🟢 <b>XBOX: MajorNelson</b>\n"
            "   xuid: 2533274812345678\n"
            "   Вход: активен, проверен 4 мин назад\n"
            "   14 520 G  ·  325 достижений  ·  сегодня: 4\n"
            "   В сети: играет [<i>Xbox Series X</i>] — Halo Infinite"
            f"{xb_muted}\n\n"
            "⚫ <b>Steam: Gaben</b>\n"
            "   steamid: 76561198000000000\n"
            "   Видимость: открытый профиль\n"
            "   89 достижений  ·  сегодня: 1\n"
            "   В сети: играет — Half-Life 2"
            f"{st_muted}\n\n"
            f"{psn_text}\n\n"
            f"Язык: Русский  ·  Часовой пояс: {_format_offset(state.tz_offset_min)}  ·  "
            f"Редкость: {_rarity_title(state.rarity_mode)}"
        )
        builder.row(
            InlineKeyboardButton(text="◀️ Назад в админку", callback_data="tp:admin"),
            InlineKeyboardButton(text="🧭 В каталог", callback_data="tp:showcase"),
        )
        return text, builder.as_markup()

    if screen == "adm_chats":
        text = (
            "💬 <b>Чаты (2)</b>\n\n"
            "1. <b>Dev Igor and Igorr</b> (ID: -100123456789)\n"
            "   Участников: 3  ·  Дайджест: от 5  ·  Редкость: все\n\n"
            "2. <b>test chat</b> (ID: -100987654321)\n"
            "   Участников: 1  ·  Дайджест: от 3  ·  Редкость: все"
        )
        builder.row(
            InlineKeyboardButton(text="◀️ Назад в админку", callback_data="tp:admin"),
            InlineKeyboardButton(text="🧭 В каталог", callback_data="tp:showcase"),
        )
        return text, builder.as_markup()

    if screen == "adm_keys":
        text = (
            "🔑 <b>Ключи платформ</b>\n\n"
            "• Steam Web API: задан\n"
            "• PSN NPSSO: задан\n"
            "• Anthropic API: задан"
        )
        builder.row(
            InlineKeyboardButton(text="◀️ Назад в админку", callback_data="tp:admin"),
            InlineKeyboardButton(text="🧭 В каталог", callback_data="tp:showcase"),
        )
        return text, builder.as_markup()

    # =========================================================================
    # 5. Chat Hub (Хаб в чате)
    # =========================================================================
    if screen == "chat_hub":
        text = (
            "🎮 Слежу за достижениями и трофеями тех, кто играет на XBOX, "
            "PlayStation и в Steam, и публикую их сюда — с фильтром по редкости, "
            "статистикой каждого и итогом дня.\n\n"
            "Публикуются: @GamerAdmin, @PlayerTwo, @SnakeEater\n\n"
            "<i>Версия 1.5.0</i>"
        )
        builder.row(
            InlineKeyboardButton(
                text="🎮 Открыть приложение", callback_data="tp:noop:open_app"
            )
        )
        builder.row(
            InlineKeyboardButton(text="👤 Игрок", callback_data="tp:noop:hub_who"),
            InlineKeyboardButton(text="🟢 Онлайн", callback_data="tp:screen:online"),
            InlineKeyboardButton(text="🕘 Недавние", callback_data="tp:screen:recent"),
        )
        builder.row(
            InlineKeyboardButton(text="📅 Сводка дня", callback_data="tp:screen:sum_day"),
            InlineKeyboardButton(text="📆 Сводка месяца", callback_data="tp:screen:sum_month"),
        )
        hub_pub_label = (
            "🔕 Не публиковать сюда" if state.hub_publishes else "🔔 Публиковать сюда"
        )
        builder.row(
            InlineKeyboardButton(text=hub_pub_label, callback_data="tp:toggle_hub_pub"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="tp:screen:panel"),
        )
        builder.row(
            InlineKeyboardButton(text="🔗 XBOX", callback_data="tp:noop:connect_xbox"),
            InlineKeyboardButton(text="🎮 PSN", callback_data="tp:noop:connect_psn"),
            InlineKeyboardButton(text="🎮 Steam", callback_data="tp:noop:connect_steam"),
        )
        builder.row(InlineKeyboardButton(text="🧭 В каталог экранов", callback_data="tp:showcase"))
        return text, builder.as_markup()

    # =========================================================================
    # 6. Player Stats (/stats)
    # =========================================================================
    if screen == "stats":
        text = (
            "👤 <b>GamerAdmin</b>\n"
            "🟢 XBOX: MajorNelson  ·  14 520 G  ·  325 достижений  ·  12 🌀\n"
            "🔵 PlayStation: SuperOmsk  ·  120 трофеев  ·  5 💠  ·  уровень 45\n"
            "⚫️ Steam: Gaben  ·  89 достижений  ·  4 👾\n\n"
            "За сутки:  4 достижения (🟢 2 · ⚫ 1 · 🔵 1) [85 G · 1 💎 · 1 🏆]\n"
            "С 1 сентября:  28 достижений (🟢 15 · ⚫ 5 · 🔵 8) [640 G · 3 💎 · 1 🏆 2 🏆 5 🏆]\n\n"
            "<b>Игры с 1 сентября</b>\n"
            "• Halo Infinite (🟢 <i>XSX</i>) — 8 достижений [150 G · 1 💎]\n"
            "• God of War Ragnarök (🔵 <i>PS5</i>) — 6 трофеев [1 🏆 2 🏆 3 🏆]\n"
            "• Metal Gear Solid Delta (🔵 <i>PS5</i>) — 2 трофея [2 🏆]\n"
            "• Half-Life 2 (⚫) — 5 достижений\n"
            "• Elden Ring (🟢 <i>XSX</i>) — 7 достижений [120 G · 1 💎]"
        )
        builder.row(
            InlineKeyboardButton(
                text="🎮 Открыть приложение", callback_data="tp:noop:open_app"
            )
        )
        builder.row(
            InlineKeyboardButton(text="📅 Сводка дня", callback_data="tp:screen:sum_day"),
            InlineKeyboardButton(text="📆 Сводка месяца", callback_data="tp:screen:sum_month"),
        )
        builder.row(InlineKeyboardButton(text="🧭 В каталог экранов", callback_data="tp:showcase"))
        return text, builder.as_markup()

    # =========================================================================
    # 7. Summary: Day & Month
    # =========================================================================
    if screen == "summary_day":
        text = (
            "📅 <b>Итоги дня</b>\n\n"
            "Всего: 14 достижений (🟢 7 · ⚫ 2 · 🔵 5) [320 G · 2 💎 · 1 🏆 1 🏆 3 🏆]\n\n"
            "<b>Игроки:</b>\n"
            "1. GamerAdmin — 6 достижений (🟢 3 · ⚫ 0 · 🔵 3) [150 G · 1 💎 · 1 🏆 2 🏆]\n"
            "2. SnakeEater — 5 достижений (🟢 0 · ⚫ 0 · 🔵 5) [120 G · 3 🏆]\n"
            "3. Cortana — 3 достижения (🟢 3 · ⚫ 0 · 🔵 0) [50 G · 1 💎]\n"
            "4. Chief117 — 0 достижений (🟢 0 · ⚫ 0 · 🔵 0)\n\n"
            "<b>Игры:</b>\n"
            "• Halo Infinite (🟢 <i>XSX</i>) — 4 достижения [80 G]\n"
            "• God of War Ragnarök (🔵 <i>PS5</i>) — 5 трофеев [1 🏆 1 🏆 3 🏆]\n"
            "• Forza Horizon 5 (🟢 <i>XSX</i>) — 3 достижения [50 G · 1 💎]\n"
            "• Half-Life 2 (⚫) — 2 достижения"
        )
        builder.row(
            InlineKeyboardButton(text="◀️ 26 сен", callback_data="tp:noop:prev_day"),
            InlineKeyboardButton(text="🔘 27 сен (сегодня)", callback_data="tp:noop:cur_day"),
            InlineKeyboardButton(text="28 сен ▶️", callback_data="tp:noop:next_day"),
        )
        builder.row(
            InlineKeyboardButton(
                text="Показать всех (24ч)", callback_data="tp:noop:full_roster"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🎮 Открыть приложение", callback_data="tp:noop:open_app"
            )
        )
        builder.row(InlineKeyboardButton(text="🧭 В каталог экранов", callback_data="tp:showcase"))
        return text, builder.as_markup()

    if screen == "summary_month":
        text = (
            "🗓 <b>Итоги месяца</b>\n\n"
            "Всего: 184 достижения (🟢 96 · ⚫ 34 · 🔵 54) [4 120 G · 18 💎 · 3 🏆 8 🏆 15 🏆]\n\n"
            "<b>Игроки:</b>\n"
            "1. GamerAdmin — 86 достижений (🟢 48 · ⚫ 12 · 🔵 26) "
            "[1 840 G · 8 💎 · 2 🏆 4 🏆 6 🏆]\n"
            "2. Chief117 — 54 достижения (🟢 54 · ⚫ 0 · 🔵 0) [1 200 G · 5 💎]\n"
            "3. SnakeEater — 32 достижения (🟢 0 · ⚫ 0 · 🔵 32) [780 G · 1 🏆 3 🏆 8 🏆]\n"
            "4. Cortana — 12 достижений (🟢 12 · ⚫ 0 · 🔵 0) [300 G · 2 💎]\n\n"
            "<b>Игры:</b>\n"
            "• Halo Infinite (🟢 <i>XSX</i>) — 42 достижения [920 G · 4 💎]\n"
            "• God of War Ragnarök (🔵 <i>PS5</i>) — 36 трофеев [1 🏆 5 🏆 10 🏆]\n"
            "• Cyberpunk 2077 (⚫) — 28 достижений\n"
            "• Forza Horizon 5 (🟢 <i>XSX</i>) — 24 достижения [580 G · 3 💎]"
        )
        builder.row(
            InlineKeyboardButton(text="◀️ Август", callback_data="tp:noop:prev_month"),
            InlineKeyboardButton(text="🔘 Сентябрь 2026", callback_data="tp:noop:cur_month"),
            InlineKeyboardButton(text="Октябрь ▶️", callback_data="tp:noop:next_month"),
        )
        builder.row(
            InlineKeyboardButton(
                text="Показать всех (за месяц)", callback_data="tp:noop:full_month"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🎮 Открыть приложение", callback_data="tp:noop:open_app"
            )
        )
        builder.row(InlineKeyboardButton(text="🧭 В каталог экранов", callback_data="tp:showcase"))
        return text, builder.as_markup()

    # =========================================================================
    # 8. Single Achievement & Digest Cards
    # =========================================================================
    if screen == "single_achievement":
        text = (
            "<b>GamerAdmin</b> получает достижение\n\n"
            "Halo Infinite (<i>XBOX</i>) · 34/119\n"
            "💎 «Восхождение Спартанца» · 50 G · 3.4%\n\n"
            '<span class="tg-spoiler">Завершите все испытания кампании на Легендарной сложности '
            "без использования черепов-модификаторов.</span>"
        )
        builder.row(
            InlineKeyboardButton(
                text="🎮 Открыть приложение", callback_data="tp:noop:open_app"
            )
        )
        builder.row(InlineKeyboardButton(text="🧭 В каталог экранов", callback_data="tp:showcase"))
        return text, builder.as_markup()

    if screen == "digest_achievement":
        is_multi_psn = len(state.psn_accounts) > 1
        psn_prefix = "SuperOmsk (PSN1)" if is_multi_psn else "SuperOmsk"
        text = (
            "<b>GamerAdmin</b> получает 3 трофея\n\n"
            f"<b>{psn_prefix}</b>\n"
            "God of War Ragnarök (<i>PlayStation</i>) · 24/36\n"
            "🥉 «Холодный приём» · 42%\n"
            "<i>Победите первого босса в прологе.</i>\n"
            "🥈 «Охотник на валькирий» · 12.5%\n"
            "<i>Одолейте всех берсерков в девяти мирах.</i>\n"
            "🏆 «Чистильщик девяти миров» · 4.1%\n"
            "<i>Завершите все дополнительные активности во всех королевствах.</i>"
        )
        builder.row(
            InlineKeyboardButton(
                text="🎮 Открыть приложение", callback_data="tp:noop:open_app"
            )
        )
        builder.row(InlineKeyboardButton(text="🧭 В каталог экранов", callback_data="tp:showcase"))
        return text, builder.as_markup()

    # =========================================================================
    # 9. Online & Recent (/online, /recent)
    # =========================================================================
    if screen == "online":
        text = (
            "🎮 <b>Онлайн-статус игроков</b>\n"
            "<i>Обновлено: 13:45</i>\n\n"
            "🟢 MajorNelson — играет [<i>Xbox Series X</i>] — Halo Infinite\n"
            "🔵 SuperOmsk — играет [<i>PS5</i>] — God of War Ragnarök\n"
            "⚫ Gaben — в сети, не играет\n"
            "⚪ Chief117 — не в сети\n"
            "⚪ Cortana — не в сети"
        )
        builder.row(
            InlineKeyboardButton(
                text="🎮 Открыть приложение", callback_data="tp:noop:open_app"
            )
        )
        builder.row(
            InlineKeyboardButton(text="🔄 Обновить список", callback_data="tp:noop:refresh_online"),
            InlineKeyboardButton(text="👥 Все участники", callback_data="tp:noop:all_online"),
        )
        builder.row(InlineKeyboardButton(text="🧭 В каталог экранов", callback_data="tp:showcase"))
        return text, builder.as_markup()

    if screen == "recent":
        text = (
            "🕘 <b>Последние достижения</b>\n\n"
            "💎 GamerAdmin — (🟢 <i>XSX</i>) Halo Infinite · "
            "«Восхождение Спартанца» (+50 G · 3.4%) · 25 мин назад\n"
            "🏆 GamerAdmin — (🔵 <i>PS5</i>) God of War Ragnarök · "
            "«Чистильщик девяти миров» (4.1%) · 1 ч назад\n"
            "🥈 SnakeEater — (🔵 <i>PS5</i>) MGS Delta · «Тихий шаг» (18%) · 2 ч назад\n"
            "💎 Chief117 — (🟢 <i>XSX</i>) Halo: MCC · "
            "«Мастер Чиф на века» (+100 G · 1.2%) · 5 ч назад"
        )
        builder.row(
            InlineKeyboardButton(
                text="🎮 Открыть приложение", callback_data="tp:noop:open_app"
            )
        )
        builder.row(
            InlineKeyboardButton(text="🔄 Обновить ленту", callback_data="tp:noop:refresh_recent")
        )
        builder.row(InlineKeyboardButton(text="🧭 В каталог экранов", callback_data="tp:showcase"))
        return text, builder.as_markup()

    return "Неизвестный экран", builder.as_markup()
