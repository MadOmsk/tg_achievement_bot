"""Interactive test panel for user and admin features (#10, #20, #126).

Provides an in-memory stub/mock screen in private Telegram messages
so admins can test UX, submenus, toggle switches, and navigation
without mutating production or test database state.
"""

from __future__ import annotations

import contextlib

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import Settings
from bot.views.test_panel import (
    MockPanelState,
    _format_offset,
    _rarity_name,
    render_screen,
)

router = Router(name="test_panel")


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, settings: Settings) -> bool:
        user = getattr(event, "from_user", None)
        return user is not None and settings.is_admin(user.id)


router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


_USER_STATES: dict[int, MockPanelState] = {}


def get_mock_state(tg_id: int) -> MockPanelState:
    if tg_id not in _USER_STATES:
        _USER_STATES[tg_id] = MockPanelState()
    return _USER_STATES[tg_id]


def reset_mock_state(tg_id: int) -> MockPanelState:
    _USER_STATES[tg_id] = MockPanelState()
    return _USER_STATES[tg_id]


@router.message(Command("test_panel", "testpanel", "demo"))
async def handle_test_panel_cmd(message: Message) -> None:
    if message.chat.type != ChatType.PRIVATE:
        await message.answer("Команда доступна только в личных сообщениях с ботом.")
        return
    state = get_mock_state(message.from_user.id)
    text, markup = render_screen("home", state)
    await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("tp:"))
