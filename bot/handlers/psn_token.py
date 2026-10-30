"""A player's own PSN token in the bot (#233): its screen behind the PSN
screen's «🔑 Токен» button, pasting it, removing it, and linking a new PSN
account by its token. Routing and actions only; the screens are
`views/psn_token.py`, the rules `services/psn/personal.py`.

The message carrying a token is deleted at once, and the result is drawn in
place of the prompt it answered (a step of the account flow edits the
message it came from, CLAUDE.md "Private chat").
"""

from __future__ import annotations

import contextlib
import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject, User
from aiogram_i18n import I18nContext

from bot.constants import MAX_PSN_ACCOUNTS, Platform
from bot.db.repo import Repo
from bot.handlers import awaiting
from bot.handlers.delivery import safe_edit
from bot.i18n import StaticI18nContext
from bot.poller.psn_fetcher import PsnFetcher
from bot.services.naming import link_nickname
from bot.services.psn.auth import STATUS_NOT_CONFIGURED, PsnAuth
from bot.services.psn.personal import PsnTokenError
from bot.views import Screen
from bot.views.panel import render_account_menu, render_panel
from bot.views.psn_token import (
    keyboard,
    render_delete_confirm,
    render_deleted,
    render_input,
    render_result,
    render_steps,
    render_token,
)

log = logging.getLogger(__name__)

router = Router(name="psn_token")

# What `awaiting` holds while a token is expected: this prefix, then the
# account it is for, or "new" for linking an account by its token.
EXPECT = "psntoken:"

# tg_id -> (chat_id, message_id) of the prompt a pasted token answers, so the
# result replaces it. In memory, like `awaiting`: a restart only means asking again.
_prompts: dict[int, tuple[int, int]] = {}


class AwaitingPsnToken(BaseFilter):
    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        if user is None:
            return False
        expected = awaiting.expected(user.id) or ""
        text = getattr(event, "text", None) or ""
        return expected.startswith(EXPECT) and not text.lstrip().startswith("/")


async def _show(callback: CallbackQuery, screen: Screen) -> None:
    await safe_edit(callback, screen.text, screen.keyboard, parse_mode=ParseMode.HTML)
    await callback.answer()


async def _name(repo: Repo, person_id: int, account_id: str) -> str | None:
    for link in await repo.platform_links_for(person_id, Platform.PSN):
        if link.external_id == account_id:
            return link_nickname(link)
    return None


