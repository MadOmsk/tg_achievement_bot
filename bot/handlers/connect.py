"""/start, /connect_xbox, /disconnect_xbox and the timezone picker. UI only (CLAUDE.md)."""

from __future__ import annotations

import asyncio
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
)
from aiogram_i18n import I18nContext

from bot.config import Settings
from bot.constants import TokenStatus
from bot.db.repo import Repo
from bot.handlers.delivery import safe_edit
from bot.handlers.panel import send_panel
from bot.handlers.psn import prompt_for_link as prompt_for_psn_link
from bot.handlers.steam import prompt_for_link
from bot.services.connect import ConnectService
from bot.services.notify import AdminNotifier
from bot.services.psn.auth import PsnAuth
from bot.services.steam.auth import SteamAuth
from bot.util import parse_utc_offset
from bot.views.keyboards import (
    TZ_MANUAL,
    TZ_MORE,
    TZ_SET,
    TZ_SKIP,
    connect_keyboard,
    deep_link_keyboard,
    format_offset,
    onboarding_keyboard,
    timezone_keyboard,
)

log = logging.getLogger(__name__)

router = Router(name="connect")

REVOKE_URL = "https://account.live.com/consent/Manage"
GROUP_HINT_TTL = 15


async def _redirect_to_dm(
    message: Message, bot: Bot, hint_text: str, i18n: I18nContext, *, payload: str | None = None
) -> None:
    me = await bot.me()
    url = f"https://t.me/{me.username}" + (f"?start={payload}" if payload else "")
    hint = await message.answer(hint_text, reply_markup=deep_link_keyboard(url, i18n))
    asyncio.create_task(_delete_later(bot, hint.chat.id, hint.message_id))  # noqa: RUF006


async def _delete_later(bot: Bot, chat_id: int, message_id: int) -> None:
    await asyncio.sleep(GROUP_HINT_TTL)
    with contextlib.suppress(Exception):
        await bot.delete_message(chat_id, message_id)


@router.message(CommandStart(deep_link=True))
async def start_with_payload(
    message: Message,
    command: CommandObject,
    repo: Repo,
    connect: ConnectService,
    settings: Settings,
    psn_auth: PsnAuth,
    steam_auth: SteamAuth,
    bot: Bot,
    i18n: I18nContext,
) -> None:
    """Deep link from a group chat: its buttons send people here (SPEC 6.3)."""
    person_id = _person_id(message)
    if person_id is None:
        return
    await repo.ensure_user(person_id, _username(message))
    if command.args == "panel":
        await send_panel(bot, repo, person_id, i18n)
        return
    if command.args == "connectsteam":
        # Same prompt-and-wait as every other door into this flow
        # (steam.py's prompt_for_link, 2026-09-05 follow-up) — a deep link
        # can't carry the profile URL itself, but landing here now arms the
        # wait too, so there's nothing left to type but the link itself.
        await prompt_for_link(bot, repo, steam_auth, person_id, i18n)
        return
    if command.args == "connectpsn":
        # Same treatment as connectsteam above, for PSN (SPEC 9, M-PSN-1).
        await prompt_for_psn_link(bot, repo, psn_auth, person_id, i18n)
        return
    is_connect, origin_chat_id = _parse_connect_payload(command.args or "")
    if is_connect:
        # Straight to the login link: the person pressed the Xbox connect button in a
        # group and does not need the whole greeting again. If the button
        # carried which group it was pressed in, we auto-subscribe him there
        # once the login actually succeeds (see on_linked in bot/main.py).
        user = await repo.get_user(person_id)
        if user is not None and user.xuid:
            await message.answer(i18n.get("connect-xbox-already-connected"))
            return
        await _send_login_link(message, connect, repo, i18n, origin_chat_id=origin_chat_id)
        return
    await _greet(message, repo, connect, bot, i18n, settings)


@router.message(CommandStart())
async def start(
    message: Message,
    repo: Repo,
    connect: ConnectService,
    bot: Bot,
    i18n: I18nContext,
    settings: Settings,
) -> None:
    person_id = _person_id(message)
    if person_id is None:
        return
    await repo.ensure_user(person_id, _username(message))
    await _greet(message, repo, connect, bot, i18n, settings)