async def handle_test_panel_callback(callback: CallbackQuery) -> None:
    data = callback.data or ""
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else "home"
    user_id = callback.from_user.id
    state = get_mock_state(user_id)

    # 1. Navigation
    if action == "home":
        text, markup = render_screen("home", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer()
        return

    if action == "acc":
        plat = parts[2] if len(parts) > 2 else "xbox"
        text, markup = render_screen(f"acc:{plat}", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer()
        return

    if action == "rarity":
        text, markup = render_screen("rarity", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer()
        return

    if action == "chats":
        text, markup = render_screen("chats", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer()
        return

    if action == "chat":
        chat_id = int(parts[2]) if len(parts) > 2 else 101
        text, markup = render_screen("chat_detail", state, {"chat_id": chat_id})
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer()
        return

    if action == "tz":
        text, markup = render_screen("tz", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer()
        return

    if action == "admin":
        text, markup = render_screen("admin", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer()
        return

    if action == "adm_digest":
        text, markup = render_screen("adm_digest", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer()
        return

    if action == "adm_usercard":
        text, markup = render_screen("adm_usercard", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer()
        return

    if action == "psn_add":
        text, markup = render_screen("psn_add", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer()
        return

    # 2. State Toggles & Actions (#20, #126, #10)
    if action == "pub":
        plat = parts[2] if len(parts) > 2 else "xbox"
        if plat == "xbox":
            state.xbox_publishes = not state.xbox_publishes
            toast = (
                "XBOX: 🔔 Публикация вкл" if state.xbox_publishes else "XBOX: 🔇 Публикация выкл"
            )
        elif plat == "steam":
            state.steam_publishes = not state.steam_publishes
            toast = (
                "Steam: 🔔 Публикация вкл" if state.steam_publishes else "Steam: 🔇 Публикация выкл"
            )
        elif plat == "psn":
            # Toggle all PSN accounts together from home screen
            any_pub = any(a["publishes"] for a in state.psn_accounts)
            new_val = not any_pub
            for a in state.psn_accounts:
                a["publishes"] = new_val
            toast = "PSN: 🔔 Публикация вкл" if new_val else "PSN: 🔇 Публикация выкл"
        else:
            toast = "Обновлено"

        text, markup = render_screen("home", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer(toast)
        return

    if action == "toggle_psn_pub":
        acc_id = parts[2] if len(parts) > 2 else "1"
        acc = next((a for a in state.psn_accounts if a["id"] == acc_id), None)
        if acc:
            acc["publishes"] = not acc["publishes"]
            toast = f"{acc['name']}: 🔔 Вкл" if acc["publishes"] else f"{acc['name']}: 🔇 Заглушен"
        else:
            toast = "Аккаунт не найден"
        text, markup = render_screen("acc:psn", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer(toast)
        return

    if action == "toggle_links":
        state.show_profile_links = not state.show_profile_links
        toast = "Ссылки на профили: Вкл" if state.show_profile_links else "Ссылки на профили: Выкл"
        text, markup = render_screen("home", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer(toast)
        return

    if action == "toggle_secrets":
        state.show_secrets = not state.show_secrets
        toast = "Секретные ачивки: Вкл" if state.show_secrets else "Секретные ачивки: Выкл"
        text, markup = render_screen("home", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer(toast)
        return

    if action == "set_rarity":
        mode = parts[2] if len(parts) > 2 else "all"
        state.rarity_mode = mode
        text, markup = render_screen("rarity", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer(f"Редкость: {_rarity_name(mode)}")
        return

    if action == "set_tz":
        off = int(parts[2]) if len(parts) > 2 else 180
        state.tz_offset_min = off
        text, markup = render_screen("tz", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer(f"Часовой пояс: {_format_offset(off)}")
        return

    if action == "toggle_sub":
        chat_id = int(parts[2]) if len(parts) > 2 else 101
        chat = next((c for c in state.chats if c["id"] == chat_id), None)
        if chat:
            chat["subscribed"] = not chat["subscribed"]
            toast = "Публикация сюда: Вкл" if chat["subscribed"] else "Публикация сюда: Выкл"
        else:
            toast = "Чат не найден"
        text, markup = render_screen("chat_detail", state, {"chat_id": chat_id})
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer(toast)
        return

    if action == "do_psn_add":
        if len(state.psn_accounts) < 3:
            new_acc = {
                "id": str(len(state.psn_accounts) + 1),
                "name": "Hunter3 (третий)",
                "publishes": True,
                "level": 12,
                "trophies": 15,
                "platinum": 0,
            }
            state.psn_accounts.append(new_acc)
            await callback.answer(
                "⚙️ [Заглушка]: Аккаунт Hunter3 успешно привязан!", show_alert=True
            )
        else:
            await callback.answer("Достигнут максимум (3 аккаунта)", show_alert=True)
        text, markup = render_screen("acc:psn", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        return

    if action == "unlink_confirm":
        plat = parts[2] if len(parts) > 2 else "psn"
        acc_id = parts[3] if len(parts) > 3 else "0"
        text, markup = render_screen("unlink_confirm", state, {"platform": plat, "id": acc_id})
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer()
        return

    if action == "do_unlink":
        plat = parts[2] if len(parts) > 2 else "psn"
        acc_id = parts[3] if len(parts) > 3 else "0"
        if plat == "psn":
            state.psn_accounts = [a for a in state.psn_accounts if a["id"] != acc_id]
            next_screen = "acc:psn"
        else:
            next_screen = "home"
        await callback.answer("⚙️ [Заглушка]: Аккаунт отключен.", show_alert=True)
        text, markup = render_screen(next_screen, state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        return

    if action == "adm_cycle_rarity":
        order = ["all", "rare", "hidden"]
        idx = order.index(state.default_rarity) if state.default_rarity in order else 0
        state.default_rarity = order[(idx + 1) % len(order)]
        text, markup = render_screen("admin", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer(f"Редкость новичков: {_rarity_name(state.default_rarity)}")
        return

    if action == "adm_toggle_links":
        state.default_links = not state.default_links
        text, markup = render_screen("admin", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer(
            "Ссылки новичков: Вкл" if state.default_links else "Ссылки новичков: Выкл"
        )
        return

    if action == "set_digest":
        val = int(parts[2]) if len(parts) > 2 else 5
        state.admin_chat_digest = val
        text, markup = render_screen("adm_digest", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer(f"Порог дайджеста: {val if val < 99 else 'Никогда'}")
        return

    if action == "reset":
        reset_mock_state(user_id)
        text, markup = render_screen("home", get_mock_state(user_id))
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer("Состояние тестовой панели сброшено", show_alert=True)
        return

    if action == "noop":
        await callback.answer(
            "⚙️ [Заглушка]: Это демонстрационная ссылка на профиль.", show_alert=True
        )
        return

    await callback.answer()
