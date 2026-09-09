"""/panel — the user's own screen. Reads the database only (SPEC 1.5)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram_i18n import I18nContext

from bot.config import Settings
from bot.constants import Platform, PresenceState, RarityMode, TokenStatus
from bot.db.repo import PlatformLink, Repo, User, UserChatRow
from bot.handlers.keyboards import (
    DIGEST_NEVER,
    deep_link_keyboard,
    digest_keyboard,
    disconnect_prompt_keyboard,
    format_digest,
    format_offset,
    format_rarity,
    next_rarity_mode,
    panel_keyboard,
    safe_edit,
    timezone_keyboard,
)
from bot.i18n import StaticI18nContext, static_i18n
from bot.poller.fetcher import Fetcher
from bot.services.achievements import (
    platform_header_lines,
    telegram_identity,
    visibility_status_text,
)
from bot.services.single_message import send_replacing
from bot.util import cooldown_minutes_left, humanize_ago, parse_iso

log = logging.getLogger(__name__)

router = Router(name="panel")

GROUP_HINT_TTL = 30

# The one panel button that goes to the network (SPEC 5.8). Without a cooldown
# it is a way to hammer Xbox Live by holding a finger on the keyboard.
SYNC_COOLDOWN_SECONDS = 600
_last_sync: dict[int, float] = {}

LOGIN_STATUS_KEYS = {
    TokenStatus.ACTIVE: "panel-login-active",
    TokenStatus.INVALID: "panel-login-invalid",
    TokenStatus.REVOKED: "panel-login-revoked",
}


async def send_panel(bot: Bot, repo: Repo, tg_id: int, i18n: I18nContext) -> None:
    """The one place that actually delivers the panel as a new message
    (not an edit) — the bare /panel command and the ?start=panel deep link
    (handlers/connect.py) both go through this, so a person re-opening
    their panel replaces the previous copy instead of piling up a new one
    every time (Follow-up 2026-09-06)."""
    text, markup = await render_panel(repo, tg_id, i18n)
    await send_replacing(bot, repo, tg_id, "panel", text, reply_markup=markup)


@router.message(Command("panel"), F.chat.type == ChatType.PRIVATE)
async def panel_command(message: Message, repo: Repo, bot: Bot, i18n: I18nContext) -> None:
    await repo.ensure_user(message.chat.id, _username(message))
    await send_panel(bot, repo, message.chat.id, i18n)


@router.message(Command("panel"))
async def panel_in_group(message: Message, bot: Bot, i18n: I18nContext) -> None:
    """Settings never render in a group: an inline keyboard there is clickable
    by everyone in the chat (SPEC 6.3)."""
    me = await bot.me()
    hint = await message.answer(
        i18n.get("panel-group-hint"),
        reply_markup=deep_link_keyboard(f"https://t.me/{me.username}?start=panel", i18n),
    )
    asyncio.create_task(_delete_later(bot, hint.chat.id, hint.message_id))  # noqa: RUF006


@router.callback_query(F.data == "panel:refresh")
async def panel_refresh(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    text, markup = await render_panel(repo, callback.from_user.id, i18n)
    await safe_edit(callback, text, markup)
    await callback.answer(i18n.get("panel-refreshed"))


@router.callback_query(F.data == "panel:sync")
async def panel_sync(
    callback: CallbackQuery, repo: Repo, fetcher: Fetcher, settings: Settings, i18n: I18nContext
) -> None:
    """Catch up on what was unlocked while the bot was down (SPEC 5.8)."""
    tg_id = callback.from_user.id
    user = await repo.get_user(tg_id)
    if user is None or not user.xuid:
        await callback.answer(i18n.get("panel-xbox-not-connected"), show_alert=True)
        return

    minutes_left = cooldown_minutes_left(
        _last_sync.get(tg_id), time.monotonic(), SYNC_COOLDOWN_SECONDS
    )
    if minutes_left:
        await callback.answer(i18n.get("panel-sync-cooldown", minutes=minutes_left))
        return

    _last_sync[tg_id] = time.monotonic()
    await callback.answer(i18n.get("panel-syncing"))

    target = next((t for t in await repo.pollable_users() if t.tg_id == tg_id), None)
    try:
        titles, published = await fetcher.catch_up(
            tg_id,
            user.xuid,
            user.gamertag or i18n.get("panel-default-player-name"),
            parse_iso(target.updated_at) if target else None,
            settings.catchup_publish_window_hours,
            settings.catchup_max_titles,
        )
    except Exception:
        log.exception("manual catch-up for tg_id=%s failed", tg_id)
        if isinstance(callback.message, Message):
            await callback.message.answer(i18n.get("panel-sync-failed"))
        return

    summary = (
        i18n.get("panel-sync-summary-found", titles=titles, published=published)
        if titles
        else i18n.get("panel-sync-summary-none")
    )
    if isinstance(callback.message, Message):
        await callback.message.answer(summary)


@router.callback_query(F.data == "panel:disconnect")
async def panel_disconnect_prompt(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    """Same confirmation as /disconnect_xbox — the actual disconnect handlers
    (disconnect:yes / disconnect:no in connect.py) just edit whatever message
    triggered them, so they work unchanged from the panel too."""
    from bot.handlers.connect import REVOKE_URL

    user = await repo.get_user(callback.from_user.id)
    if user is None or not user.xuid:
        await callback.answer(i18n.get("panel-xbox-already-disconnected"), show_alert=True)
        return
    await safe_edit(
        callback,
        i18n.get("panel-disconnect-prompt", revoke_url=REVOKE_URL),
        disconnect_prompt_keyboard(i18n, from_panel=True),
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data == "panel:disconnect:no")
async def panel_disconnect_cancel(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    # Cancelling here edits the panel message itself, so restore the panel
    # in place instead of leaving a throwaway "cancelled" message behind.
    text, markup = await render_panel(repo, callback.from_user.id, i18n)
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data == "panel:steamdisconnect:no")
async def panel_steam_disconnect_cancel(
    callback: CallbackQuery, repo: Repo, i18n: I18nContext
) -> None:
    """Same treatment as panel_disconnect_cancel above, for Steam's own
    disconnect button (2026-09-05 follow-up)."""
    text, markup = await render_panel(repo, callback.from_user.id, i18n)
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data == "panel:psndisconnect:no")
async def panel_psn_disconnect_cancel(
    callback: CallbackQuery, repo: Repo, i18n: I18nContext
) -> None:
    """Same treatment as panel_steam_disconnect_cancel above, for PSN's own
    disconnect button (SPEC 9, M-PSN-1)."""
    text, markup = await render_panel(repo, callback.from_user.id, i18n)
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data == "panel:linkstoggle")
async def panel_toggle_profile_links(
    callback: CallbackQuery, repo: Repo, i18n: I18nContext
) -> None:
    """Flips user_settings.show_profile_links (Follow-up 2026-09-06) —
    one tap, no confirm, same weight as re-subscribing to a chat: showing
    a link costs the person nothing they can't undo with another tap."""
    settings_row = await repo.get_user_settings(callback.from_user.id)
    currently_on = bool(settings_row and settings_row.show_profile_links)
    await repo.update_user_settings(
        callback.from_user.id, show_profile_links=0 if currently_on else 1
    )
    await callback.answer(
        i18n.get("panel-links-hidden-toast" if currently_on else "panel-links-shown-toast")
    )
    text, markup = await render_panel(repo, callback.from_user.id, i18n)
    await safe_edit(callback, text, markup)


