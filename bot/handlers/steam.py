"""`/connect_steam`, `/disconnect_steam` (M-Steam-1, TODO.md; backfill —
SPEC 9, M-Steam-2d).

Private chat only, like /connect_xbox and /panel — this is personal, not a group
setting (SPEC 6.3's "настройки в общий чат не попадают никогда" applies the
same way here). Found live: an earlier version filtered group chat out at
the router level with no reply at all — from inside a group that reads as
the bot simply not responding, not as "try this in DM". Redirects instead,
same pattern as /panel in a group (panel.py's panel_in_group).

Steam login flow (Follow-up, 2026-09-05): a person no longer has to retype
the whole command with the link as an argument. Pressing the panel button,
running the bare command, or arriving via the group hub's deep link all
just arm a wait for the *next* plain message and treat that as the link or
nickname (`resolve_steam_id`, services/steam/client.py, already accepts
either). Found live too: someone can just paste a steamcommunity.com link
with no prior command at all — that gets a one-tap confirm instead of
being silently ignored.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re

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

from bot.config import get_settings
from bot.constants import Platform
from bot.db.repo import Repo
from bot.handlers.keyboards import (
    deep_link_keyboard,
    notify_previous_owner,
    safe_edit,
    switch_keyboard,
    switch_prompt,
)
from bot.i18n import StaticI18nContext, static_i18n
from bot.poller.steam_fetcher import SteamFetcher
from bot.services import relink
from bot.services.achievements import platform_label
from bot.services.steam.auth import SteamAuth
from bot.services.steam.client import (
    SteamApiError,
    SteamGameDetailsPrivateError,
    get_profile,
    resolve_steam_id,
)

log = logging.getLogger(__name__)

router = Router(name="steam")

NOT_CONFIGURED_KEY = "steam-not-configured"
PRIVACY_URL = "https://steamcommunity.com/my/edit/settings"
GROUP_HINT_TTL = 30
# Shown by every path that ends in "now send me the link" — bare
# /connect_steam, the panel button, and the group hub's deep link alike.
# The privacy warning is up front on purpose (2026-09-05 follow-up): it
# used to only show up *after* a failed attempt (still does, below, in
# case someone doesn't read this first or fixes it only after sending the
# link), which meant a round trip everyone with a private profile hit once.

# tg_ids who just pressed "Подключить Steam" (button, bare command, or the
# group hub's deep link) — their next plain private message is the link or
# nickname, not something to route anywhere else. In-memory only, like
# admin.py's own _awaiting_input: nothing here is worth surviving a
# restart, and a stray leftover entry is harmless — it only ever affects
# what happens to that one person's very next private message.
_awaiting_link: set[int] = set()

# tg_id -> the raw text of a steamcommunity.com link spotted in an
# *unprompted* message, waiting on a yes/no tap (steam_link_spotted below).
_pending_confirmation: dict[int, str] = {}

# tg_id -> the raw profile link/nickname waiting on a "yes, switch accounts"
# tap (#52). Same in-memory, dies-with-the-process treatment as everything
# else here: a lost prompt just means answering /connect_steam again.
_pending_switch: dict[int, str] = {}

# Loose on purpose — /id/ and /profiles/ cover every real profile URL shape,
# and being stricter buys nothing: a false match here just offers a button
# that goes nowhere useful if tapped on garbage, a false miss silently does
# nothing, which is the worse failure of the two.
_STEAM_LINK_PATTERN = r"(?i)steamcommunity\.com/(id|profiles)/"


class AwaitingSteamLink(BaseFilter):
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


@router.message(Command("connect_steam"), F.chat.type != ChatType.PRIVATE)
async def connect_steam_in_group(message: Message, bot: Bot, i18n: I18nContext) -> None:
    # ?start=connectsteam (connect.py) is the same deep link the group hub's
    # own "🎮 Подключить Steam" button already uses — landing in DM this way
    # arms the wait immediately, so there is nothing left to type but the
    # link itself (2026-09-05 follow-up).
    await _redirect_to_dm(
        message, bot, i18n.get("steam-connect-group-redirect"), i18n, payload="connectsteam"
    )


@router.message(Command("disconnect_steam"), F.chat.type != ChatType.PRIVATE)
async def disconnect_steam_in_group(message: Message, bot: Bot, i18n: I18nContext) -> None:
    await _redirect_to_dm(message, bot, i18n.get("steam-private-only"), i18n)


async def prompt_for_link(
    bot: Bot,
    repo: Repo,
    steam_auth: SteamAuth,
    tg_id: int,
    i18n: I18nContext | StaticI18nContext | None = None,
) -> None:
    """The shared "now send me the link" step — bare /connect_steam, the
    panel button, and the deep link all go through this one place, so
    "already connected" and "not configured" are answered the same way
    regardless of which door someone came in through."""
    i18n = i18n or static_i18n("steam")
    if await steam_auth.get_key() is None:
        await bot.send_message(tg_id, i18n.get(NOT_CONFIGURED_KEY))
        return
    link = await repo.get_platform_link(tg_id, Platform.STEAM)
    if link is not None:
        await bot.send_message(tg_id, i18n.get("steam-already-connected", name=link.display_name))
        return
    _awaiting_link.add(tg_id)
    await bot.send_message(tg_id, i18n.get("steam-link-prompt", privacy_url=PRIVACY_URL))


@router.callback_query(F.data == "steam:connect")
async def steam_connect_button(
    callback: CallbackQuery, repo: Repo, steam_auth: SteamAuth, bot: Bot, i18n: I18nContext
) -> None:
    """The panel's own "🎮 Подключить Steam" button (2026-09-05 follow-up) —
    same prompt-and-wait as everywhere else, panel.py never had a Steam
    button at all before this."""
    await prompt_for_link(bot, repo, steam_auth, callback.from_user.id, i18n)
    await callback.answer()


@router.message(Command("connect_steam"), F.chat.type == ChatType.PRIVATE)
async def connect_steam(
    message: Message,
    repo: Repo,
    steam_auth: SteamAuth,
    command: CommandObject,
    steam_fetcher: SteamFetcher,
    bot: Bot,
    i18n: I18nContext,
) -> None:
    raw = (command.args or "").strip()
    if not raw:
        # No argument — wait for the next message instead of making someone
        # retype the whole command with the link tacked on (2026-09-05).
        await prompt_for_link(bot, repo, steam_auth, message.chat.id, i18n)
        return
    username = message.from_user.username if message.from_user else None
    await _connect(bot, repo, steam_auth, steam_fetcher, message.chat.id, username, raw, i18n)


@router.message(F.chat.type == ChatType.PRIVATE, AwaitingSteamLink())
async def steam_link_provided(
    message: Message,
    repo: Repo,
    steam_auth: SteamAuth,
    steam_fetcher: SteamFetcher,
    bot: Bot,
    i18n: I18nContext,
) -> None:
    """The answer to prompt_for_link's own prompt — whatever this message
    says, resolve_steam_id (services/steam/client.py) already accepts a
    full link, a bare SteamID64, or just a vanity nickname."""
    _awaiting_link.discard(message.from_user.id)
    username = message.from_user.username if message.from_user else None
    await _connect(
        bot,
        repo,
        steam_auth,
        steam_fetcher,
        message.chat.id,
        username,
        (message.text or "").strip(),
        i18n,
    )


@router.message(F.chat.type == ChatType.PRIVATE, F.text.regexp(_STEAM_LINK_PATTERN, mode="search"))
async def steam_link_spotted(message: Message, i18n: I18nContext) -> None:
    """Found live: someone pasted a steamcommunity.com link with no prior
    command at all. Registered after steam_link_provided above, so anyone
    already in the explicit flow lands there instead — this is only for a
    link that shows up out of nowhere, and gets a one-tap confirm rather
    than silently doing nothing with it (2026-09-05 follow-up)."""
    assert message.text is not None and message.from_user is not None
    _pending_confirmation[message.from_user.id] = message.text.strip()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("steam-link-confirm-yes"), callback_data="steam:linkyes"
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("steam-link-confirm-no"), callback_data="steam:linkno"
                )
            ],
        ]
    )
    await message.answer(i18n.get("steam-link-confirm-prompt"), reply_markup=keyboard)


@router.callback_query(F.data == "steam:linkno")
async def steam_link_decline(callback: CallbackQuery, i18n: I18nContext) -> None:
    _pending_confirmation.pop(callback.from_user.id, None)
    await safe_edit(callback, i18n.get("steam-link-declined"))
    await callback.answer()


@router.callback_query(F.data == "steam:linkyes")
async def steam_link_accept(
    callback: CallbackQuery,
    repo: Repo,
    steam_auth: SteamAuth,
    steam_fetcher: SteamFetcher,
    bot: Bot,
    i18n: I18nContext,
) -> None:
    raw = _pending_confirmation.pop(callback.from_user.id, None)
    if isinstance(callback.message, Message):
        with contextlib.suppress(Exception):
            await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    if raw is None:
        return
    username = callback.from_user.username
    await _connect(bot, repo, steam_auth, steam_fetcher, callback.from_user.id, username, raw, i18n)


def _unresolved_profile_hint(raw: str, i18n: I18nContext | StaticI18nContext | None = None) -> str:
    """2026-09-05 follow-up: a bare word that isn't a link gets a longer
    hint. Steam has no official way to search by the display name shown in
    the client/friends list, only by the *custom URL* slug
    (steamcommunity.com/id/<this>) — those two often match, but not
    always, and when they don't there is genuinely no way to resolve one
    from the other (verified: no ISteamUser search-by-name endpoint
    exists). A link or raw profile ID always works, so that's the only
    fallback offered — not a nickname search."""
    i18n = i18n or static_i18n("steam")
    hint = i18n.get("steam-unresolved-profile")
    if not re.search(_STEAM_LINK_PATTERN, raw):
        hint += i18n.get("steam-unresolved-profile-nickname-hint")
    return hint


async def _connect(
    bot: Bot,
    repo: Repo,
    steam_auth: SteamAuth,
    steam_fetcher: SteamFetcher,
    tg_id: int,
    username: str | None,
    raw: str,
    i18n: I18nContext | StaticI18nContext | None = None,
    *,
    confirmed: bool = False,
) -> None:
    """The actual link-and-backfill, shared by every entry point above —
    replying through `bot.send_message(tg_id, ...)` rather than a specific
    inbound Message's `.answer()` so it works the same whether triggered by
    a command, a plain message, or a callback confirmation."""
    i18n = i18n or static_i18n("steam")
    if await steam_auth.get_key() is None:
        await bot.send_message(tg_id, i18n.get(NOT_CONFIGURED_KEY))
        return
    if not raw:
        await prompt_for_link(bot, repo, steam_auth, tg_id, i18n)
        return

    api_key = await steam_auth.require_key()
    try:
        steam_id = await resolve_steam_id(api_key, raw)
        profile = await get_profile(api_key, steam_id)
    except SteamApiError as exc:
        # Found live: a report of "couldn't connect Steam" turned out
        # impossible to diagnose after the fact — nothing logged which of
        # the failure branches a given attempt actually hit (2026-09-05).
        # `raw` is whatever the person typed, not a secret — same as a
        # gamertag, safe to log as-is.
        log.info("connect_steam: could not resolve tg_id=%s raw=%r: %s", tg_id, raw, exc)
        await bot.send_message(tg_id, _unresolved_profile_hint(raw, i18n))
        return

    if not profile.is_public:
        log.info("connect_steam: private profile for tg_id=%s steam_id=%s", tg_id, steam_id)
        await bot.send_message(tg_id, i18n.get("steam-profile-private", privacy_url=PRIVACY_URL))
        return

    await repo.ensure_user(tg_id, username)

    # Swapping one Steam account for another is not an overwrite any more
    # (#52): the old account keeps its achievements, and they stop counting
    # for this person the moment the link moves. Worth asking first — but
    # only for a genuine identity change, never for relinking the same
    # account after a hiccup.
    preview = await relink.preview(repo, tg_id, Platform.STEAM, profile.steam_id)
    if preview.needs_confirmation and not confirmed:
        _pending_switch[tg_id] = raw
        await bot.send_message(
            tg_id,
            switch_prompt(
                preview,
                platform_label(Platform.STEAM, i18n.locale),
                profile.persona_name,
                i18n,
            ),
            reply_markup=switch_keyboard("steam", i18n),
        )
        return

    taken_from = await relink.perform(
        repo, tg_id, Platform.STEAM, profile.steam_id, profile.persona_name
    )
    log.info("connect_steam: tg_id=%s linked steam_id=%s", tg_id, profile.steam_id)
    await bot.send_message(tg_id, i18n.get("steam-connected", name=profile.persona_name))
    if taken_from is not None:
        await notify_previous_owner(
            bot,
            taken_from,
            Platform.STEAM,
            profile.persona_name,
            locale=await repo.user_locale(taken_from),
        )

    # An account the bot already knows needs a delta, not a backfill (#52):
    # its history is already stored, and only games played since our newest
    # stored unlock can hold anything new. Measured on a real account: 301
    # requests for the backfill, 2 for the delta.
    since = await repo.account_latest_unlock(Platform.STEAM, profile.steam_id)
    if since is not None:
        await bot.send_message(tg_id, i18n.get("steam-catch-up-started"))
        asyncio.create_task(  # noqa: RUF006
            steam_fetcher.catch_up(
                tg_id,
                profile.steam_id,
                profile.persona_name,
                since,
                get_settings().catchup_publish_window_hours,
            )
        )
        return

    # Backgrounded (SPEC 9, M-Steam-2d) — a big library is genuinely
    # hundreds of requests, the reply above must not wait for it.
    await bot.send_message(tg_id, i18n.get("steam-backfill-started"))
    asyncio.create_task(  # noqa: RUF006
        _backfill_and_notify(bot, steam_fetcher, tg_id, profile.steam_id, i18n)
    )


@router.callback_query(F.data == "steam:switch:yes")
async def steam_switch_confirmed(
    callback: CallbackQuery,
    repo: Repo,
    steam_auth: SteamAuth,
    steam_fetcher: SteamFetcher,
    bot: Bot,
    i18n: I18nContext,
) -> None:
    raw = _pending_switch.pop(callback.from_user.id, None)
    await callback.answer()
    if raw is None:
        return  # the prompt outlived a restart, or was answered twice
    with contextlib.suppress(Exception):
        await callback.message.delete()
    await _connect(
        bot,
        repo,
        steam_auth,
        steam_fetcher,
        callback.from_user.id,
        callback.from_user.username,
        raw,
        i18n,
        confirmed=True,
    )


@router.callback_query(F.data == "steam:switch:no")
async def steam_switch_cancelled(callback: CallbackQuery, i18n: I18nContext) -> None:
    _pending_switch.pop(callback.from_user.id, None)
    await callback.answer()
    with contextlib.suppress(Exception):
        await callback.message.edit_text(i18n.get("connect-switch-cancelled"))


async def _backfill_and_notify(
    bot: Bot, fetcher: SteamFetcher, tg_id: int, steam_id: str, i18n: I18nContext
) -> None:
    try:
        count = await fetcher.backfill(tg_id, steam_id)
    except SteamGameDetailsPrivateError:
        # Found live (whalerider84, 2026-09-08): "My Profile" passed the
        # is_public check above, but the separate "Game details" privacy
        # setting was still private/friends-only — backfill silently stored
        # 0, and this person would otherwise only ever see "0 достижений"
        # with no explanation anywhere. Same fix, same wording as
        # steam-profile-private, just caught one step later.
        log.info("connect_steam: game details private for tg_id=%s steam_id=%s", tg_id, steam_id)
        await bot.send_message(
            tg_id, i18n.get("steam-game-details-private", privacy_url=PRIVACY_URL)
        )
        return
    except Exception:
        log.exception("steam backfill for tg_id=%s failed", tg_id)
        await bot.send_message(tg_id, i18n.get("steam-backfill-failed"))
        return
    await bot.send_message(tg_id, i18n.get("steam-backfill-done", count=count))


def _disconnect_prompt_keyboard(i18n: I18nContext, *, from_panel: bool) -> InlineKeyboardMarkup:
    # Cancelling from the panel restores the panel in place (panel.py's own
    # panel:steamdisconnect:no) rather than just vanishing — same treatment
    # as XBOX's own disconnect_prompt_keyboard (keyboards.py), 2026-09-05.
    cancel_data = "panel:steamdisconnect:no" if from_panel else "steam:disconnect:no"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("steam-disconnect-confirm-button"),
                    callback_data="steam:disconnect:yes",
                )
            ],
            [InlineKeyboardButton(text=i18n.get("steam-cancel-button"), callback_data=cancel_data)],
        ]
    )


@router.message(Command("disconnect_steam"), F.chat.type == ChatType.PRIVATE)
async def disconnect_steam_command(message: Message, repo: Repo, i18n: I18nContext) -> None:
    link = await repo.get_platform_link(message.chat.id, Platform.STEAM)
    if link is None:
        await message.answer(i18n.get("steam-already-disconnected"))
        return
    await message.answer(
        i18n.get("steam-disconnect-prompt", name=link.display_name),
        reply_markup=_disconnect_prompt_keyboard(i18n, from_panel=False),
    )


@router.callback_query(F.data == "steam:disconnectprompt")
async def steam_disconnect_button(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    """The panel's own "🔕 Отключить Steam" button (2026-09-05 follow-up,
    same treatment XBOX's disconnect button already gets)."""
    link = await repo.get_platform_link(callback.from_user.id, Platform.STEAM)
    if link is None:
        await callback.answer(i18n.get("steam-already-disconnected"), show_alert=True)
        return
    await safe_edit(
        callback,
        i18n.get("steam-disconnect-prompt", name=link.display_name),
        _disconnect_prompt_keyboard(i18n, from_panel=True),
    )
    await callback.answer()


@router.callback_query(F.data == "steam:disconnect:no")
async def disconnect_steam_cancel(callback: CallbackQuery) -> None:
    if isinstance(callback.message, Message):
        with contextlib.suppress(Exception):
            await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data == "steam:disconnect:yes")
async def disconnect_steam_confirm(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    link = await repo.get_platform_link(callback.from_user.id, Platform.STEAM)
    await repo.unlink_platform_account(callback.from_user.id, Platform.STEAM)
    if link is not None:
        # Symmetric with Xbox's disconnect (connect.py, delete_presence_state)
        # — a stale presence row would otherwise keep answering /online for
        # an account that's no longer linked to anyone.
        await repo.delete_steam_presence_state(link.external_id)
    # Found while refactoring (2026-09-05): the one edit in this file that
    # didn't tolerate a failed edit, unlike every other one here.
    await safe_edit(callback, i18n.get("steam-disconnected"))
    await callback.answer()
