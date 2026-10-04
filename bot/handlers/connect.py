"""/start, /connect_xbox, /disconnect_xbox and the timezone picker. UI only (CLAUDE.md)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from html import escape as html_escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatType, ParseMode
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
from bot.services.naming import xbox_nickname
from bot.services.notify import AdminNotifier
from bot.services.psn.auth import PsnAuth
from bot.services.steam.auth import SteamAuth
from bot.util import parse_utc_offset
from bot.views.keyboards import (
    PANEL_TZ,
    TZ_MANUAL,
    TZ_MORE,
    TZ_PICK,
    TZ_SET,
    TZ_SKIP,
    back_to_panel_button,
    buttons,
    connect_keyboard,
    deep_link_keyboard,
    format_offset,
    onboarding_keyboard,
    panel_button,
    timezone_keyboard,
)
from bot.views.panel import render_panel

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
        user = await repo.get_user(await repo.person_id(person_id))
        if user is not None and user.xuid:
            await message.answer(
                i18n.get("connect-xbox-already-connected", name=_xbox_name(user)),
                reply_markup=buttons(
                    InlineKeyboardButton(
                        text=i18n.get("kb-open-xbox"), callback_data="panel:acc:xbox"
                    ),
                    panel_button(i18n),
                ),
                parse_mode=ParseMode.HTML,
            )
            return
        await _send_login_link(message, connect, repo, i18n, origin_chat_id=origin_chat_id)
        return
    await _greet(message, repo, connect, bot, i18n, settings, person_id)


@router.message(CommandStart(), F.chat.type != ChatType.PRIVATE)
async def start_in_group(message: Message, bot: Bot, i18n: I18nContext) -> None:
    await _redirect_to_dm(message, bot, i18n.get("connect-xbox-group-redirect"), i18n)


@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
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
    await _greet(message, repo, connect, bot, i18n, settings, person_id)


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
    user = await repo.get_user(await repo.person_id(person_id))
    if user is not None and user.xuid:
        await message.answer(
            i18n.get("connect-xbox-already-connected-relogin", name=_xbox_name(user)),
            reply_markup=buttons(
                InlineKeyboardButton(
                    text=i18n.get("kb-unlink-xbox"), callback_data="panel:disconnect"
                ),
                panel_button(i18n),
            ),
            parse_mode=ParseMode.HTML,
        )
        return
    await _send_login_link(message, connect, repo, i18n)


@router.message(Command("disconnect_xbox"), F.chat.type == ChatType.PRIVATE)
async def disconnect_command(message: Message, repo: Repo, i18n: I18nContext) -> None:
    person_id = _person_id(message)
    if person_id is None:
        return
    user = await repo.get_user(await repo.person_id(person_id))
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
    user = await repo.get_user(await repo.person_id(tg_id))
    gamertag = (user.gamertag if user else None) or f"id{tg_id}"
    if user is not None and user.xuid:
        await repo.delete_presence_state(user.xuid)
    await repo.delete_token(await repo.person_id(tg_id))
    await repo.delete_subscriptions_of_user(await repo.person_id(tg_id))
    await repo.unlink_xbox_account(await repo.person_id(tg_id))
    await notifier.user_disconnected(tg_id, gamertag, "disconnect-command")

    # Found while refactoring (2026-09-05): none of the edits in this file
    # tolerated a failed edit, unlike panel.py/steam.py's own — now they do.
    await safe_edit(
        callback,
        i18n.get("connect-disconnected", revoke_url=REVOKE_URL),
        buttons(
            InlineKeyboardButton(text=i18n.get("kb-connect-xbox-again"), callback_data="relogin"),
            back_to_panel_button(i18n),
        ),
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data == "relogin")
async def relogin(callback: CallbackQuery, connect: ConnectService, i18n: I18nContext) -> None:
    """Button from the "access expired" reminder (SPEC 5.1.1), the panel's
    connect and reconnect buttons, and the steps after unlinking: the login
    link in place, with a way back (owner, 2026-09-30)."""
    url = connect.start_login(callback.from_user.id)
    markup = connect_keyboard(url, i18n)
    markup.inline_keyboard.append([back_to_panel_button(i18n)])
    await safe_edit(callback, i18n.get("connect-relogin-prompt"), markup)
    await callback.answer()


@router.callback_query(F.data == "optout")
async def optout(
    callback: CallbackQuery, repo: Repo, notifier: AdminNotifier, i18n: I18nContext
) -> None:
    """Left on purpose: subscriptions go, history stays, reminders stop."""
    tg_id = callback.from_user.id
    user = await repo.get_user(await repo.person_id(tg_id))
    await repo.set_token_status(await repo.person_id(tg_id), TokenStatus.REVOKED)
    await repo.delete_subscriptions_of_user(await repo.person_id(tg_id))
    await notifier.user_disconnected(
        tg_id, (user.gamertag if user else None) or f"id{tg_id}", "disconnect-button"
    )
    await safe_edit(
        callback,
        i18n.get("connect-optout-done"),
        buttons(
            InlineKeyboardButton(text=i18n.get("kb-relogin-xbox"), callback_data="relogin"),
            panel_button(i18n),
        ),
    )
    await callback.answer()


def _in_panel(data: str | None) -> bool:
    return bool(data) and data.startswith(f"{PANEL_TZ}:")  # type: ignore[union-attr]


def _tz_prompt(i18n: I18nContext, in_panel: bool) -> str:
    return i18n.get("panel-timezone-prompt" if in_panel else "connect-timezone-prompt")


@router.callback_query(F.data.in_({TZ_MORE, f"{PANEL_TZ}:more"}))
async def timezone_full_list(callback: CallbackQuery, i18n: I18nContext) -> None:
    in_panel = _in_panel(callback.data)
    await safe_edit(
        callback, _tz_prompt(i18n, in_panel), timezone_keyboard(i18n, full=True, in_panel=in_panel)
    )
    await callback.answer()


@router.callback_query(F.data == TZ_PICK)
async def timezone_pick_again(callback: CallbackQuery, i18n: I18nContext) -> None:
    await safe_edit(callback, i18n.get("connect-timezone-prompt"), timezone_keyboard(i18n))
    await callback.answer()


@router.callback_query(F.data == TZ_SKIP)
async def timezone_skip(callback: CallbackQuery, i18n: I18nContext) -> None:
    await safe_edit(
        callback,
        i18n.get("connect-timezone-skip-done"),
        buttons(
            InlineKeyboardButton(text=i18n.get("kb-tz-pick"), callback_data=TZ_PICK),
            panel_button(i18n),
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{TZ_SET}:") | F.data.startswith(f"{PANEL_TZ}:set:"))
async def timezone_set(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    minutes = int(callback.data.rsplit(":", 1)[1])
    await repo.ensure_user(callback.from_user.id, callback.from_user.username)
    await repo.update_user_settings(
        await repo.person_id(callback.from_user.id), tz_offset_min=minutes
    )
    _awaiting_manual_tz.pop(callback.from_user.id, None)
    offset = format_offset(minutes, i18n)

    if _in_panel(callback.data):
        # Back to the panel it was opened from; the new value is on its
        # button, and a toast says it took.
        screen = await render_panel(repo, callback.from_user.id, locale=i18n.locale)
        await safe_edit(callback, screen.text, screen.keyboard, parse_mode=ParseMode.HTML)
        await callback.answer(i18n.get("panel-timezone-toast", offset=offset))
        return
    await safe_edit(
        callback, i18n.get("connect-timezone-set", offset=offset), buttons(panel_button(i18n))
    )
    await callback.answer()


# tg_id -> (id of the prompt message, opened from /panel?) — the prompt is
# where the answer lands. Module-level and in-memory, same as admin.py's
# _awaiting_input — losing it on a restart just means asking again.
_awaiting_manual_tz: dict[int, tuple[int, bool]] = {}


@router.callback_query(F.data.in_({TZ_MANUAL, f"{PANEL_TZ}:manual"}))
async def timezone_manual_prompt(callback: CallbackQuery, i18n: I18nContext) -> None:
    in_panel = _in_panel(callback.data)
    if isinstance(callback.message, Message):
        _awaiting_manual_tz[callback.from_user.id] = (callback.message.message_id, in_panel)
    await safe_edit(
        callback,
        i18n.get("connect-timezone-manual-hint"),
        buttons(back_to_panel_button(i18n, back=True)) if in_panel else None,
    )
    await callback.answer()


# A mandatory sign, unlike parse_utc_offset itself: admin.py's own numeric
# flow (rare threshold, row limits) accepts bare unsigned numbers in the same
# private chat, and a bare "3" must not be ambiguous between the two.
@router.message(
    F.chat.type == ChatType.PRIVATE, F.text.regexp(r"(?i)^(?:utc)?\s*[+-]\d{1,2}(?::[0-5]\d)?$")
)
async def timezone_manual_input(message: Message, repo: Repo, bot: Bot, i18n: I18nContext) -> None:
    assert message.from_user is not None and message.text is not None
    waiting = _awaiting_manual_tz.pop(message.from_user.id, None)
    if waiting is None:
        return  # a stray signed number from someone not in this flow — ignore
    prompt_id, in_panel = waiting

    minutes = parse_utc_offset(message.text)
    if minutes is None:  # out of −12..+14 range — the regex alone can't catch that
        _awaiting_manual_tz[message.from_user.id] = waiting
        hint = i18n.get("connect-timezone-manual-hint")
        await message.answer(i18n.get("connect-timezone-manual-invalid", hint=hint))
        return

    await repo.ensure_user(message.from_user.id, message.from_user.username)
    await repo.update_user_settings(
        await repo.person_id(message.from_user.id), tz_offset_min=minutes
    )
    offset = format_offset(minutes, i18n)
    # The answer lands in the prompt it was asked in (owner, 2026-09-30): the
    # panel again, or the "set" line with its way on.
    if in_panel:
        screen = await render_panel(repo, message.from_user.id, locale=i18n.locale)
        text, markup = screen.text, screen.keyboard
    else:
        text = i18n.get("connect-timezone-set", offset=offset)
        markup = buttons(panel_button(i18n))
    try:
        await bot.edit_message_text(
            text,
            chat_id=message.chat.id,
            message_id=prompt_id,
            reply_markup=markup,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        await message.answer(text, reply_markup=markup, parse_mode=ParseMode.HTML)


async def _greet(
    message: Message,
    repo: Repo,
    connect: ConnectService,
    bot: Bot,
    i18n: I18nContext,
    settings: Settings,
    person_id: int | None = None,
) -> None:
    """Already connected on *any* platform -> straight to the panel;
    otherwise greet and offer all three (#53).
    """
    pid = person_id if person_id is not None else _person_id(message)
    if pid:
        user = await repo.get_user(await repo.person_id(pid))
        links = await repo.platform_links_of(await repo.person_id(pid))
        if (user is not None and user.xuid) or links:
            await send_panel(bot, repo, pid, i18n)
            return
    in_private = message.chat.type == ChatType.PRIVATE
    await message.answer(i18n.get("connect-greeting-multi"))
    await message.answer(
        i18n.get("connect-pick-platform"),
        reply_markup=onboarding_keyboard(
            connect.start_login(pid or 0),
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


def _xbox_name(user: object) -> str:
    return html_escape(
        xbox_nickname(
            gamertag_modern=getattr(user, "gamertag_modern", None),
            gamertag=getattr(user, "gamertag", None),
            xuid=getattr(user, "xuid", None),
        )
    )
