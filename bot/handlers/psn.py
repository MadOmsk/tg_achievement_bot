"""`/connect_psn`, `/disconnect_psn` (SPEC 9, M-PSN-1) — symmetric to
steam.py, minus the link-parsing: PSN has no profile URL a person would ever
paste, only an Online ID, and psnawp_api resolves that directly to an
account_id (no separate "vanity name" lookup step the way Steam needs one).

Private chat only, same reasoning as connect_steam/connect_xbox — this is
personal, not a group setting (SPEC 6.3).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)

from bot.db.repo import Repo
from bot.handlers.keyboards import deep_link_keyboard, safe_edit
from bot.services.psn.auth import STATUS_NOT_CONFIGURED, PsnAuth, PsnNotConfiguredError
from bot.services.psn.client import (
    PsnApiError,
    PsnTokenDeadError,
    is_trophy_visible,
    resolve_profile,
)

log = logging.getLogger(__name__)

router = Router(name="psn")

NOT_CONFIGURED = "Подключение PSN пока не настроено — обратитесь к администратору."
GROUP_HINT_TTL = 30
LINK_PROMPT = (
    "Пришли свой PSN Online ID (ник) — подключу по нему.\n\n"
    "⚠️ Приватность трофеев должна быть открыта, иначе не смогу их читать: "
    "в приложении PS App → Настройки → Приватность → «Уровень трофеев и коллекция игр» → "
    "«Все пользователи»."
)

# Same in-memory "next plain message is the answer" pattern as steam.py's own
# _awaiting_link — nothing here needs to survive a restart.
_awaiting_link: set[int] = set()


class AwaitingPsnLink(BaseFilter):
    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        return user is not None and user.id in _awaiting_link


async def _redirect_to_dm(
    message: Message, bot: Bot, hint_text: str, *, payload: str | None = None
) -> None:
    me = await bot.me()
    url = f"https://t.me/{me.username}" + (f"?start={payload}" if payload else "")
    hint = await message.answer(hint_text, reply_markup=deep_link_keyboard(url))
    asyncio.create_task(_delete_later(bot, hint.chat.id, hint.message_id))  # noqa: RUF006


async def _delete_later(bot: Bot, chat_id: int, message_id: int) -> None:
    await asyncio.sleep(GROUP_HINT_TTL)
    with contextlib.suppress(Exception):
        await bot.delete_message(chat_id, message_id)


@router.message(Command("connect_psn"), F.chat.type != ChatType.PRIVATE)
async def connect_psn_in_group(message: Message, bot: Bot) -> None:
    await _redirect_to_dm(
        message, bot, "Напиши мне в личку — подключим PSN там.", payload="connectpsn"
    )


@router.message(Command("disconnect_psn"), F.chat.type != ChatType.PRIVATE)
async def disconnect_psn_in_group(message: Message, bot: Bot) -> None:
    await _redirect_to_dm(message, bot, "Эта команда — в личке.")


async def prompt_for_link(bot: Bot, repo: Repo, psn_auth: PsnAuth, tg_id: int) -> None:
    """The shared "now send me your Online ID" step — bare /connect_psn, the
    panel button and the deep link all go through this one place."""
    if await psn_auth.status() == STATUS_NOT_CONFIGURED:
        await bot.send_message(tg_id, NOT_CONFIGURED)
        return
    link = await repo.get_platform_link(tg_id, "psn")
    if link is not None:
        await bot.send_message(tg_id, f"PSN уже подключён: {link.display_name}.")
        return
    _awaiting_link.add(tg_id)
    await bot.send_message(tg_id, LINK_PROMPT)


@router.callback_query(F.data == "psn:connect")
async def psn_connect_button(
    callback: CallbackQuery, repo: Repo, psn_auth: PsnAuth, bot: Bot
) -> None:
    await prompt_for_link(bot, repo, psn_auth, callback.from_user.id)
    await callback.answer()


@router.message(Command("connect_psn"), F.chat.type == ChatType.PRIVATE)
async def connect_psn(
    message: Message, repo: Repo, psn_auth: PsnAuth, command: CommandObject, bot: Bot
) -> None:
    raw = (command.args or "").strip()
    if not raw:
        await prompt_for_link(bot, repo, psn_auth, message.chat.id)
        return
    username = message.from_user.username if message.from_user else None
    await _connect(bot, repo, psn_auth, message.chat.id, username, raw)


@router.message(F.chat.type == ChatType.PRIVATE, AwaitingPsnLink())
async def psn_link_provided(
    message: Message, repo: Repo, psn_auth: PsnAuth, bot: Bot
) -> None:
    _awaiting_link.discard(message.from_user.id)
    username = message.from_user.username if message.from_user else None
    await _connect(
        bot, repo, psn_auth, message.chat.id, username, (message.text or "").strip()
    )


async def _connect(
    bot: Bot,
    repo: Repo,
    psn_auth: PsnAuth,
    tg_id: int,
    username: str | None,
    raw: str,
) -> None:
    if await psn_auth.status() == STATUS_NOT_CONFIGURED:
        await bot.send_message(tg_id, NOT_CONFIGURED)
        return
    if not raw:
        await prompt_for_link(bot, repo, psn_auth, tg_id)
        return

    try:
        client = await psn_auth.get_client()
        profile = await resolve_profile(client, raw)
    except PsnNotConfiguredError:
        await bot.send_message(tg_id, NOT_CONFIGURED)
        return
    except PsnTokenDeadError:
        log.warning("connect_psn: service token dead, tg_id=%s", tg_id)
        await bot.send_message(
            tg_id, "PSN сейчас недоступен — сервисный вход устарел, сообщите администратору."
        )
        return
    except PsnApiError as exc:
        log.info("connect_psn: could not resolve tg_id=%s raw=%r: %s", tg_id, raw, exc)
        await bot.send_message(
            tg_id, f"Не нашёл такой PSN Online ID: {raw!r}. Проверь написание и попробуй снова."
        )
        return

    if not await is_trophy_visible(client, profile.account_id):
        log.info(
            "connect_psn: private profile for tg_id=%s account_id=%s", tg_id, profile.account_id
        )
        await bot.send_message(
            tg_id,
            "Профиль есть, но трофеи скрыты — я не смогу их читать. Открой приватность и "
            "попробуй снова: PS App → Настройки → Приватность → «Уровень трофеев и коллекция "
            "игр» → «Все пользователи».",
        )
        return

    await repo.ensure_user(tg_id, username)
    await repo.link_platform_account(tg_id, "psn", profile.account_id, profile.online_id)
    log.info("connect_psn: tg_id=%s linked account_id=%s", tg_id, profile.account_id)
    await bot.send_message(tg_id, f"Подключил PSN: {profile.online_id}.")


def _disconnect_prompt_keyboard(*, from_panel: bool) -> InlineKeyboardMarkup:
    cancel_data = "panel:psndisconnect:no" if from_panel else "psn:disconnect:no"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, отключить", callback_data="psn:disconnect:yes")],
            [InlineKeyboardButton(text="Отмена", callback_data=cancel_data)],
        ]
    )


@router.message(Command("disconnect_psn"), F.chat.type == ChatType.PRIVATE)
async def disconnect_psn_command(message: Message, repo: Repo) -> None:
    link = await repo.get_platform_link(message.chat.id, "psn")
    if link is None:
        await message.answer("PSN и так не подключён.")
        return
    await message.answer(
        f"Отключить PSN ({link.display_name})?",
        reply_markup=_disconnect_prompt_keyboard(from_panel=False),
    )


@router.callback_query(F.data == "psn:disconnectprompt")
async def psn_disconnect_button(callback: CallbackQuery, repo: Repo) -> None:
    link = await repo.get_platform_link(callback.from_user.id, "psn")
    if link is None:
        await callback.answer("PSN и так не подключён.", show_alert=True)
        return
    await safe_edit(
        callback,
        f"Отключить PSN ({link.display_name})?",
        _disconnect_prompt_keyboard(from_panel=True),
    )
    await callback.answer()


@router.callback_query(F.data == "psn:disconnect:no")
async def disconnect_psn_cancel(callback: CallbackQuery) -> None:
    if isinstance(callback.message, Message):
        with contextlib.suppress(Exception):
            await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data == "psn:disconnect:yes")
async def disconnect_psn_confirm(callback: CallbackQuery, repo: Repo) -> None:
    await repo.unlink_platform_account(callback.from_user.id, "psn")
    await safe_edit(callback, "Отключил PSN. Вернуться можно в любой момент.")
    await callback.answer()
