"""Interactive test panel views (#10, #20, #126).

Renders screens for testing UX, submenus, toggle switches, and navigation.
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
    psn_accounts: list[dict] = field(
        default_factory=lambda: [
            {
                "id": "1",
                "name": "Kratos (основной)",
                "publishes": True,
                "level": 45,
                "trophies": 120,
                "platinum": 5,
            },
            {
                "id": "2",
                "name": "Snake (второй)",
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


def _rarity_name(mode: str) -> str:
    if mode == "rare":
        return "редкие"
    if mode == "hidden":
        return "никакие"
    return "все"


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

    if screen == "home":
        psn_pub_text = []
        for a in state.psn_accounts:
            st = "🔔 Публикуется" if a["publishes"] else "🔇 Не публикуется"
            psn_pub_text.append(f"• PSN ({html_escape(a['name'])}): {st}")
        psn_summary = "\n".join(psn_pub_text)

        rarity_str = _rarity_name(state.rarity_mode)
        secrets_str = "показывать" if state.show_secrets else "не показывать"

        text = (
            "👤 <b>Тестовая панель (Демо-режим)</b>\n"
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
            f"🎯 <b>Достижения (#126):</b> {rarity_str}\n"
            f"👁 <b>Секретные достижения:</b> {secrets_str}\n"
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

        # 3. Rarity cycle button
        builder.row(
            InlineKeyboardButton(
                text=f"Публиковать достижения: {rarity_str}",
                callback_data="tp:cycle_rarity",
            )
        )

        # 4. Secret achievements toggle
        builder.row(
            InlineKeyboardButton(
                text=f"Секретные достижения: {secrets_str}",
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
            InlineKeyboardButton(text="🔄 Сбросить состояние заглушек", callback_data="tp:reset")
        )
        return text, builder.as_markup()

    if screen == "acc:psn":
        lines = [
            f"🎮 <b>PlayStation Network ({len(state.psn_accounts)} из 3 аккаунтов) (#10)</b>",
            "<i>Управление несколькими аккаунтами PSN для одного человека.</i>\n",
        ]
        for a in state.psn_accounts:
            lines.append(
                f"<b>PSN: {html_escape(a['name'])}</b> · {a['level']} ур. · {a['trophies']} 🏆"
            )
            lines.append("Статус: Открытый профиль")
            lines.append(
                f"Публикация: {'🔔 Публикуется' if a['publishes'] else '🔇 Заглушен (#20)'}\n"
            )

        if len(state.psn_accounts) > 1:
            lines.append(
                "<i>Статистика в профиле суммируется, "
                "а одинаковые трофеи в каталоге игр дедуплицируются.</i>"
            )

        for a in state.psn_accounts:
            builder.row(
                InlineKeyboardButton(
                    text=f"👤 Профиль: {a['name']}", callback_data="tp:noop:profile"
                )
            )
            builder.row(
                InlineKeyboardButton(
                    text="🔔 Публикуется" if a["publishes"] else "🔇 Не публикуется",
                    callback_data=f"tp:toggle_psn_pub:{a['id']}",
                ),
                InlineKeyboardButton(
                    text="🔌 Отвязать", callback_data=f"tp:unlink_confirm:psn:{a['id']}"
                ),
            )

        if len(state.psn_accounts) < 3:
            builder.row(
                InlineKeyboardButton(
                    text=f"➕ Добавить аккаунт ({len(state.psn_accounts) + 1}/3)",
                    callback_data="tp:psn_add",
                )
            )
        builder.row(InlineKeyboardButton(text="‹ Назад", callback_data="tp:home"))
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
            InlineKeyboardButton(text="🔌 Отвязать", callback_data="tp:unlink_confirm:xbox:0")
        )
        builder.row(InlineKeyboardButton(text="‹ Назад", callback_data="tp:home"))
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
            InlineKeyboardButton(text="🔌 Отвязать", callback_data="tp:unlink_confirm:steam:0")
        )
        builder.row(InlineKeyboardButton(text="‹ Назад", callback_data="tp:home"))
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
        if plat == "psn":
            acc = next((a for a in state.psn_accounts if a["id"] == acc_id), None)
            if acc:
                name = f"PSN '{acc['name']}'"
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
        builder.row(InlineKeyboardButton(text="‹ Назад", callback_data="tp:home"))
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
            f"Редкость: из вашего профиля (<b>{_rarity_name(state.rarity_mode)}</b>)\n"
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
        builder.row(InlineKeyboardButton(text="‹ К списку чатов", callback_data="tp:chats"))
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
                    text=f"{mark}{_format_offset(off)}", callback_data=f"tp:set_tz:{off}"
                )
            )
            if len(row_buttons) == 4:
                builder.row(*row_buttons)
                row_buttons = []
        if row_buttons:
            builder.row(*row_buttons)
        builder.row(InlineKeyboardButton(text="‹ Назад", callback_data="tp:home"))
        return text, builder.as_markup()

    if screen == "admin":
        text = (
            "⚙️ <b>Панель администратора (Демо-режим /admin)</b>\n\n"
            "1. <b>Новые пользователи (#126):</b>\n"
            f"• Редкость по умолчанию: <b>{_rarity_name(state.default_rarity)}</b>\n\n"
            "2. <b>Глобальные настройки проекта:</b>\n"
            f"• Ссылки на профили: <b>{'✅ Да' if state.default_links else '⚪ Нет'}</b>\n\n"
            "3. <b>Настройки групп (#126):</b>\n"
            f"• Порог группировки в дайджест: <b>{state.admin_chat_digest} ачивок</b>\n\n"
            "4. <b>Мульти-аккаунты (#10, #20):</b>\n"
            "• В карточках пользователей отображаются все привязанные аккаунты PSN (1..3) "
            "и метка 🔇 Заглушен, если юзер отключил публикации."
        )
        builder.row(
            InlineKeyboardButton(
                text=f"🎯 Редкость новичков: {_rarity_name(state.default_rarity)}",
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
            InlineKeyboardButton(text="🔄 Сбросить настройки админки", callback_data="tp:reset")
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
                InlineKeyboardButton(text=f"{mark}{label}", callback_data=f"tp:set_digest:{c}")
            )
            if len(row_buttons) == 3:
                builder.row(*row_buttons)
                row_buttons = []
        if row_buttons:
            builder.row(*row_buttons)
        builder.row(InlineKeyboardButton(text="‹ Назад в админку", callback_data="tp:admin"))
        return text, builder.as_markup()

    if screen == "adm_usercard":
        psn_blocks = []
        for a in state.psn_accounts:
            muted = "" if a["publishes"] else "\n   🔇 <i>Публикация выключена (#20)</i>"
            name = html_escape(a["name"])
            trophies = a["trophies"]
            plat = a["platinum"]
            psn_blocks.append(f"🎮 <b>PSN:</b> {name} · {trophies} 🏆 ({plat} 🏆){muted}")
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
            f"Глобальная редкость (#126): <b>{_rarity_name(state.rarity_mode)}</b>\n\n"
            "🎮 <b>XBOX:</b> MajorNelson  ·  14 520 G  ·  325 ачивок\n"
            f"   {xb_muted}\n"
            "🎮 <b>Steam:</b> Gaben  ·  89 ачивок\n"
            f"   {st_muted}\n"
            f"{psn_text}\n\n"
            "<i>Все аккаунты PSN (1..3) видны списком, а отключенные тумблером "
            "помечаются меткой 'Публикация отключена'.</i>"
        )
        builder.row(InlineKeyboardButton(text="‹ Назад в админку", callback_data="tp:admin"))
        return text, builder.as_markup()

    return "Неизвестный экран", builder.as_markup()
