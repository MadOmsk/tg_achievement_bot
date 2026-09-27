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
    tz_offset_min: int = 180  # UTC+3
    show_secrets: bool = True
    xbox_publishes: bool = True
    steam_publishes: bool = True
    hub_publishes: bool = True
    psn_accounts: list[dict] = field(
        default_factory=lambda: [
            {
                "id": "1",
                "name": "Kratos",
                "publishes": True,
                "level": 45,
                "trophies": 120,
                "platinum": 5,
            },
            {
                "id": "2",
                "name": "Snake",
                "publishes": False,
                "level": 28,
                "trophies": 64,
                "platinum": 1,
            },
        ]
    )
    chats: list[dict] = field(
        default_factory=lambda: [
            {"id": 101, "title": "Xbox Community", "subscribed": True, "digest": 5},
            {"id": 102, "title": "PlayStation Club", "subscribed": False, "digest": 3},
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
        psn_pub_text = []
        for idx, a in enumerate(state.psn_accounts, 1):
            prefix = f"PSN{idx}" if is_multi_psn else "PSN"
            st = "🔔 Публикуется" if a["publishes"] else "🔇 Не публикуется"
            psn_pub_text.append(f"• {prefix} ({html_escape(a['name'])}): {st}")
        psn_summary = "\n".join(psn_pub_text)

        rarity_val = _rarity_title(state.rarity_mode)
        secrets_val = "Показывать" if state.show_secrets else "Не показывать"

        text = (
            "👤 <b>Тестовая панель пользователя (/panel)</b>\n"
            "<i>Все кнопки и переходы интерактивны. Все действия выполняются заглушками "
            "без изменения рабочей базы данных.</i>\n\n"
            "<b>GamerAdmin</b>  ·  14 520 G  ·  325 ачивок  ·  184 🏆\n"
            "🎮 <b>XBOX:</b> MajorNelson · В сети (Halo Infinite)\n"
            "🎮 <b>Steam:</b> Gaben · В сети\n"
            f"🎮 <b>PSN:</b> {len(state.psn_accounts)} аккаунта(ов)\n\n"
            "<b>Публикация (#20):</b>\n"
            f"• XBOX: {'🔔 Публикуется' if state.xbox_publishes else '🔇 Не публикуется'}\n"
            f"• Steam: {'🔔 Публикуется' if state.steam_publishes else '🔇 Не публикуется'}\n"
            f"{psn_summary}\n\n"
            f"🎯 <b>Достижения (#126):</b> <b>{rarity_val}</b>\n"
            f"👁 <b>Секретные достижения:</b> <b>{secrets_val}</b>\n"
            f"⏱ <b>Часовой пояс:</b> {_format_offset(state.tz_offset_min)}"
        )

        # 1. Timezone
        builder.row(
            InlineKeyboardButton(
                text=f"⏱ Часовой пояс: {_format_offset(state.tz_offset_min)} ▸",
                callback_data="tp:tz",
            )
        )

        # 2. My chats
        builder.row(
            InlineKeyboardButton(
                text=f"💬 Мои чаты ({len(state.chats)}) ▸",
                callback_data="tp:chats",
            )
        )

        # 3. Rarity cyclic button
        builder.row(
            InlineKeyboardButton(
                text=f"🎯 Публиковать достижения: {rarity_val}",
                callback_data="tp:cycle_rarity",
            )
        )

        # 4. Secret achievements cyclic toggle
        builder.row(
            InlineKeyboardButton(
                text=f"👁 Секретные достижения: {secrets_val}",
                callback_data="tp:cycle_secrets",
            )
        )

        # 5. Platforms (old main screen order: Xbox -> PSN -> Steam)
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
            f"🔵 PSN ({len(state.psn_accounts)}) ▸" if len(state.psn_accounts) > 1 else "🔵 PSN ▸"
        )
        builder.row(
            InlineKeyboardButton(text=psn_count_label, callback_data="tp:acc:psn"),
            InlineKeyboardButton(text=psn_pub_label, callback_data="tp:pub:psn"),
        )

        builder.row(
            InlineKeyboardButton(text="⚪ Steam ▸", callback_data="tp:acc:steam"),
            InlineKeyboardButton(
                text="🔔 Публикуется" if state.steam_publishes else "🔇 Не публикуется",
                callback_data="tp:pub:steam",
            ),
        )

        # 6. Actions
        builder.row(InlineKeyboardButton(text="🔄 Синхронизировать", callback_data="tp:noop:sync"))
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
            f"🎮 <b>PlayStation Network ({len(state.psn_accounts)} из 3 аккаунтов) (#10)</b>",
            "<i>Управление несколькими аккаунтами PSN для одного человека.</i>\n",
        ]
        for idx, a in enumerate(state.psn_accounts, 1):
            prefix = f"PSN{idx}" if is_multi_psn else "PSN"
            lines.append(
                f"<b>{prefix}: {html_escape(a['name'])}</b> · {a['level']} ур. · {a['trophies']} 🏆"
            )
            lines.append("Статус: Открытый профиль")
            lines.append(
                f"Публикация: {'🔔 Публикуется' if a['publishes'] else '🔇 Заглушен (#20)'}\n"
            )

        if is_multi_psn:
            lines.append(
                "<i>Статистика в профиле суммируется, "
                "а одинаковые трофеи в каталоге игр дедуплицируются.</i>"
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
        return "\n".join(lines), builder.as_markup()

    if screen == "acc:xbox":
        text = (
            "🎮 <b>XBOX</b>\n\n"
            "MajorNelson  ·  14 520 G  ·  325 ачивок\n"
            "Вход: активен\n"
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
            "🎮 <b>Steam</b>\n\n"
            "Gaben  ·  89 ачивок  ·  4 🏆\n"
            "Видимость: Открытый профиль\n"
            f"Публикация: {'🔔 Публикуется' if state.steam_publishes else '🔇 Не публикуется'}"
        )
        builder.row(InlineKeyboardButton(text="👤 Профиль: Gaben", callback_data="tp:noop:profile"))
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
            name = "Steam 'Gaben'"

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
        builder.row(InlineKeyboardButton(text="◀️ К списку чатов", callback_data="tp:chats"))
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
            "⚙️ <b>Панель администратора (/admin)</b>\n\n"
            "1. <b>Новые пользователи (#126):</b>\n"
            f"• Редкость по умолчанию: <b>{_rarity_title(state.default_rarity)}</b>\n\n"
            "2. <b>Глобальные настройки проекта:</b>\n"
            f"• Ссылки на профили для всех: <b>{'Да' if state.default_links else 'Нет'}</b>\n\n"
            "3. <b>Настройки групп (#126):</b>\n"
            f"• Порог группировки в дайджест: <b>{state.admin_chat_digest} ачивок</b>\n\n"
            "4. <b>Мульти-аккаунты (#10, #20):</b>\n"
            "• В карточках пользователей отображаются все привязанные аккаунты PSN (1..3) "
            "и метка 🔇 Заглушен, если юзер отключил публикации."
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
            InlineKeyboardButton(
                text=f"📊 Порог дайджеста чата: {state.admin_chat_digest}",
                callback_data="tp:adm_digest",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="👤 Тестовая карточка юзера в админке",
                callback_data="tp:adm_usercard",
            )
        )
        builder.row(
            InlineKeyboardButton(text="🧭 В каталог экранов", callback_data="tp:showcase"),
            InlineKeyboardButton(text="🔄 Сброс настроек", callback_data="tp:reset"),
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
        builder.row(InlineKeyboardButton(text="◀️ Назад в админку", callback_data="tp:admin"))
        return text, builder.as_markup()

    if screen == "adm_usercard":
        is_multi_psn = len(state.psn_accounts) > 1
        psn_blocks = []
        for idx, a in enumerate(state.psn_accounts, 1):
            prefix = f"PSN{idx}" if is_multi_psn else "PSN"
            muted = "" if a["publishes"] else "\n   🔇 <i>Публикация выключена (#20)</i>"
            name = html_escape(a["name"])
            trophies = a["trophies"]
            plat = a["platinum"]
            psn_blocks.append(f"🎮 <b>{prefix}:</b> {name} · {trophies} 🏆 ({plat} 🏆){muted}")
        psn_text = "\n".join(psn_blocks)

        xb_muted = (
            "🔇 <i>Публикация отключена</i>" if not state.xbox_publishes else "🔔 Публикуется"
        )
        st_muted = (
            "🔇 <i>Публикация отключена</i>" if not state.steam_publishes else "🔔 Публикуется"
        )

        text = (
            "👤 <b>Карточка пользователя в /admin (#10, #20)</b>\n\n"
            "Пользователь: <b>@GamerAdmin (Igor)</b>  [ID: 188022193]\n"
            f"Глобальная редкость (#126): <b>{_rarity_title(state.rarity_mode)}</b>\n\n"
            "🎮 <b>XBOX:</b> MajorNelson  ·  14 520 G  ·  325 ачивок\n"
            f"   {xb_muted}\n"
            "🎮 <b>Steam:</b> Gaben  ·  89 ачивок\n"
            f"   {st_muted}\n"
            f"{psn_text}\n\n"
            "<i>Все аккаунты PSN (1..3) видны списком, а отключенные тумблером "
            "помечаются меткой 'Публикация отключена'.</i>"
        )
        builder.row(InlineKeyboardButton(text="◀️ Назад в админку", callback_data="tp:admin"))
        return text, builder.as_markup()

    # =========================================================================
    # 5. Chat Hub (Хаб в чате)
    # =========================================================================
    if screen == "chat_hub":
        text = (
            "💬 <b>Хаб чата: Xbox & PlayStation Club</b>\n\n"
            "🔔 В этом чате публикуются достижения участников:\n"
            "• @GamerAdmin, @PlayerTwo, @SnakeEater\n\n"
            "<i>🎮 Привяжи свои аккаунты, чтобы делиться победами!</i>\n\n"
            "<code>tg_achievement_bot v1.5.0</code>"
        )
        builder.row(
            InlineKeyboardButton(text="👤 Кто здесь?", callback_data="tp:noop:hub_who"),
            InlineKeyboardButton(text="🟢 Кто в сети", callback_data="tp:screen:online"),
            InlineKeyboardButton(text="⏳ Недавние", callback_data="tp:screen:recent"),
        )
        builder.row(
            InlineKeyboardButton(text="📅 Итоги дня", callback_data="tp:screen:sum_day"),
            InlineKeyboardButton(text="🗓️ Итоги месяца", callback_data="tp:screen:sum_month"),
        )
        hub_pub_label = "🔕 Не публиковать сюда" if state.hub_publishes else "🔔 Публиковать сюда"
        builder.row(
            InlineKeyboardButton(text=hub_pub_label, callback_data="tp:toggle_hub_pub"),
            InlineKeyboardButton(text="⚙️ Настройки чата", callback_data="tp:noop:hub_settings"),
        )
        builder.row(
            InlineKeyboardButton(text="🟢 XBOX", callback_data="tp:noop:connect_xbox"),
            InlineKeyboardButton(text="🔵 PSN", callback_data="tp:noop:connect_psn"),
            InlineKeyboardButton(text="⚪ Steam", callback_data="tp:noop:connect_steam"),
        )
        builder.row(InlineKeyboardButton(text="🧭 В каталог экранов", callback_data="tp:showcase"))
        return text, builder.as_markup()

    # =========================================================================
    # 6. Player Stats (/stats)
    # =========================================================================
    if screen == "stats":
        is_multi_psn = len(state.psn_accounts) > 1
        psn_lines = []
        for idx, a in enumerate(state.psn_accounts, 1):
            prefix = f"PSN{idx}" if is_multi_psn else "PSN"
            psn_lines.append(
                f"🎮 <b>{prefix}:</b> {html_escape(a['name'])}  ·  "
                f"{a['level']} ур.  ·  {a['trophies']} 🏆 ({a['platinum']} 🏆)"
            )
        psn_block = "\n".join(psn_lines)

        text = (
            "📊 <b>Статистика: GamerAdmin</b>  ·  14 520 G  ·  325 ачивок  ·  184 🏆\n\n"
            "🎮 <b>XBOX:</b> MajorNelson  ·  14 520 G  ·  325 ачивок\n"
            "🎮 <b>Steam:</b> Gaben  ·  89 ачивок  ·  4 🏆\n"
            f"{psn_block}\n\n"
            "<b>Популярные игры:</b>\n"
            "• Halo Infinite — 1000/1000 G (100%)\n"
            "• God of War Ragnarök — 🏆 36/36 (Платина)\n"
            "• Metal Gear Solid Delta — 🏆 18/42\n"
            "• Half-Life 2 — 33/33 (100%)\n"
            "• Elden Ring — 42/42 (100%)\n\n"
            "📅 <b>За сегодня:</b> 4 ачивки (+85 G)\n"
            "🗓️ <b>За сентябрь:</b> 28 ачивок (+640 G, 1 🏆)"
        )
        builder.row(
            InlineKeyboardButton(text="👤 Профиль XBOX", callback_data="tp:noop:xbox_profile"),
            InlineKeyboardButton(text="👤 Профиль Steam", callback_data="tp:noop:steam_profile"),
        )
        if state.psn_accounts:
            p_btns = []
            for idx, a in enumerate(state.psn_accounts, 1):
                prefix = f"PSN{idx}" if is_multi_psn else "PSN"
                p_btns.append(
                    InlineKeyboardButton(
                        text=f"👤 {prefix}: {a['name']}", callback_data="tp:noop:psn_profile"
                    )
                )
            builder.row(*p_btns)
        builder.row(
            InlineKeyboardButton(text="📅 За сегодня (4)", callback_data="tp:screen:sum_day"),
            InlineKeyboardButton(text="🗓️ За месяц (28)", callback_data="tp:screen:sum_month"),
        )
        builder.row(InlineKeyboardButton(text="🧭 В каталог экранов", callback_data="tp:showcase"))
        return text, builder.as_markup()

    # =========================================================================
    # 7. Summary: Day & Month
    # =========================================================================
    if screen == "summary_day":
        text = (
            "📅 <b>Итоги дня: 27 сентября</b>\n"
            "💬 Чат «Xbox & PlayStation Club»\n\n"
            "Всего за 24 часа выбито <b>14 достижений</b> (+320 G, 2 🏆) в 4 играх.\n\n"
            "🏆 <b>Таблица лидеров:</b>\n"
            "1. 🥇 <b>GamerAdmin</b> — 6 ачивок (+150 G, 1 🏆)\n"
            "   • Halo Infinite (3), God of War (3)\n"
            "2. 🥈 <b>SnakeEater</b> — 5 ачивок (+120 G)\n"
            "   • MGS Delta (5)\n"
            "3. 🥉 <b>Cortana</b> — 3 ачивки (+50 G, 1 🏆)\n"
            "   • Forza Horizon 5 (3)\n"
            "4. <b>Chief117</b> — 0 ачивок"
        )
        builder.row(
            InlineKeyboardButton(text="◀️ 26 сен", callback_data="tp:noop:prev_day"),
            InlineKeyboardButton(text="🔘 27 сен (сегодня)", callback_data="tp:noop:cur_day"),
            InlineKeyboardButton(text="28 сен ▶️", callback_data="tp:noop:next_day"),
        )
        builder.row(
            InlineKeyboardButton(
                text="👥 Показать всех участников (4)", callback_data="tp:noop:full_roster"
            )
        )
        builder.row(InlineKeyboardButton(text="🧭 В каталог экранов", callback_data="tp:showcase"))
        return text, builder.as_markup()

    if screen == "summary_month":
        text = (
            "🗓️ <b>Итоги месяца: Сентябрь 2026</b>\n"
            "💬 Чат «Xbox & PlayStation Club»\n\n"
            "Всего за месяц выбито <b>184 достижения</b> (+4 120 G, 12 🏆) в 18 играх.\n\n"
            "🏆 <b>Таблица лидеров месяца:</b>\n"
            "1. 🥇 <b>GamerAdmin</b> — 86 ачивок (+1 840 G, 5 🏆)\n"
            "2. 🥈 <b>Chief117</b> — 54 ачивки (+1 200 G, 4 🏆)\n"
            "3. 🥉 <b>SnakeEater</b> — 32 ачивки (+780 G, 2 🏆)\n"
            "4. <b>Cortana</b> — 12 ачивок (+300 G, 1 🏆)"
        )
        builder.row(
            InlineKeyboardButton(text="◀️ Август", callback_data="tp:noop:prev_month"),
            InlineKeyboardButton(text="🔘 Сентябрь 2026", callback_data="tp:noop:cur_month"),
            InlineKeyboardButton(text="Октябрь ▶️", callback_data="tp:noop:next_month"),
        )
        builder.row(
            InlineKeyboardButton(
                text="👥 Показать полный список", callback_data="tp:noop:full_month"
            )
        )
        builder.row(InlineKeyboardButton(text="🧭 В каталог экранов", callback_data="tp:showcase"))
        return text, builder.as_markup()

    # =========================================================================
    # 8. Single Achievement & Digest Cards
    # =========================================================================
    if screen == "single_achievement":
        text = (
            "🎮 <b>GamerAdmin</b> получает достижение:\n\n"
            "<i>Halo Infinite (Xbox Series X)</i>  ·  34/119\n"
            "💎 <b>«Восхождение Спартанца»</b>  ·  50 G  ·  3.4%\n\n"
            '<span class="tg-spoiler">Завершите все испытания кампании на Легендарной сложности '
            "без использования черепов-модификаторов.</span>"
        )
        builder.row(
            InlineKeyboardButton(
                text="🎮 Halo Infinite (Прогресс)", callback_data="tp:noop:game_info"
            ),
            InlineKeyboardButton(
                text="👤 Профиль GamerAdmin", callback_data="tp:noop:player_profile"
            ),
        )
        builder.row(InlineKeyboardButton(text="🧭 В каталог экранов", callback_data="tp:showcase"))
        return text, builder.as_markup()

    if screen == "digest_achievement":
        is_multi_psn = len(state.psn_accounts) > 1
        psn_prefix = "PSN1" if is_multi_psn else "PSN"
        text = (
            "🎮 <b>GamerAdmin</b> выбивает <b>3 трофея</b>:\n\n"
            "<i>God of War Ragnarök (PS5)</i>  ·  🏆 24/36\n"
            f"• {psn_prefix} (Kratos)\n"
            "🥉 <b>«Холодный приём»</b>  ·  42%\n"
            "🥈 <b>«Охотник на валькирий»</b>  ·  12.5%\n"
            "🏆 <b>«Чистильщик девяти миров»</b>  ·  4.1%"
        )
        builder.row(
            InlineKeyboardButton(text="🎮 God of War Ragnarök", callback_data="tp:noop:game_info"),
            InlineKeyboardButton(
                text=f"👤 Профиль {psn_prefix}", callback_data="tp:noop:psn_profile"
            ),
        )
        builder.row(InlineKeyboardButton(text="🧭 В каталог экранов", callback_data="tp:showcase"))
        return text, builder.as_markup()

    # =========================================================================
    # 9. Online & Recent (/online, /recent)
    # =========================================================================
    if screen == "online":
        text = (
            "🟢 <b>Сейчас в сети</b> (обновлено 13:45 UTC+3)\n\n"
            "🟢 <b>MajorNelson</b> — играет в <i>Halo Infinite (Xbox)</i>\n"
            "🔵 <b>Kratos</b> — играет в <i>God of War Ragnarök (PS5)</i>\n"
            "⚪ <b>Gaben</b> — в сети (Steam)\n"
            "⚫ <b>Chief117</b> — не в сети (35 мин. назад)\n"
            "⚫ <b>Cortana</b> — не в сети (3 ч. назад)"
        )
        builder.row(
            InlineKeyboardButton(text="🔄 Обновить список", callback_data="tp:noop:refresh_online"),
            InlineKeyboardButton(text="👥 Все участники", callback_data="tp:noop:all_online"),
        )
        builder.row(InlineKeyboardButton(text="🧭 В каталог экранов", callback_data="tp:showcase"))
        return text, builder.as_markup()

    if screen == "recent":
        text = (
            "⏳ <b>Недавние достижения в чате:</b>\n\n"
            "• 13:20 🎮 <b>GamerAdmin</b>: 💎 «Восхождение Спартанца» (+50 G) · "
            "<i>Halo Infinite</i>\n"
            "• 12:45 🎮 <b>GamerAdmin</b>: 🏆 «Чистильщик девяти миров» · <i>God of War</i>\n"
            "• 11:10 🎮 <b>SnakeEater</b>: 🥈 «Тихий шаг» (+25 G) · <i>MGS Delta</i>\n"
            "• Вчера 🎮 <b>Chief117</b>: 💎 «Мастер Чиф на века» (+100 G) · <i>MCC</i>"
        )
        builder.row(
            InlineKeyboardButton(text="🔄 Обновить ленту", callback_data="tp:noop:refresh_recent")
        )
        builder.row(InlineKeyboardButton(text="🧭 В каталог экранов", callback_data="tp:showcase"))
        return text, builder.as_markup()

    return "Неизвестный экран", builder.as_markup()