@router.callback_query(F.data == "panel:tz")
async def panel_timezone(callback: CallbackQuery, i18n: I18nContext) -> None:
    # Found while refactoring (2026-09-05): the one edit in this file that
    # didn't tolerate a failed edit, unlike every other one here.
    await safe_edit(
        callback,
        i18n.get("panel-timezone-prompt"),
        timezone_keyboard(i18n, skippable=False),
    )
    await callback.answer()


# ------------------------------------------------------------------ my chats


@router.callback_query(F.data == "panel:chatlist")
async def panel_chat_list(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    await _redraw_chat_list(callback, repo, i18n)


async def _redraw_chat_list(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    chats = await repo.user_chats(callback.from_user.id)
    text = i18n.get("panel-my-chats-title")
    if not chats:
        text += i18n.get("panel-my-chats-empty")
    builder = InlineKeyboardBuilder()
    for chat in chats:
        mark = "✅" if chat.is_subscribed else "⚪"
        builder.row(
            InlineKeyboardButton(
                text=f"{mark} {chat.title or chat.chat_id}",
                callback_data=f"panel:chat:{chat.chat_id}",
            )
        )
    builder.row(InlineKeyboardButton(text=i18n.get("panel-back"), callback_data="panel:refresh"))
    await safe_edit(callback, text, builder.as_markup())
    await callback.answer()


async def _find_user_chat(repo: Repo, tg_id: int, chat_id: int) -> UserChatRow | None:
    return next((c for c in await repo.user_chats(tg_id) if c.chat_id == chat_id), None)


async def _chat_card(
    repo: Repo, tg_id: int, chat_id: int, i18n: I18nContext
) -> tuple[str, InlineKeyboardMarkup] | None:
    chat = await _find_user_chat(repo, tg_id, chat_id)
    if chat is None:
        return None
    title = chat.title or chat.chat_id
    builder = InlineKeyboardBuilder()
    if chat.is_subscribed:
        text = (
            i18n.get("panel-chat-card-title", title=title)
            + "\n\n"
            + i18n.get("panel-publication-enabled")
        )
        # Per-chat, not one shared value any more (SPEC 9, M-Steam-2e's
        # follow-up) — only shown while actually publishing here, same as
        # min_gamerscore/muted_title_ids having nothing to apply to
        # otherwise.
        builder.row(
            InlineKeyboardButton(
                text=i18n.get(
                    "panel-achievements-mode",
                    mode=format_rarity(chat.rarity_mode or RarityMode.ALL, i18n),
                ),
                callback_data=f"panel:chatrarity:{chat_id}",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=i18n.get(
                    "panel-digest-row",
                    threshold=format_digest(chat.digest_threshold or 3, i18n),
                ),
                callback_data=f"panel:chatdigest:{chat_id}",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=i18n.get("panel-unsubscribe"), callback_data=f"panel:chatunsub:{chat_id}"
            )
        )
    else:
        text = (
            i18n.get("panel-chat-card-title", title=title)
            + "\n\n"
            + i18n.get("panel-publication-disabled")
        )
        builder.row(
            InlineKeyboardButton(
                text=i18n.get("panel-subscribe"), callback_data=f"panel:chatsub:{chat_id}"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=i18n.get("panel-remove-from-list"), callback_data=f"panel:chatdel:{chat_id}"
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=i18n.get("panel-back-to-chat-list"), callback_data="panel:chatlist"
        )
    )
    return text, builder.as_markup()


async def _redraw_chat_card(
    callback: CallbackQuery, repo: Repo, chat_id: int, i18n: I18nContext
) -> None:
    built = await _chat_card(repo, callback.from_user.id, chat_id, i18n)
    if built is None:
        await _redraw_chat_list(callback, repo, i18n)
        return
    text, markup = built
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data.startswith("panel:chat:"))
async def panel_chat_card(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    await _redraw_chat_card(callback, repo, chat_id, i18n)


@router.callback_query(F.data.startswith("panel:chatrarity:"))
async def panel_chat_rarity_cycle(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    """One tap advances this chat's mode to the next one (SPEC 9, M-Steam-2e's
    follow-up — moved off the main panel, per chat now)."""
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await _find_user_chat(repo, callback.from_user.id, chat_id)
    if chat is None or not chat.is_subscribed:
        await callback.answer()
        return
    mode = next_rarity_mode(chat.rarity_mode or RarityMode.ALL)
    await repo.update_subscription_rarity_mode(chat_id, callback.from_user.id, mode)
    await _redraw_chat_card(callback, repo, chat_id, i18n)


@router.callback_query(F.data.startswith("panel:chatdigest:"))
async def panel_chat_digest_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    """Per chat now, not the main panel screen (Follow-up, 2026-09-05, same
    move as the rarity toggle above it)."""
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await _find_user_chat(repo, callback.from_user.id, chat_id)
    if chat is None or not chat.is_subscribed:
        await callback.answer()
        return
    current = chat.digest_threshold or 3
    await safe_edit(
        callback,
        i18n.get("panel-digest-menu"),
        digest_keyboard(current, chat_id, i18n),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("panel:cdigestset:"))
async def panel_chat_digest_set(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    _, _, chat_id_raw, value_raw = callback.data.split(":")
    chat_id, value = int(chat_id_raw), int(value_raw)
    await repo.update_subscription_digest_threshold(chat_id, callback.from_user.id, value)
    await callback.answer(
        i18n.get("panel-digest-set-never-toast")
        if value >= DIGEST_NEVER
        else i18n.get("panel-digest-set-from-toast", value=value)
    )
    await _redraw_chat_card(callback, repo, chat_id, i18n)


@router.callback_query(F.data.startswith("panel:chatsub:"))
async def panel_chat_subscribe(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    """No confirm — resubscribing has no downside, unlike unsubscribing or
    deleting (SPEC 6.2).

    Found live (2026-09-09, keimaks/kmaks90 — same class of bug as
    /subscribe's own #35-adjacent fix): this used to gate on `not user.xuid`
    alone, so a Steam/PSN-only person's own "Мои чаты" screen could never
    re-subscribe to a chat either — publishing has nothing to do with Xbox
    specifically."""
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    user = await repo.get_user(callback.from_user.id)
    platform_links = await repo.platform_links_of(callback.from_user.id) if user else []
    if user is None or (not user.xuid and not platform_links):
        await callback.answer(i18n.get("panel-connect-any-platform-first"), show_alert=True)
        return
    await repo.subscribe(chat_id, callback.from_user.id)
    await callback.answer(i18n.get("panel-subscribed-toast"))
    await _redraw_chat_card(callback, repo, chat_id, i18n)


@router.callback_query(F.data.startswith("panel:chatunsub:"))
async def panel_chat_unsub_prompt(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    """Same weight as the standalone /unsubscribe — a confirm, not an instant
    action (SPEC 6.3): losing a feed in a chat deserves a second tap."""
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await _find_user_chat(repo, callback.from_user.id, chat_id)
    if chat is None:
        await _redraw_chat_list(callback, repo, i18n)
        return
    title = chat.title or chat.chat_id
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=i18n.get("panel-unsub-yes"), callback_data=f"panel:chatunsuby:{chat_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=i18n.get("panel-unsub-cancel"), callback_data=f"panel:chat:{chat_id}"
        )
    )
    await safe_edit(callback, i18n.get("panel-unsub-prompt", title=title), builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("panel:chatunsuby:"))
async def panel_chat_unsub_confirm(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    await repo.unsubscribe(chat_id, callback.from_user.id)
    await callback.answer(i18n.get("panel-unsubscribed-toast"))
    await _redraw_chat_card(callback, repo, chat_id, i18n)


@router.callback_query(F.data.startswith("panel:chatdel:"))
async def panel_chat_delete_prompt(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    chat = await _find_user_chat(repo, callback.from_user.id, chat_id)
    if chat is None:
        await _redraw_chat_list(callback, repo, i18n)
        return
    title = chat.title or chat.chat_id
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=i18n.get("panel-delete-yes"), callback_data=f"panel:chatdely:{chat_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=i18n.get("panel-unsub-cancel"), callback_data=f"panel:chat:{chat_id}"
        )
    )
    await safe_edit(
        callback,
        i18n.get("panel-delete-prompt", title=title),
        builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("panel:chatdely:"))
async def panel_chat_delete_confirm(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    await repo.forget_chat_membership(chat_id, callback.from_user.id)
    await callback.answer(i18n.get("panel-deleted-toast"))
    await _redraw_chat_list(callback, repo, i18n)


def _panel_identity(user: User, i18n: I18nContext | StaticI18nContext) -> str:
    """The person's own name for the /panel header (#18) — same priority as
    /stats' header (@username > first+last > gamertag, `telegram_identity`,
    2026-09-08 review: this used to reimplement that chain a third time).
    This screen is only ever shown to its owner, so a bare id is the
    guaranteed last resort."""
    name = telegram_identity(
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        gamertag=user.gamertag,
    )
    return i18n.get("panel-header-identity", name=name or str(user.tg_id))


async def _panel_header_lines(
    repo: Repo,
    user: User,
    steam_link: PlatformLink | None,
    psn_link: PlatformLink | None,
    i18n: I18nContext | StaticI18nContext,
) -> list[str]:
    """Identity + one line per connected platform with its lifetime count
    (#18) — now built by the exact same function /stats' own header uses
    (services/achievements.py::platform_header_lines, 2026-09-08 user
    request: "пусть одни одинаково формируются" — this used to be a
    hand-duplicated, HTML-identical copy of that same logic).

    `show_links=False`: unlike /stats, this header's names were never
    inline hyperlinks — /panel's own "Profile" buttons already cover that
    (CLAUDE.md: "always visible regardless of the privacy toggle" is about
    those buttons, not a second, redundant link inside the header text)."""
    platform_links = [link for link in (steam_link, psn_link) if link is not None]
    return [_panel_identity(user, i18n)] + await platform_header_lines(
        repo,
        tg_id=user.tg_id,
        xuid=user.xuid,
        gamertag=user.gamertag,
        gamerscore=user.gamerscore,
        platform_links=platform_links,
        show_links=False,
    )


async def render_panel(
    repo: Repo, tg_id: int, i18n: I18nContext | StaticI18nContext | None = None
) -> tuple[str, InlineKeyboardMarkup]:
    i18n = i18n or static_i18n("panel")
    user = await repo.get_user(tg_id)
    settings_row = await repo.get_user_settings(tg_id)
    connected = user is not None and bool(user.xuid)
    steam_link = await repo.get_platform_link(tg_id, Platform.STEAM)
    psn_link = await repo.get_platform_link(tg_id, Platform.PSN)

    token = await repo.get_token(tg_id) if connected else None
    needs_reconnect = token is not None and token.status == TokenStatus.INVALID
    tz_offset = settings_row.tz_offset_min if settings_row else None
    keyboard = panel_keyboard(
        tz_offset,
        i18n,
        connected=connected,
        needs_reconnect=needs_reconnect,
        steam_connected=steam_link is not None,
        psn_connected=psn_link is not None,
        gamertag=user.gamertag if user else None,
        steam_id=steam_link.external_id if steam_link else None,
        psn_id=psn_link.display_name if psn_link else None,
        show_profile_links=bool(settings_row and settings_row.show_profile_links),
    )

    if user is None:
        # Defensive only — every real call site ensures the user row first
        # (panel_command's own repo.ensure_user, or a callback that can only
        # fire from an already-rendered panel in the first place).
        return i18n.get("panel-header-not-connected"), keyboard

    # The body is the same shape regardless of which platforms are
    # connected (2026-09-09, confirmed live: a Steam/PSN-only person used to
    # get an entirely different, stripped-down body here — no header/
    # achievement counts, no publication/presence/timezone rows at all —
    # because this whole branch used to hard-gate on Xbox specifically,
    # a leftover from before Steam/PSN existed. Every row below now
    # degrades per-platform (shown/omitted on its own) instead of the
    # whole body switching on whether *Xbox* is connected.
    login = (
        i18n.get(LOGIN_STATUS_KEYS.get(token.status, "panel-login-revoked"))
        if token
        else i18n.get("panel-login-not-connected")
    )

    # Header: identity + per-platform lifetime counts (#18). The 24h/30d
    # counters and "последние достижения" list this body used to carry are
    # gone — the header covers achievements now.
    lines = await _panel_header_lines(repo, user, steam_link, psn_link, i18n)
    lines += ["", i18n.get("panel-login-xbox-row", status=login)]
    if steam_link is not None:
        lines.append(
            i18n.get(
                "panel-login-steam-row",
                name=steam_link.display_name,
                status=visibility_status_text(steam_link),
            )
        )
    if psn_link is not None:
        lines.append(
            i18n.get(
                "panel-login-psn-row",
                name=psn_link.display_name,
                status=visibility_status_text(psn_link),
            )
        )
    lines.append(
        i18n.get(
            "panel-publication-row",
            status=await _publication_status(repo, user.tg_id, user.is_excluded, i18n),
        )
    )
    if user.xuid:
        # Presence stays Xbox-only for now (issue #1's own follow-up note,
        # CLAUDE.md) — Steam/PSN both have presence data now too, just not
        # wired into this one row yet. Omitted rather than shown as "нет
        # данных" for a Steam/PSN-only person: unlike the login rows above,
        # there is no per-platform variant of this row to fall back to yet.
        playing = await _now_playing(repo, user.xuid, i18n)
        lines.append(i18n.get("panel-now-playing-row", playing=playing))
    lines += [
        "",
        # Kept as a text line too (#18): the person should see which
        # timezone is selected, not just have it on the button label.
        i18n.get("panel-timezone-row", offset=format_offset(tz_offset, i18n)),
    ]
    if needs_reconnect:
        lines += ["", i18n.get("panel-reconnect-hint")]
    return "\n".join(lines), keyboard


async def _now_playing(repo: Repo, xuid: str, i18n: I18nContext) -> str:
    presence = await repo.presence_of(xuid)
    if presence is None:
        return i18n.get("panel-no-presence-data")
    if presence.state != PresenceState.ONLINE:
        return i18n.get("panel-offline", ago=humanize_ago(presence.updated_at))
    if not presence.title_id:
        return i18n.get("panel-online-idle")
    # Presence gives no name for PC titles — fall back to the cache the
    # poller fills (SPEC 4), same as the admin card.
    game = presence.title_name or await repo.title_name(presence.title_id) or presence.title_id
    return i18n.get("panel-playing", game=game)


async def _publication_status(repo: Repo, tg_id: int, is_excluded: bool, i18n: I18nContext) -> str:
    if is_excluded:
        # An exclusion is never silent: the person sees it here (SPEC 6.4).
        return i18n.get("panel-excluded")
    chats = await repo.chats_of_user(tg_id)
    if not chats:
        return i18n.get("panel-not-subscribed-anywhere")
    return i18n.get("panel-subscribed-in", chats=", ".join(f"«{title}»" for title in chats))


async def _delete_later(bot: Bot, chat_id: int, message_id: int) -> None:
    await asyncio.sleep(GROUP_HINT_TTL)
    with contextlib.suppress(Exception):
        await bot.delete_message(chat_id, message_id)


def _username(message: Message) -> str | None:
    return message.from_user.username if message.from_user else None
