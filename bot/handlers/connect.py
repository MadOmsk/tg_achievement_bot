"""/start opens the Mini App; timezone callbacks; leftover connect callbacks."""

from __future__ import annotations

import contextlib
import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from aiogram_i18n import I18nContext

from bot.config import Settings
from bot.constants import TokenStatus
from bot.db.repo import Repo
from bot.handlers.keyboards import (
    TZ_MANUAL,
    TZ_MORE,
    TZ_SET,
    TZ_SKIP,
    connect_keyboard,
    format_offset,
    safe_edit,
    timezone_keyboard,
)
from bot.services.connect import ConnectService
from bot.services.mini_app import mini_app_open_markup
from bot.services.notify import AdminNotifier
from bot.util import parse_utc_offset

log = logging.getLogger(__name__)

router = Router(name="connect")

REVOKE_URL = "https://account.live.com/consent/Manage"

# Old slash commands are not supported — swallow so leftover panel/chat/admin
# handlers never answer them. Mini App only (/start, /app stay).
_LEGACY_COMMANDS = (
    "panel",
    "stats",
    "online",
    "who",
    "recent",
    "summary",
    "summary_day",
    "summary_month",
    "hltb",
    "help",
    "subscribe",
    "unsubscribe",
    "delete_last",
    "admin",
    "connect_xbox",
    "disconnect_xbox",
    "connect_steam",
    "disconnect_steam",
    "connect_psn",
    "disconnect_psn",
)


def open_app_markup(
    settings: Settings,
    i18n: I18nContext,
    *,
    chat_id: int | None = None,
    bot_username: str = "",
    in_group: bool = False,
) -> InlineKeyboardMarkup | None:
    url = (settings.mini_app_url or "").strip()
    if not url:
        return None
    text = i18n.get("connect-open-app-button")
    if chat_id is not None:
        return mini_app_open_markup(
            text,
            https_url=url,
            bot_username=bot_username,
            chat_id=chat_id,
            in_group=in_group,
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=text,
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )


async def send_open_app(
    message: Message, settings: Settings, i18n: I18nContext, *, chat_id: int | None = None
) -> None:
    in_group = message.chat.type != ChatType.PRIVATE
    username = ""
    if in_group or chat_id is not None:
        me = await message.bot.me()
        username = me.username or ""
    await message.answer(
        i18n.get("connect-open-app-hint"),
        reply_markup=open_app_markup(
            settings,
            i18n,
            chat_id=chat_id if chat_id is not None else (message.chat.id if in_group else None),
            bot_username=username,
            in_group=in_group,
        ),
    )


@router.message(CommandStart(deep_link=True))
async def start_with_payload(
    message: Message,
    command: CommandObject,
    repo: Repo,
    settings: Settings,
    i18n: I18nContext,
) -> None:
    await repo.ensure_user(message.chat.id, _username(message))
    is_connect, origin_chat_id = _parse_connect_payload(command.args or "")
    await send_open_app(message, settings, i18n, chat_id=origin_chat_id if is_connect else None)


@router.message(CommandStart())
async def start(
    message: Message,
    repo: Repo,
    i18n: I18nContext,
    settings: Settings,
) -> None:
    await repo.ensure_user(message.chat.id, _username(message))
    await send_open_app(message, settings, i18n)


@router.message(Command(*_LEGACY_COMMANDS))
async def ignore_legacy_commands(message: Message) -> None:
    return


@router.message(Command("connect_xbox"))
async def connect_command(
    message: Message, repo: Repo, connect: ConnectService, i18n: I18nContext
) -> None:
    await repo.ensure_user(message.chat.id, _username(message))
    user = await repo.get_user(message.chat.id)
    if user is not None and user.xuid:
        await message.answer(i18n.get("connect-xbox-already-connected-relogin"))
        return
    await _send_login_link(message, connect, i18n)


@router.message(Command("disconnect_xbox"))
async def disconnect_command(message: Message, repo: Repo, i18n: I18nContext) -> None:
    user = await repo.get_user(message.chat.id)
    if user is None or not user.xuid:
        await message.answer(i18n.get("connect-xbox-not-connected"))
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("connect-disconnect-yes"), callback_data="disconnect:yes"
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("connect-disconnect-cancel"), callback_data="disconnect:no"
                )
            ],
        ]
    )
    await message.answer(
        i18n.get("connect-disconnect-prompt", revoke_url=REVOKE_URL),
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "disconnect:no")
async def disconnect_cancel(callback: CallbackQuery) -> None:
    # Nothing changed — just remove the prompt instead of leaving a
    # "cancelled" message behind for no reason.
    if isinstance(callback.message, Message):
        with contextlib.suppress(Exception):
            await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data == "disconnect:yes")
async def disconnect_confirm(
    callback: CallbackQuery, repo: Repo, notifier: AdminNotifier, i18n: I18nContext
) -> None:
    tg_id = callback.from_user.id
    user = await repo.get_user(tg_id)
    gamertag = (user.gamertag if user else None) or f"id{tg_id}"
    if user is not None and user.xuid:
        await repo.delete_presence_state(user.xuid)
    await repo.delete_token(tg_id)
    await repo.delete_subscriptions_of_user(tg_id)
    await repo.unlink_xbox_account(tg_id)
    await notifier.user_disconnected(tg_id, gamertag, "disconnect-command")

    # Found while refactoring (2026-09-05): none of the edits in this file
    # tolerated a failed edit, unlike panel.py/steam.py's own — now they do.
    await safe_edit(
        callback,
        i18n.get("connect-disconnected", revoke_url=REVOKE_URL),
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data == "relogin")
async def relogin(callback: CallbackQuery, connect: ConnectService, i18n: I18nContext) -> None:
    """Button from the "access expired" reminder (SPEC 5.1.1)."""
    url = connect.start_login(callback.from_user.id)
    if isinstance(callback.message, Message):
        await callback.message.answer(
            i18n.get("connect-relogin-prompt"),
            reply_markup=connect_keyboard(url, i18n),
        )
    await callback.answer()


