"""/panel — the user's own screen. Reads the database only (SPEC 1.5)."""

from __future__ import annotations

import logging
import time

from aiogram import Bot, F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram_i18n import I18nContext

from bot.config import Settings
from bot.constants import AccountPlatform, Platform, RarityMode, TokenStatus
from bot.db.repo import PlatformLink, Repo
from bot.handlers.delivery import safe_edit
from bot.poller.fetcher import Fetcher
from bot.poller.psn_fetcher import PsnFetcher
from bot.poller.steam_catch_up import catch_up_steam_account
from bot.poller.steam_fetcher import SteamFetcher
from bot.services.naming import link_nickname
from bot.services.single_message import send_replacing
from bot.services.steam import client as steam_client  # noqa: F401
from bot.services.steam.auth import SteamAuth
from bot.util import cooldown_minutes_left, parse_iso
from bot.views.keyboards import (
    disconnect_prompt_keyboard,
    locale_name,
    next_locale,
    timezone_keyboard,
)
from bot.views.panel import (
    render_account_menu,
    render_chat_card,
    render_chat_delete_prompt,
    render_chat_list,
    render_panel,
    render_panel_delete_confirm_1,
    render_panel_delete_confirm_2,
    render_rarity_picker,
    render_unsub_prompt,
)

log = logging.getLogger(__name__)

router = Router(name="panel")

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
    screen = await render_panel(repo, tg_id, locale=i18n.locale)
    await send_replacing(
        bot,
        repo,
        tg_id,
        "panel",
        screen.text,
        reply_markup=screen.keyboard,
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("panel"), F.chat.type == ChatType.PRIVATE)
async def panel_command(message: Message, repo: Repo, bot: Bot, i18n: I18nContext) -> None:
    person_id = _person_id(message)
    if person_id is None:
        return
    await repo.ensure_user(person_id, _username(message))
    await send_panel(bot, repo, person_id, i18n)


