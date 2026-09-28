"""Interactive test panel handlers for user PM panel (#10, #20, #126, #141).

Provides an in-memory stub/mock screen in private Telegram messages
so admins can test UX, submenus, toggle switches, and navigation
for the user panel during development.
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
    _rarity_title,
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


@router.message(Command("test_panel", "testpanel"))
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
    if action in ("home", "panel"):
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

    if action == "psn_add":
        text, markup = render_screen("psn_add", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer()
        return

    # 2. Interactive toggles
    if action == "cycle_rarity":
        order = ["all", "rare", "hidden"]
        idx = order.index(state.rarity_mode) if state.rarity_mode in order else 0
        state.rarity_mode = order[(idx + 1) % len(order)]
        text, markup = render_screen("home", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer(f"Редкость: {_rarity_title(state.rarity_mode)}")
        return

    if action == "pub":
        plat = parts[2] if len(parts) > 2 else "xbox"
        if plat == "xbox":
            state.xbox_publishes = not state.xbox_publishes
            toast = f"XBOX: {'🔔' if state.xbox_publishes else '🔇'}"
        elif plat == "steam":
            state.steam_publishes = not state.steam_publishes
            toast = f"Steam: {'🔔' if state.steam_publishes else '🔇'}"
        elif plat == "psn":
            new_val = not any(a["publishes"] for a in state.psn_accounts)
            for a in state.psn_accounts:
                a["publishes"] = new_val
            toast = f"PSN: {'🔔' if new_val else '🔇'}"
        else:
            toast = "Обновлено"

        # If on submenu, refresh submenu; otherwise refresh home
        text, markup = render_screen("home", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer(toast)
        return

    if action == "toggle_psn_pub":
        acc_id = parts[2] if len(parts) > 2 else "1"
        found = next((a for a in state.psn_accounts if a["id"] == acc_id), None)
        if found:
            found["publishes"] = not found["publishes"]
            toast = f"{found['name']}: {'🔔' if found['publishes'] else '🔇'}"
        else:
            toast = "Аккаунт не найден"
        text, markup = render_screen("acc:psn", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer(toast)
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
            toast = "Подписан" if chat["subscribed"] else "Отписан"
        else:
            toast = "Чат не найден"
        text, markup = render_screen("chat_detail", state, {"chat_id": chat_id})
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer(toast)
        return

    if action == "del_chat_prompt":
        chat_id = int(parts[2]) if len(parts) > 2 else 101
        text, markup = render_screen("chat_del_confirm", state, {"chat_id": chat_id})
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer()
        return

    if action == "do_chat_del":
        chat_id = int(parts[2]) if len(parts) > 2 else 101
        state.chats = [c for c in state.chats if c["id"] != chat_id]
        await callback.answer("Чат удалён из списка", show_alert=True)
        text, markup = render_screen("chats", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        return

    if action == "do_psn_add":
        if len(state.psn_accounts) < 3:
            new_acc = {
                "id": str(len(state.psn_accounts) + 1),
                "name": "Hunter",
                "publishes": True,
                "level": 12,
                "trophies": 15,
                "platinum": 0,
            }
            state.psn_accounts.append(new_acc)
            await callback.answer("⚙️ [Заглушка]: Аккаунт Hunter успешно привязан!", show_alert=True)
        else:
            await callback.answer("Достигнут максимум (3 аккаунта)", show_alert=True)
        text, markup = render_screen("acc:psn", state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        return

    if action == "unlink_confirm":
        plat = parts[2] if len(parts) > 2 else "psn"
        acc_id = parts[3] if len(parts) > 3 else "0"
        text, markup = render_screen("unlink_confirm", state, {"platform": plat, "acc_id": acc_id})
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
        await callback.answer("⚙️ [Заглушка]: Аккаунт отвязан.", show_alert=True)
        text, markup = render_screen(next_screen, state)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        return

    if action == "reset":
        reset_mock_state(user_id)
        text, markup = render_screen("home", get_mock_state(user_id))
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer("Все настройки сброшены", show_alert=True)
        return

    if action == "noop":
        sub = parts[2] if len(parts) > 2 else ""
        if sub == "sync":
            toast = "Синхронизирую… (заглушка)"
        else:
            toast = "⚙️ [Заглушка]: Интерактивное демо-действие."
        await callback.answer(toast, show_alert=True)
        return

    await callback.answer()