async def _back_to_psn(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    screen = await render_account_menu(
        repo, callback.from_user.id, Platform.PSN, locale=i18n.locale
    ) or await render_panel(repo, callback.from_user.id, locale=i18n.locale)
    await _show(callback, screen)


@router.callback_query(F.data == "psn:add")
async def psn_add(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    """ "Link another PSN account" (#10): by nickname or by token (#233)."""
    awaiting.clear(callback.from_user.id)
    links = await repo.platform_links_for(await repo.person_id(callback.from_user.id), Platform.PSN)
    if len(links) >= MAX_PSN_ACCOUNTS:
        await callback.answer(i18n.get("psn-accounts-full", max=MAX_PSN_ACCOUNTS), show_alert=True)
        return
    await _show(
        callback,
        Screen(
            i18n.get("psn-add-choice", count=len(links) + 1, max=MAX_PSN_ACCOUNTS),
            keyboard(
                [(i18n.get("psn-add-by-nick"), "psn:addnick")],
                [(i18n.get("psn-add-by-token"), "psntok:steps:new")],
                [(i18n.get("psn-token-back"), "panel:acc:psn")],
            ),
        ),
    )


@router.callback_query(F.data.startswith("psntok:steps:"))
async def token_steps(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    account_id = callback.data.removeprefix("psntok:steps:")
    if account_id == "new":
        await _show(callback, render_steps(None, None, locale=i18n.locale))
        return
    person = await repo.person_id(callback.from_user.id)
    name = await _name(repo, person, account_id)
    if name is None:
        await _back_to_psn(callback, repo, i18n)
        return
    await _show(callback, render_steps(name, account_id, locale=i18n.locale))


@router.callback_query(F.data.startswith("psntok:in:"))
async def token_input(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    account_id = callback.data.removeprefix("psntok:in:")
    name = None
    if account_id != "new":
        name = await _name(repo, await repo.person_id(callback.from_user.id), account_id)
        if name is None:
            await _back_to_psn(callback, repo, i18n)
            return
    awaiting.expect(callback.from_user.id, EXPECT + account_id)
    if isinstance(callback.message, Message):
        _prompts[callback.from_user.id] = (callback.message.chat.id, callback.message.message_id)
    await _show(
        callback,
        render_input(name, None if account_id == "new" else account_id, locale=i18n.locale),
    )


@router.callback_query(F.data.startswith("psntok:del:"))
async def token_delete(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    account_id = callback.data.removeprefix("psntok:del:")
    name = await _name(repo, await repo.person_id(callback.from_user.id), account_id)
    if name is None:
        await _back_to_psn(callback, repo, i18n)
        return
    await _show(callback, render_delete_confirm(name, account_id, locale=i18n.locale))


@router.callback_query(F.data.startswith("psntok:dely:"))
async def token_delete_confirmed(
    callback: CallbackQuery, repo: Repo, psn_auth: PsnAuth, i18n: I18nContext
) -> None:
    account_id = callback.data.removeprefix("psntok:dely:")
    if psn_auth.personal is not None:
        await psn_auth.personal.remove(await repo.person_id(callback.from_user.id), account_id)
    await _show(callback, render_deleted(locale=i18n.locale))


@router.callback_query(F.data.startswith("psntok:"))
async def token_screen(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    """One account's token (the PSN screen's «🔑 Токен» button). Registered
    after the longer prefixes above, which it would otherwise swallow."""
    awaiting.clear(callback.from_user.id)
    account_id = callback.data.removeprefix("psntok:")
    screen = await render_token(
        repo, await repo.person_id(callback.from_user.id), account_id, locale=i18n.locale
    )
    if screen is None:
        await _back_to_psn(callback, repo, i18n)
        return
    await _show(callback, screen)


async def _answer(bot: Bot, tg_id: int, screen: Screen) -> None:
    """The result in place of the prompt, else as a message of its own."""
    prompt = _prompts.pop(tg_id, None)
    if prompt is not None:
        with contextlib.suppress(Exception):
            await bot.edit_message_text(
                screen.text,
                chat_id=prompt[0],
                message_id=prompt[1],
                reply_markup=screen.keyboard,
                parse_mode=ParseMode.HTML,
            )
            return
    await bot.send_message(
        tg_id, screen.text, reply_markup=screen.keyboard, parse_mode=ParseMode.HTML
    )


@router.message(F.chat.type == ChatType.PRIVATE, AwaitingPsnToken())
async def token_pasted(
    message: Message,
    repo: Repo,
    psn_auth: PsnAuth,
    psn_fetcher: PsnFetcher,
    bot: Bot,
    i18n: I18nContext,
) -> None:
    tg_id = message.from_user.id  # type: ignore[union-attr]
    target = (awaiting.expected(tg_id) or "").removeprefix(EXPECT)
    awaiting.clear(tg_id)
    raw = message.text or ""
    # Out of the chat before anything else: it is a key to a whole account.
    with contextlib.suppress(Exception):
        await message.delete()
    if psn_auth.personal is None:
        return
    if target == "new":
        await link_by_token(bot, repo, psn_auth, psn_fetcher, message.from_user, raw, i18n)
        return
    person = await repo.person_id(tg_id)
    name = await _name(repo, person, target)
    try:
        await psn_auth.personal.add(person, target, raw)
    except PsnTokenError as exc:
        await _answer(
            bot,
            tg_id,
            render_result(
                exc.code, name=name, account_id=target, other=exc.online_id, locale=i18n.locale
            ),
        )
        return
    await _answer(bot, tg_id, render_result("ok", name=name, account_id=target, locale=i18n.locale))


async def link_by_token(
    bot: Bot,
    repo: Repo,
    psn_auth: PsnAuth,
    psn_fetcher: PsnFetcher,
    user: User | None,
    raw: str,
    i18n: I18nContext | StaticI18nContext,
    *,
    confirmed: bool = False,
) -> None:
    """Links the PSN account a token opens, then keeps the token for it (#233).
    The account's trophies may be hidden: its own token reads them."""
    from bot.handlers.psn import NOT_CONFIGURED_KEY, link_profile

    if user is None or psn_auth.personal is None:
        return
    if await psn_auth.status() == STATUS_NOT_CONFIGURED:
        # No shared token: the poller reads nobody, a linked account included.
        await bot.send_message(user.id, i18n.get(NOT_CONFIGURED_KEY))
        return
    personal = psn_auth.personal
    try:
        npsso, profile = await personal.identify(raw, ("tg", user.id))
    except PsnTokenError as exc:
        await _answer(
            bot, user.id, render_result(exc.code, name=None, account_id=None, locale=i18n.locale)
        )
        return

    async def keep(person_id: int) -> None:
        await personal.keep(person_id, profile.account_id, npsso)

    _prompts.pop(user.id, None)
    linked = await link_profile(
        bot,
        repo,
        psn_fetcher,
        user.id,
        user.username,
        profile,
        i18n,
        confirmed=confirmed,
        pending=("token", npsso),
        keep_token=keep,
    )
    if linked:
        log.info("psn account %s linked by its own token", profile.account_id)