@router.message(Command("connect_xbox"), F.chat.type != ChatType.PRIVATE)
async def connect_xbox_in_group(message: Message, bot: Bot, i18n: I18nContext) -> None:
    await _redirect_to_dm(
        message, bot, i18n.get("connect-xbox-group-redirect"), i18n, payload="connect"
    )


@router.message(Command("disconnect_xbox"), F.chat.type != ChatType.PRIVATE)
async def disconnect_xbox_in_group(message: Message, bot: Bot, i18n: I18nContext) -> None:
    await _redirect_to_dm(message, bot, i18n.get("connect-xbox-private-only"), i18n)


@router.message(Command("connect_xbox"), F.chat.type == ChatType.PRIVATE)
async def connect_command(
    message: Message, repo: Repo, connect: ConnectService, i18n: I18nContext
) -> None:
    person_id = _person_id(message)
    if person_id is None:
        return
    await repo.ensure_user(person_id, _username(message))
    user = await repo.get_user(person_id)
    if user is not None and user.xuid:
        await message.answer(i18n.get("connect-xbox-already-connected-relogin"))
        return
    await _send_login_link(message, connect, repo, i18n)


@router.message(Command("disconnect_xbox"), F.chat.type == ChatType.PRIVATE)
async def disconnect_command(message: Message, repo: Repo, i18n: I18nContext) -> None:
    person_id = _person_id(message)
    if person_id is None:
        return
    user = await repo.get_user(person_id)
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
    """Already connected on *any* platform -> straight to the panel;
    otherwise greet and offer all three (#53).
    """
    person_id = _person_id(message)
    if person_id:
        user = await repo.get_user(person_id)
        links = await repo.platform_links_of(person_id)
        if (user is not None and user.xuid) or links:
            await send_panel(bot, repo, person_id, i18n)
            return
    # The Mini App row is a `web_app` button, which Telegram accepts only in
    # a private chat — anywhere else it answers BUTTON_TYPE_INVALID and the
    # whole message fails to send. `/start` carries no chat-type filter (the
    # one in this file guards the timezone prompt, not this), so it does
    # reach here from a group, and without this guard it would stop
    # answering there entirely rather than simply offering one row fewer.
    in_private = message.chat.type == ChatType.PRIVATE
    await message.answer(i18n.get("connect-greeting-multi"))
    await message.answer(
        i18n.get("connect-pick-platform"),
        reply_markup=onboarding_keyboard(
            connect.start_login(person_id or 0),
            i18n,
            mini_app_url=(settings.mini_app_url or "") if in_private else "",
        ),
    )


async def _send_login_link(
    message: Message,
    connect: ConnectService,
    repo: Repo,
    i18n: I18nContext,
    *,
    origin_chat_id: int | None = None,
) -> None:
    person_id = _person_id(message)
    if person_id is None:
        return
    cooldown = await repo.check_platform_cooldown(person_id, "xbox")
    if cooldown.is_blocked:
        hours = cooldown.remaining_seconds // 3600
        minutes = (cooldown.remaining_seconds % 3600) // 60
        await message.answer(
            i18n.get("platform-cooldown-active", platform="Xbox", hours=hours, minutes=minutes)
        )
        return
    url = connect.start_login(person_id, origin_chat_id=origin_chat_id)
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


def _person_id(message: Message) -> int | None:
    """Whose row this is — the person's id, never the chat's (#66).

    These handlers used to pass `message.chat.id`, which is the same number
    in a DM and a completely different one in a group: `/start` is
    answerable there, so one person running it created a `users` row for the
    *group*. Found on production as tg_id -5246175458, a person who does not
    exist sitting in the table every "who are our people" query reads.
    """
    from_user = getattr(message, "from_user", None)
    return from_user.id if from_user else None


def _username(message: Message) -> str | None:
    from_user = getattr(message, "from_user", None)
    return from_user.username if from_user else None