@router.callback_query(F.data == "optout")
async def optout(
    callback: CallbackQuery, repo: Repo, notifier: AdminNotifier, i18n: I18nContext
) -> None:
    """Left on purpose: subscriptions go, history stays, reminders stop."""
    tg_id = callback.from_user.id
    user = await repo.get_user(tg_id)
    await repo.set_token_status(tg_id, TokenStatus.REVOKED)
    await repo.delete_subscriptions_of_user(tg_id)
    await notifier.user_disconnected(
        tg_id, (user.gamertag if user else None) or f"id{tg_id}", "disconnect-button"
    )
    await safe_edit(callback, i18n.get("connect-optout-done"))
    await callback.answer()


@router.callback_query(F.data == TZ_MORE)
async def timezone_full_list(callback: CallbackQuery, i18n: I18nContext) -> None:
    await safe_edit(
        callback, i18n.get("connect-timezone-prompt"), timezone_keyboard(i18n, full=True)
    )
    await callback.answer()


@router.callback_query(F.data == TZ_SKIP)
async def timezone_skip(callback: CallbackQuery, i18n: I18nContext) -> None:
    await safe_edit(callback, i18n.get("connect-timezone-skip-done"))
    await callback.answer()


@router.callback_query(F.data.startswith(f"{TZ_SET}:"))
async def timezone_set(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    minutes = int(callback.data.rsplit(":", 1)[1])
    await repo.ensure_user(callback.from_user.id, callback.from_user.username)
    await repo.update_user_settings(callback.from_user.id, tz_offset_min=minutes)
    _awaiting_manual_tz.pop(callback.from_user.id, None)

    await safe_edit(callback, i18n.get("connect-timezone-set", offset=format_offset(minutes, i18n)))
    await callback.answer()


# tg_id -> id of the prompt message to restore on a bad reply. Module-level
# and in-memory, same as admin.py's _awaiting_input — losing it on a restart
# just means asking again, nothing worth persisting to disk for.
_awaiting_manual_tz: dict[int, int] = {}


@router.callback_query(F.data == TZ_MANUAL)
async def timezone_manual_prompt(callback: CallbackQuery, i18n: I18nContext) -> None:
    if isinstance(callback.message, Message):
        _awaiting_manual_tz[callback.from_user.id] = callback.message.message_id
    await safe_edit(callback, i18n.get("connect-timezone-manual-hint"))
    await callback.answer()


# A mandatory sign, unlike parse_utc_offset itself: admin.py's own numeric
# flow (rare threshold, row limits) accepts bare unsigned numbers in the same
# private chat, and a bare "3" must not be ambiguous between the two.
@router.message(
    F.chat.type == ChatType.PRIVATE, F.text.regexp(r"(?i)^(?:utc)?\s*[+-]\d{1,2}(?::[0-5]\d)?$")
)
async def timezone_manual_input(message: Message, repo: Repo, i18n: I18nContext) -> None:
    assert message.from_user is not None and message.text is not None
    prompt_id = _awaiting_manual_tz.pop(message.from_user.id, None)
    if prompt_id is None:
        return  # a stray signed number from someone not in this flow — ignore

    minutes = parse_utc_offset(message.text)
    if minutes is None:  # out of −12..+14 range — the regex alone can't catch that
        _awaiting_manual_tz[message.from_user.id] = prompt_id
        hint = i18n.get("connect-timezone-manual-hint")
        await message.answer(i18n.get("connect-timezone-manual-invalid", hint=hint))
        return

    await repo.ensure_user(message.from_user.id, message.from_user.username)
    await repo.update_user_settings(message.from_user.id, tz_offset_min=minutes)
    await message.answer(i18n.get("connect-timezone-set", offset=format_offset(minutes, i18n)))


async def _greet(
    message: Message,
    repo: Repo,
    connect: ConnectService,
    bot: Bot,
    i18n: I18nContext,
    settings: Settings,
) -> None:
    del repo, connect, bot
    await send_open_app(message, settings, i18n)


async def _send_login_link(
    message: Message,
    connect: ConnectService,
    i18n: I18nContext,
    *,
    origin_chat_id: int | None = None,
) -> None:
    url = connect.start_login(message.chat.id, origin_chat_id=origin_chat_id)
    await message.answer(
        i18n.get("connect-login-button-hint"),
        reply_markup=connect_keyboard(url, i18n),
    )


def _parse_connect_payload(args: str) -> tuple[bool, int | None]:
    """`?start=connect` from a private chat, or `?start=connect<chat_id>` from
    the group hub keyboard (SPEC 6.3) — (is it a connect payload, which
    group, if any)."""
    if args == "connect":
        return True, None
    if args.startswith("connect"):
        try:
            return True, int(args.removeprefix("connect"))
        except ValueError:
            return False, None
    return False, None


def _username(message: Message) -> str | None:
    return message.from_user.username if message.from_user else None