@router.callback_query(F.data == "panel:refresh")
async def panel_refresh(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    await repo.touch_last_online(callback.from_user.id)
    screen = await render_panel(repo, callback.from_user.id, locale=i18n.locale)
    await safe_edit(callback, screen.text, screen.keyboard, parse_mode=ParseMode.HTML)
    await callback.answer(i18n.get("panel-refreshed"))


@router.callback_query(F.data == "panel:sync")
async def panel_sync(
    callback: CallbackQuery,
    repo: Repo,
    fetcher: Fetcher,
    steam_fetcher: SteamFetcher,
    psn_fetcher: PsnFetcher,
    steam_auth: SteamAuth,
    settings: Settings,
    i18n: I18nContext,
) -> None:
    """Wake up user, refresh UI, and catch up across all connected platforms (Xbox, Steam, PSN)."""
    tg_id = callback.from_user.id
    await repo.touch_last_online(tg_id)

    screen = await render_panel(repo, tg_id, locale=i18n.locale)
    await safe_edit(callback, screen.text, screen.keyboard, parse_mode=ParseMode.HTML)

    user = await repo.get_user(tg_id)
    token = await repo.get_token(tg_id) if user and user.xuid else None
    xbox_linked = bool(user and user.xuid)
    xbox_active = bool(xbox_linked and token and token.status == TokenStatus.ACTIVE)
    steam_link = await repo.get_platform_link(tg_id, Platform.STEAM)
    psn_links = await repo.platform_links_for(tg_id, Platform.PSN)
    psn_link = psn_links[0] if psn_links else None

    if not (xbox_linked or steam_link or psn_link):
        await callback.answer(i18n.get("panel-connect-any-platform-first"), show_alert=True)
        return

    if xbox_linked and not xbox_active and not (steam_link or psn_link):
        await callback.answer(i18n.get("panel-login-invalid"), show_alert=True)
        return

    minutes_left = cooldown_minutes_left(
        _last_sync.get(tg_id), time.monotonic(), SYNC_COOLDOWN_SECONDS
    )
    if minutes_left:
        await callback.answer(i18n.get("panel-sync-cooldown", minutes=minutes_left))
        return

    _last_sync[tg_id] = time.monotonic()
    await callback.answer(i18n.get("panel-syncing"))

    total_titles = 0
    total_published = 0
    errors: list[str] = []
    attempted_platforms = 0

    # 1. Xbox
    if xbox_active and user and user.xuid:
        attempted_platforms += 1
        since_iso = await repo.account_latest_unlock(AccountPlatform.XBOX, user.xuid)
        try:
            x_titles, x_published = await fetcher.catch_up(
                tg_id,
                user.xuid,
                user.gamertag or i18n.get("panel-default-player-name"),
                parse_iso(since_iso) if since_iso else None,
                settings.catchup_publish_window_hours,
                settings.catchup_max_titles,
            )
            total_titles += x_titles
            total_published += x_published
        except Exception:
            errors.append("xbox")
            log.exception("manual xbox catch-up for tg_id=%s failed", tg_id)

    # 2. Steam
    if steam_link:
        attempted_platforms += 1
        try:
            s_titles, s_published = await catch_up_steam_account(
                settings,
                repo,
                steam_fetcher,
                steam_auth,
                tg_id,
                steam_link.external_id,
                link_nickname(steam_link),
            )
            total_titles += s_titles
            total_published += s_published
        except Exception:
            errors.append("steam")
            log.exception("manual steam catch-up for tg_id=%s failed", tg_id)

    # 3. PSN — every account the person holds (#10)
    for link in psn_links:
        attempted_platforms += 1
        try:
            p_published = await psn_fetcher.poll_account(
                tg_id, link.external_id, link_nickname(link)
            )
            total_published += p_published
        except Exception:
            errors.append("psn")
            log.exception("manual psn catch-up for tg_id=%s failed", tg_id)

    # Redraw panel with newly inserted achievements / gamerscore
    screen = await render_panel(repo, tg_id, locale=i18n.locale)
    await safe_edit(callback, screen.text, screen.keyboard, parse_mode=ParseMode.HTML)

    if errors and (len(errors) == attempted_platforms or not (total_titles or total_published)):
        summary = i18n.get("panel-sync-failed")
    elif total_titles or total_published:
        summary = i18n.get(
            "panel-sync-summary-found", titles=total_titles, published=total_published
        )
    else:
        summary = i18n.get("panel-sync-summary-none")
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
    # Cancelling here edits the panel message itself, so restore the screen
    # the prompt came from instead of leaving a "cancelled" message behind.
    await _redraw_account_menu(callback, repo, AccountPlatform.XBOX, i18n)


@router.callback_query(F.data == "panel:steamdisconnect:no")
async def panel_steam_disconnect_cancel(
    callback: CallbackQuery, repo: Repo, i18n: I18nContext
) -> None:
    """Same treatment as panel_disconnect_cancel above, for Steam's own
    disconnect button (2026-09-05 follow-up)."""
    await _redraw_account_menu(callback, repo, AccountPlatform.STEAM, i18n)


@router.callback_query(F.data == "panel:psndisconnect:no")
async def panel_psn_disconnect_cancel(
    callback: CallbackQuery, repo: Repo, i18n: I18nContext
) -> None:
    """Same treatment as panel_steam_disconnect_cancel above, for PSN's own
    disconnect button (SPEC 9, M-PSN-1)."""
    await _redraw_account_menu(callback, repo, AccountPlatform.PSN, i18n)


async def _redraw_account_menu(
    callback: CallbackQuery, repo: Repo, platform: str, i18n: I18nContext, *, answer: bool = True
) -> None:
    """A platform's own screen (#10), or the panel once nothing is left on
    that platform to show."""
    screen = await render_account_menu(repo, callback.from_user.id, platform, locale=i18n.locale)
    if screen is None:
        screen = await render_panel(repo, callback.from_user.id, locale=i18n.locale)
    await safe_edit(callback, screen.text, screen.keyboard, parse_mode=ParseMode.HTML)
    if answer:
        await callback.answer()


async def _links_of(repo: Repo, tg_id: int, platform: str) -> list[PlatformLink]:
    if platform == AccountPlatform.PSN:
        return await repo.platform_links_for(tg_id, platform)
    link = await repo.get_platform_link(tg_id, platform)
    return [link] if link is not None else []


@router.callback_query(F.data.startswith("panel:acc:"))
async def panel_account_menu(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    """A platform's button on /panel (#10): its own screen."""
    assert callback.data is not None
    platform = callback.data.rsplit(":", 1)[1]
    if platform not in (AccountPlatform.XBOX, AccountPlatform.PSN, AccountPlatform.STEAM):
        await callback.answer()
        return
    await _redraw_account_menu(callback, repo, platform, i18n)


@router.callback_query(F.data.startswith("panel:pub:"))
async def panel_toggle_publishing(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    """The person's own switch for a whole platform (#20, #10): announce its
    achievements, or keep them to stats. With several PSN accounts some on
    and some off ("Частично"), a tap turns them all on. One tap, no
    confirmation — just as undoable as the profile-links toggle."""
    assert callback.data is not None
    platform = callback.data.rsplit(":", 1)[1]
    links = await _links_of(repo, callback.from_user.id, platform)
    if not links:
        await callback.answer()
        return
    publishes = not all(link.publishes for link in links)
    await repo.set_platform_publishes(callback.from_user.id, platform, publishes)
    await callback.answer(
        i18n.get("panel-publishes-on-toast" if publishes else "panel-publishes-off-toast")
    )
    screen = await render_panel(repo, callback.from_user.id, locale=i18n.locale)
    await safe_edit(callback, screen.text, screen.keyboard, parse_mode=ParseMode.HTML)


@router.callback_query(F.data.startswith("panel:accpub:"))
async def panel_toggle_account_publishing(
    callback: CallbackQuery, repo: Repo, i18n: I18nContext
) -> None:
    """The same switch on XBOX's or Steam's own screen, which stays open."""
    assert callback.data is not None
    platform = callback.data.rsplit(":", 1)[1]
    link = await repo.get_platform_link(callback.from_user.id, platform)
    if link is None:
        await callback.answer()
        return
    await _toggle_one(callback, repo, link, i18n)
    await _redraw_account_menu(callback, repo, platform, i18n, answer=False)


@router.callback_query(F.data.startswith("panel:psnpub:"))
async def panel_toggle_psn_account(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    """One PSN account's switch, on the PSN screen (#10)."""
    assert callback.data is not None
    account_id = callback.data.rsplit(":", 1)[1]
    links = await repo.platform_links_for(callback.from_user.id, AccountPlatform.PSN)
    link = next((item for item in links if item.external_id == account_id), None)
    if link is not None:
        await _toggle_one(callback, repo, link, i18n)
    await _redraw_account_menu(callback, repo, AccountPlatform.PSN, i18n, answer=link is None)


async def _toggle_one(
    callback: CallbackQuery, repo: Repo, link: PlatformLink, i18n: I18nContext
) -> None:
    await repo.set_account_publishes(
        callback.from_user.id, link.platform, link.external_id, not link.publishes
    )
    await callback.answer(
        i18n.get("panel-publishes-off-toast" if link.publishes else "panel-publishes-on-toast")
    )


@router.callback_query(F.data == "panel:rarity")
async def panel_rarity(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    """The person's rarity mode, for every chat at once (#126)."""
    screen = await render_rarity_picker(repo, callback.from_user.id, locale=i18n.locale)
    await safe_edit(callback, screen.text, screen.keyboard, parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(F.data.startswith("panel:rarityset:"))
async def panel_rarity_set(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    mode = callback.data.rsplit(":", 1)[1]
    if mode not in (RarityMode.ALL, RarityMode.RARE, RarityMode.HIDDEN):
        await callback.answer()
        return
    await repo.ensure_user(callback.from_user.id, callback.from_user.username)
    await repo.update_user_settings(callback.from_user.id, rarity_mode=mode)
    await callback.answer(i18n.get(f"chat-hub-toast-{mode}"))
    screen = await render_panel(repo, callback.from_user.id, locale=i18n.locale)
    await safe_edit(callback, screen.text, screen.keyboard, parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "panel:locale")
async def panel_toggle_locale(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    """Flips this person's own language (#48) — one tap, same weight as the
    profile-links toggle above, and just as undoable.

    Personal, and only ever applies to DMs: a group renders from its own
    `chat_settings.locale`, which no individual member can move. The panel
    is re-rendered in the *new* locale rather than the injected one, which
    the middleware resolved from the old value before this handler ran.
    """
    tg_id = callback.from_user.id
    chosen = next_locale(await repo.user_locale(tg_id))
    await repo.update_user_settings(tg_id, locale=chosen)

    await callback.answer(locale_name(chosen))
    screen = await render_panel(repo, tg_id, locale=chosen)
    await safe_edit(callback, screen.text, screen.keyboard, parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "panel:tz")
async def panel_timezone(callback: CallbackQuery, i18n: I18nContext) -> None:
    # Found while refactoring (2026-09-05): the one edit in this file that
    # didn't tolerate a failed edit, unlike every other one here.
    await safe_edit(
        callback,
        i18n.get("panel-timezone-prompt"),
        timezone_keyboard(i18n, in_panel=True),
    )
    await callback.answer()


# ------------------------------------------------------------------ my chats


@router.callback_query(F.data == "panel:chatlist")
async def panel_chat_list(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    await _redraw_chat_list(callback, repo, i18n)


async def _redraw_chat_list(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    screen = await render_chat_list(repo, callback.from_user.id, locale=i18n.locale)
    await safe_edit(callback, screen.text, screen.keyboard, parse_mode=ParseMode.HTML)
    await callback.answer()


async def _redraw_chat_card(
    callback: CallbackQuery, repo: Repo, chat_id: int, i18n: I18nContext
) -> None:
    screen = await render_chat_card(repo, callback.from_user.id, chat_id, locale=i18n.locale)
    if screen is None:
        await _redraw_chat_list(callback, repo, i18n)
        return
    await safe_edit(callback, screen.text, screen.keyboard, parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(F.data.startswith("panel:chat:"))
async def panel_chat_card(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
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
    screen = await render_unsub_prompt(repo, callback.from_user.id, chat_id, locale=i18n.locale)
    if screen is None:
        await _redraw_chat_list(callback, repo, i18n)
        return
    await safe_edit(callback, screen.text, screen.keyboard, parse_mode=ParseMode.HTML)
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
    screen = await render_chat_delete_prompt(
        repo, callback.from_user.id, chat_id, locale=i18n.locale
    )
    if screen is None:
        await _redraw_chat_list(callback, repo, i18n)
        return
    await safe_edit(callback, screen.text, screen.keyboard, parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(F.data.startswith("panel:chatdely:"))
async def panel_chat_delete_confirm(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    chat_id = int(callback.data.rsplit(":", 1)[1])
    await repo.forget_chat_membership(chat_id, callback.from_user.id)
    await callback.answer(i18n.get("panel-deleted-toast"))
    await _redraw_chat_list(callback, repo, i18n)


@router.callback_query(F.data == "panel:delete_account")
async def panel_delete_account_step1(callback: CallbackQuery, i18n: I18nContext) -> None:
    screen = await render_panel_delete_confirm_1(locale=i18n.locale)
    await safe_edit(callback, screen.text, screen.keyboard, parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(F.data == "panel:delete:step1")
async def panel_delete_account_step2(callback: CallbackQuery, i18n: I18nContext) -> None:
    screen = await render_panel_delete_confirm_2(locale=i18n.locale)
    await safe_edit(callback, screen.text, screen.keyboard, parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(F.data == "panel:delete:step2")
async def panel_delete_account_confirmed(
    callback: CallbackQuery, repo: Repo, i18n: I18nContext
) -> None:
    deleted = await repo.delete_user(callback.from_user.id)
    if deleted:
        await safe_edit(callback, i18n.get("panel-delete-done"), None)
        await callback.answer(i18n.get("panel-delete-toast"), show_alert=True)
    else:
        await safe_edit(callback, i18n.get("panel-delete-done"), None)
        await callback.answer(i18n.get("panel-delete-not-found"), show_alert=True)


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
