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
from aiogram_i18n import I18nContext

from bot.constants import Platform
from bot.db.repo import Repo
from bot.handlers.keyboards import deep_link_keyboard, safe_edit
from bot.i18n import StaticI18nContext, static_i18n
from bot.poller.psn_fetcher import PsnFetcher
from bot.services.psn.auth import STATUS_NOT_CONFIGURED, PsnAuth, PsnNotConfiguredError
from bot.services.psn.client import (
    PsnApiError,
    PsnTokenDeadError,
    is_trophy_visible,
    resolve_profile,
)

log = logging.getLogger(__name__)

router = Router(name="psn")

NOT_CONFIGURED_KEY = "psn-not-configured"
GROUP_HINT_TTL = 30

# Same in-memory "next plain message is the answer" pattern as steam.py's own
# _awaiting_link — nothing here needs to survive a restart.
_awaiting_link: set[int] = set()


class AwaitingPsnLink(BaseFilter):
    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        return user is not None and user.id in _awaiting_link


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


@router.message(Command("connect_psn"), F.chat.type != ChatType.PRIVATE)
async def connect_psn_in_group(message: Message, bot: Bot, i18n: I18nContext) -> None:
    await _redirect_to_dm(
        message, bot, i18n.get("psn-connect-group-redirect"), i18n, payload="connectpsn"
    )


@router.message(Command("disconnect_psn"), F.chat.type != ChatType.PRIVATE)
async def disconnect_psn_in_group(message: Message, bot: Bot, i18n: I18nContext) -> None:
    await _redirect_to_dm(message, bot, i18n.get("psn-private-only"), i18n)


async def prompt_for_link(
    bot: Bot,
    repo: Repo,
    psn_auth: PsnAuth,
    tg_id: int,
    i18n: I18nContext | StaticI18nContext | None = None,
) -> None:
    """The shared "now send me your Online ID" step — bare /connect_psn, the
    panel button and the deep link all go through this one place."""
    i18n = i18n or static_i18n("psn")
    if await psn_auth.status() == STATUS_NOT_CONFIGURED:
        await bot.send_message(tg_id, i18n.get(NOT_CONFIGURED_KEY))
        return
    link = await repo.get_platform_link(tg_id, Platform.PSN)
    if link is not None:
        await bot.send_message(tg_id, i18n.get("psn-already-connected", name=link.display_name))
        return
    _awaiting_link.add(tg_id)
    await bot.send_message(tg_id, i18n.get("psn-link-prompt"))


@router.callback_query(F.data == "psn:connect")
async def psn_connect_button(
    callback: CallbackQuery, repo: Repo, psn_auth: PsnAuth, bot: Bot, i18n: I18nContext
) -> None:
    await prompt_for_link(bot, repo, psn_auth, callback.from_user.id, i18n)
    await callback.answer()


@router.message(Command("connect_psn"), F.chat.type == ChatType.PRIVATE)
async def connect_psn(
    message: Message,
    repo: Repo,
    psn_auth: PsnAuth,
    psn_fetcher: PsnFetcher,
    command: CommandObject,
    bot: Bot,
    i18n: I18nContext,
) -> None:
    raw = (command.args or "").strip()
    if not raw:
        await prompt_for_link(bot, repo, psn_auth, message.chat.id, i18n)
        return
    username = message.from_user.username if message.from_user else None
    await _connect(bot, repo, psn_auth, psn_fetcher, message.chat.id, username, raw, i18n)


@router.message(F.chat.type == ChatType.PRIVATE, AwaitingPsnLink())
async def psn_link_provided(
    message: Message,
    repo: Repo,
    psn_auth: PsnAuth,
    psn_fetcher: PsnFetcher,
    bot: Bot,
    i18n: I18nContext,
) -> None:
    _awaiting_link.discard(message.from_user.id)
    username = message.from_user.username if message.from_user else None
    await _connect(
        bot,
        repo,
        psn_auth,
        psn_fetcher,
        message.chat.id,
        username,
        (message.text or "").strip(),
        i18n,
    )


async def _connect(
    bot: Bot,
    repo: Repo,
    psn_auth: PsnAuth,
    psn_fetcher: PsnFetcher,
    tg_id: int,
    username: str | None,
    raw: str,
    i18n: I18nContext | StaticI18nContext | None = None,
) -> None:
    i18n = i18n or static_i18n("psn")
    if await psn_auth.status() == STATUS_NOT_CONFIGURED:
        await bot.send_message(tg_id, i18n.get(NOT_CONFIGURED_KEY))
        return
    if not raw:
        await prompt_for_link(bot, repo, psn_auth, tg_id, i18n)
        return

    try:
        client = await psn_auth.get_client()
        profile = await resolve_profile(client, raw)
    except PsnNotConfiguredError:
        await bot.send_message(tg_id, i18n.get(NOT_CONFIGURED_KEY))
        return
    except PsnTokenDeadError:
        log.warning("connect_psn: service token dead, tg_id=%s", tg_id)
        await bot.send_message(tg_id, i18n.get("psn-service-token-dead"))
        return
    except PsnApiError as exc:
        log.info("connect_psn: could not resolve tg_id=%s raw=%r: %s", tg_id, raw, exc)
        await bot.send_message(tg_id, i18n.get("psn-profile-not-found", raw=raw))
        return

    if not await is_trophy_visible(client, profile.account_id):
        log.info(
            "connect_psn: private profile for tg_id=%s account_id=%s", tg_id, profile.account_id
        )
        await bot.send_message(tg_id, i18n.get("psn-profile-private"))
        return

    await repo.ensure_user(tg_id, username)
    await repo.link_platform_account(tg_id, Platform.PSN, profile.account_id, profile.online_id)
    log.info("connect_psn: tg_id=%s linked account_id=%s", tg_id, profile.account_id)
    await bot.send_message(tg_id, i18n.get("psn-connected", name=profile.online_id))

    # Backgrounded (SPEC 9, M-Steam-2d's own reasoning applies here too) —
    # the reply above must not wait for it. Run on every link, not just the
    # first (link_platform_account already replaces an existing one) —
    # idempotent (INSERT OR IGNORE) and safe, same as Xbox/Steam's own
    # reconnect handling.
    await bot.send_message(tg_id, i18n.get("psn-backfill-started"))
    asyncio.create_task(  # noqa: RUF006
        _backfill_and_notify(bot, psn_fetcher, tg_id, profile.account_id, i18n)
    )


async def _backfill_and_notify(
    bot: Bot, fetcher: PsnFetcher, tg_id: int, account_id: str, i18n: I18nContext
) -> None:
    try:
        result = await fetcher.backfill(tg_id, account_id)
    except Exception:
        log.exception("psn backfill for tg_id=%s failed", tg_id)
        await bot.send_message(tg_id, i18n.get("psn-backfill-failed"))
        return
    text = i18n.get("psn-backfill-done", count=result.stored)
    if result.private_title_ids:
        # #28: the account passed the connect-time visibility check, but some
        # individual games are still private — say so, with where to fix it,
        # instead of just silently missing those trophies.
        note = i18n.get("psn-backfill-private-note", count=len(result.private_title_ids))
        text += "\n\n" + note
    await bot.send_message(tg_id, text)


def _disconnect_prompt_keyboard(i18n: I18nContext, *, from_panel: bool) -> InlineKeyboardMarkup:
    cancel_data = "panel:psndisconnect:no" if from_panel else "psn:disconnect:no"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("psn-disconnect-confirm-button"),
                    callback_data="psn:disconnect:yes",
                )
            ],
            [InlineKeyboardButton(text=i18n.get("psn-cancel-button"), callback_data=cancel_data)],
        ]
    )


@router.message(Command("disconnect_psn"), F.chat.type == ChatType.PRIVATE)
async def disconnect_psn_command(message: Message, repo: Repo, i18n: I18nContext) -> None:
    link = await repo.get_platform_link(message.chat.id, Platform.PSN)
    if link is None:
        await message.answer(i18n.get("psn-already-disconnected"))
        return
    await message.answer(
        i18n.get("psn-disconnect-prompt", name=link.display_name),
        reply_markup=_disconnect_prompt_keyboard(i18n, from_panel=False),
    )


@router.callback_query(F.data == "psn:disconnectprompt")
async def psn_disconnect_button(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    link = await repo.get_platform_link(callback.from_user.id, Platform.PSN)
    if link is None:
        await callback.answer(i18n.get("psn-already-disconnected"), show_alert=True)
        return
    await safe_edit(
        callback,
        i18n.get("psn-disconnect-prompt", name=link.display_name),
        _disconnect_prompt_keyboard(i18n, from_panel=True),
    )
    await callback.answer()


@router.callback_query(F.data == "psn:disconnect:no")
async def disconnect_psn_cancel(callback: CallbackQuery) -> None:
    if isinstance(callback.message, Message):
        with contextlib.suppress(Exception):
            await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data == "psn:disconnect:yes")
async def disconnect_psn_confirm(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    link = await repo.get_platform_link(callback.from_user.id, Platform.PSN)
    await repo.unlink_platform_account(callback.from_user.id, Platform.PSN)
    if link is not None:
        # Symmetric with Steam's own disconnect (steam.py's
        # delete_steam_presence_state) — a stale poll-state row would
        # otherwise sit there forever for an account no longer linked to
        # anyone (SPEC 9, M-PSN-2).
        await repo.delete_psn_poll_state(link.external_id)
    await safe_edit(callback, i18n.get("psn-disconnected"))
    await callback.answer()
