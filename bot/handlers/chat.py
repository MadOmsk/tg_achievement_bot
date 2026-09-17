"""Group commands (SPEC 6.3). UI only — no SQL outside repo, no API calls."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot, F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import (
    IS_MEMBER,
    IS_NOT_MEMBER,
    ChatMemberUpdatedFilter,
    Command,
    CommandObject,
)
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)
from aiogram_i18n import I18nContext

from bot.db.repo import (
    Repo,
    User,
)
from bot.handlers.admin import IsAdmin
from bot.poller.online_refresh import refresh_interval_minutes
from bot.services.message_log import stats_category
from bot.services.naming import (
    person_name_of,
)
from bot.services.single_message import send_replacing
from bot.services.stats import local_now
from bot.views.chat import (
    build_stats_text,
    help_text,
    hub_keyboard,
    hub_text,
    recent_list,
    render_who_picker,
)
from bot.views.online import render_online_table
from bot.views.summary import build_summary, full_leaderboard

log = logging.getLogger(__name__)

router = Router(name="chat")


GROUP_TYPES = {ChatType.GROUP, ChatType.SUPERGROUP}

# subscribe/unsubscribe is a check-then-act (is_subscribed, then write) —
# without a lock, a fast confirm-then-/subscribe (or a double-tapped button)
# could interleave across two concurrently-handled updates and read stale
# state. Same pattern as the per-user lock around token refresh
# (bot/services/xbox/auth.py) — keyed by (chat_id, tg_id), not just tg_id,
# since a subscription is scoped to one chat.
_subscription_locks: dict[tuple[int, int], asyncio.Lock] = {}


def _subscription_lock(chat_id: int, tg_id: int) -> asyncio.Lock:
    return _subscription_locks.setdefault((chat_id, tg_id), asyncio.Lock())


RECENT_DEFAULT = 5
RECENT_MAX = 20


class UsernameMiddleware(BaseMiddleware):
    """Keep users.username fresh, and note who's been seen writing in a group
    (`chat_seen` — feeds /online, SPEC 6.3).

    Only existing rows are touched: a group member who never talked to the bot
    should not get a user record just for writing a message.
    """

    def __init__(self, repo: Repo) -> None:
        self._repo = repo

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.from_user:
            if event.from_user.username:
                await self._repo.update_username(event.from_user.id, event.from_user.username)
            # first_name always exists for a real Telegram account, unlike
            # username above — unconditional (Follow-up 2026-09-06, /stats'
            # header identity).
            await self._repo.update_names(
                event.from_user.id, event.from_user.first_name, event.from_user.last_name
            )
            if event.chat.type in GROUP_TYPES:
                await self._repo.record_chat_seen(event.chat.id, event.from_user.id)
        return await handler(event, data)


# ------------------------------------------------------------- subscription


@router.message(Command("subscribe"))
async def subscribe(message: Message, repo: Repo, i18n: I18nContext) -> None:
    if message.chat.type not in GROUP_TYPES:
        await message.answer(i18n.get("chat-subscribe-groups-only"))
        return
    if message.from_user is None:
        return

    user = await repo.get_user(message.from_user.id)
    # Found live (2026-09-08, keimaks/kmaks90 — PSN-only, confirmed bug):
    # this used to require Xbox specifically (`not user.xuid` alone), so a
    # Steam/PSN-only person could never subscribe anywhere at all — not a
    # design choice, just this handler never learning about the other two
    # platforms the rest of the bot has long since supported.
    platform_links = await repo.platform_links_of(message.from_user.id) if user else []
    if user is None or (not user.xuid and not platform_links):
        me = await message.bot.me()  # type: ignore[union-attr]
        await message.answer(
            i18n.get("chat-subscribe-connect-first"),
            reply_markup=hub_keyboard(me.username or "", message.chat.id, i18n),
        )
        return

    await repo.upsert_chat(message.chat.id, message.chat.title, message.from_user.id)
    async with _subscription_lock(message.chat.id, message.from_user.id):
        if await repo.is_subscribed(message.chat.id, message.from_user.id):
            await message.answer(i18n.get("chat-subscribe-already"))
            return
        await repo.subscribe(message.chat.id, message.from_user.id)
    await message.answer(
        i18n.get(
            "chat-subscribe-done",
            # The person, not their Xbox account (#51) — this read
            # `user.gamertag`, so anyone without Xbox got the generic
            # "твои достижения" instead of their own name.
            gamertag=person_name_of(user, await repo.platform_links_of(message.from_user.id)),
        )
    )


@router.message(Command("unsubscribe"))
async def unsubscribe(message: Message, repo: Repo, i18n: I18nContext) -> None:
    """Same weight as /disconnect_xbox: losing your feed in a chat you might not
    remember subscribing in deserves a confirm, not an instant action."""
    if message.chat.type not in GROUP_TYPES or message.from_user is None:
        return
    if not await repo.is_subscribed(message.chat.id, message.from_user.id):
        await message.answer(i18n.get("chat-unsubscribe-not-subscribed"))
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("chat-unsubscribe-confirm-button"),
                    callback_data=f"unsub:yes:{message.from_user.id}",
                )
            ],
            [InlineKeyboardButton(text=i18n.get("chat-cancel-button"), callback_data="unsub:no")],
        ]
    )
    await message.answer(i18n.get("chat-unsubscribe-prompt"), reply_markup=keyboard)


@router.callback_query(F.data == "unsub:no")
async def unsubscribe_cancel(callback: CallbackQuery) -> None:
    # Nothing changed — remove the prompt instead of leaving a "cancelled"
    # message in the group chat for no reason.
    if isinstance(callback.message, Message):
        with contextlib.suppress(Exception):
            await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data.startswith("unsub:yes:"))
async def unsubscribe_confirm(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    assert callback.data is not None
    tg_id = int(callback.data.rsplit(":", 1)[1])
    # The confirm buttons are visible to the whole group, not just the person
    # who ran /unsubscribe — without this check anyone could confirm or
    # cancel someone else's unsubscribe.
    if callback.from_user.id != tg_id:
        await callback.answer(i18n.get("chat-not-your-button"), show_alert=True)
        return
    if not isinstance(callback.message, Message):
        return
    async with _subscription_lock(callback.message.chat.id, tg_id):
        await repo.unsubscribe(callback.message.chat.id, tg_id)
    await callback.message.edit_text(i18n.get("chat-unsubscribe-done"))
    await callback.answer()


# -------------------------------------------------------------------- stats


async def _send_stats_card(bot: Bot, repo: Repo, chat_id: int, target: User, text: str) -> None:
    """Shared by /stats and /who's button (Follow-up 2026-09-08) — one
    implementation, so a Telegram-level send option (like the line below)
    only needs to be right in one place. Keyed by the person the card is
    *about*, not who asked (Follow-up 2026-09-06) — same person's stats
    posted twice in this chat replaces the old copy, whether both came from
    /stats or one came from /who.

    disable_web_page_preview (found live, 2026-09-08): a card with
    show_profile_links on embeds a real <a href> — without this, Telegram
    attaches a link-preview card under the message for whichever profile
    URL it finds first, which connect.py's and panel.py's own links already
    guard against, this one just never had.
    """
    with stats_category():
        await send_replacing(
            bot,
            repo,
            chat_id,
            "stats",
            text,
            subject_id=target.tg_id,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


@router.message(Command("stats"))
async def stats(
    message: Message, repo: Repo, bot: Bot, command: CommandObject, i18n: I18nContext
) -> None:
    target = await _resolve(message, repo, command.args)
    if target is None:
        with stats_category():
            await message.answer(i18n.get("chat-unknown-user"))
        return
    text = await build_stats_text(repo, target, message.chat.id, i18n)
    if text is None:
        with stats_category():
            await message.answer(i18n.get("chat-stats-nothing-connected"))
        return
    await _send_stats_card(bot, repo, message.chat.id, target, text)


# --------------------------------------------------------------------- online


@router.message(Command("online"))
async def online(message: Message, repo: Repo, bot: Bot, i18n: I18nContext) -> None:
    if message.chat.type not in GROUP_TYPES:
        await message.answer(i18n.get("chat-group-command-only"))
        return

    rows = await repo.chat_member_presence(message.chat.id)
    if not rows:
        with stats_category():
            await message.answer(i18n.get("chat-online-empty"))
        return

    # A fresh /online replaces whatever was posted/auto-refreshing before
    # (Follow-up 2026-09-06) — the old snapshot has already scrolled away
    # and nobody scrolls back for it. Best-effort: an already-gone message
    # (age, a manual delete, the chat's own bot-message wipe) is exactly as
    # fine to fail on as one that was never there.
    previous = await repo.get_online_auto_refresh(message.chat.id)
    if previous is not None:
        with contextlib.suppress(Exception):
            await bot.delete_message(message.chat.id, previous.message_id)

    # Plain text, no per-name buttons: a keyboard row per player stops being a
    # list and starts being a second keyboard once a chat has more than a
    # few people. Picking someone to look up is /who's job, not this one's.
    settings_row = await repo.get_chat_daily_settings(message.chat.id)
    updated_label = local_now(settings_row.tz_offset_min).strftime("%H:%M")
    text = render_online_table(rows, updated_label, settings_row.locale)
    with stats_category():
        sent = await message.answer(text, parse_mode=ParseMode.HTML)

    # Follow-up 2026-09-05: /online now keeps itself fresh for a while
    # instead of being a one-off snapshot — skipped entirely when the admin
    # has turned the interval down to 0 (views/online.py's own
    # render is still exactly what a manual re-run would produce). The old
    # row is dropped either way (not just left stale) so a later interval
    # change doesn't suddenly revive a pointer to a message this deleted.
    if await refresh_interval_minutes(repo) > 0:
        await repo.start_online_auto_refresh(message.chat.id, sent.message_id)
    elif previous is not None:
        await repo.delete_online_auto_refresh(message.chat.id)


@router.message(Command("who"))
async def who(message: Message, repo: Repo, i18n: I18nContext) -> None:
    """The picker /online used to double as (SPEC 6.3) — split out so /online
    can stay a plain glance and this can stay a plain button grid."""
    if message.chat.type not in GROUP_TYPES:
        await message.answer(i18n.get("chat-group-command-only"))
        return

    rows = await repo.chat_member_presence(message.chat.id)
    if not rows:
        await message.answer(i18n.get("chat-online-empty"))
        return

    await message.answer(
        i18n.get("chat-who-prompt"),
        reply_markup=render_who_picker(rows, i18n),
    )


@router.callback_query(F.data == "who:cancel")
async def who_cancel(callback: CallbackQuery) -> None:
    if isinstance(callback.message, Message):
        with contextlib.suppress(Exception):
            await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data.startswith("who:stats:"))
async def who_stats_button(
    callback: CallbackQuery, repo: Repo, bot: Bot, i18n: I18nContext
) -> None:
    assert callback.data is not None
    tg_id = int(callback.data.rsplit(":", 1)[1])
    target = await repo.get_user(tg_id)
    if target is None:
        await callback.answer(i18n.get("chat-user-not-found"), show_alert=True)
        return
    # The card is built inside the isinstance guard now: it needs the chat
    # this was pressed in (the rarity threshold is per chat), and
    # `callback.message` is only guaranteed to carry one here.
    await callback.answer()
    if isinstance(callback.message, Message):
        text = await build_stats_text(repo, target, callback.message.chat.id, i18n)
        if text is not None:
            await _send_stats_card(bot, repo, callback.message.chat.id, target, text)
        # The picker's own job is done either way — drop it instead of
        # leaving a stale who-is-this prompt behind.
        with contextlib.suppress(Exception):
            await callback.message.delete()


# ------------------------------------------------------------------- summary


async def _summary(
    repo: Repo, chat_id: int, *, with_day: bool = True, with_month: bool = True
) -> tuple[str | None, InlineKeyboardMarkup | None]:
    """The report, however it was asked for — one set of numbers no matter
    which command triggered it.

    There is no rate limit (2026-09-12, user request: the ten-minute one got
    in the way more than it protected). /summary replaces the chat's own
    previous copy instead of stacking, which is what kept repeated asks from
    piling up in the first place.

    `with_day`/`with_month` (2026-09-08, user request) let /summary_day and
    /summary_month ask for one block only, from the same report /summary's
    own "both" call builds.
    """
    settings_row = await repo.get_chat_daily_settings(chat_id)
    built = await build_summary(
        repo,
        chat_id,
        settings_row.rare_threshold_percent,
        local_now(settings_row.tz_offset_min).date(),
        locale=settings_row.locale,
        tz_offset_min=settings_row.tz_offset_min,
        with_day=with_day,
        with_month=with_month,
    )
    return built if built is not None else (None, None)


async def _run_summary_command(
    message: Message, repo: Repo, bot: Bot, i18n: I18nContext, *, with_day: bool, with_month: bool
) -> None:
    if message.chat.type not in GROUP_TYPES:
        await message.answer(i18n.get("chat-summary-group-only"))
        return

    text, markup = await _summary(repo, message.chat.id, with_day=with_day, with_month=with_month)
    if text is None:
        with stats_category():
            await message.answer(i18n.get("chat-summary-empty"))
        return
    # Replaces the chat's previous /summary outright (Follow-up 2026-09-06)
    # — an "nothing new" reply just above is left untouched on purpose:
    # it isn't itself worth keeping around, but it also shouldn't erase a
    # real summary from earlier that still has something to show.
    with stats_category():
        await send_replacing(
            bot,
            repo,
            message.chat.id,
            "summary",
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )


@router.message(Command("summary"))
async def summary_command(message: Message, repo: Repo, bot: Bot, i18n: I18nContext) -> None:
    """The same report the scheduled job sends, on demand."""
    await _run_summary_command(message, repo, bot, i18n, with_day=True, with_month=True)


@router.message(Command("summary_day"))
async def summary_day_command(message: Message, repo: Repo, bot: Bot, i18n: I18nContext) -> None:
    """The day block only (2026-09-08, user request) — deliberately left out
    of /help and chat-help-text: a testing/diagnostic entry point for the
    #14 block split, not a command meant for everyday use alongside /summary
    itself."""
    await _run_summary_command(message, repo, bot, i18n, with_day=True, with_month=False)


@router.message(Command("summary_month"))
async def summary_month_command(message: Message, repo: Repo, bot: Bot, i18n: I18nContext) -> None:
    """The month block only — see summary_day_command above for why this
    stays out of the help text."""
    await _run_summary_command(message, repo, bot, i18n, with_day=False, with_month=True)


@router.callback_query(F.data.startswith("summary:all:"))
async def summary_show_all(callback: CallbackQuery, repo: Repo, i18n: I18nContext) -> None:
    """«Показать всех» under a truncated summary table — a fresh, uncapped
    re-fetch as its own message, not the original send re-edited (SPEC 6.3)."""
    if not isinstance(callback.message, Message):
        return
    assert callback.data is not None
    window = callback.data.rsplit(":", 1)[1]
    settings_row = await repo.get_chat_daily_settings(callback.message.chat.id)
    text = await full_leaderboard(
        repo,
        callback.message.chat.id,
        settings_row.rare_threshold_percent,
        window,
        settings_row.tz_offset_min,
        locale=settings_row.locale,
    )
    await callback.answer()
    if text is not None:
        with stats_category():
            await callback.message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("recent"))
async def recent(
    message: Message, repo: Repo, bot: Bot, command: CommandObject, i18n: I18nContext
) -> None:
    if message.chat.type not in GROUP_TYPES:
        await message.answer(i18n.get("chat-recent-group-only"))
        return

    limit = RECENT_DEFAULT
    if command.args and command.args.strip().isdigit():
        limit = max(1, min(int(command.args.strip()), RECENT_MAX))

    rows = await repo.chat_recent(message.chat.id, limit, locale=i18n.locale)
    if not rows:
        with stats_category():
            await message.answer(i18n.get("chat-recent-empty"))
        return
    text = i18n.get("chat-recent-header") + "\n" + recent_list(rows, i18n)
    # Replaces the chat's previous /recent outright (Follow-up 2026-09-06).
    with stats_category():
        await send_replacing(bot, repo, message.chat.id, "recent", text, parse_mode=ParseMode.HTML)


async def _resolve(message: Message, repo: Repo, argument: str | None) -> User | None:
    """Find who the command is about: reply, mention, @username or the sender."""
    if message.reply_to_message and message.reply_to_message.from_user:
        return await repo.get_user(message.reply_to_message.from_user.id)

    for entity in message.entities or []:
        if entity.type == "text_mention" and entity.user:
            return await repo.get_user(entity.user.id)

    if argument:
        return await repo.find_user_by_username(argument.strip())

    return await repo.get_user(message.from_user.id) if message.from_user else None


# ---------------------------------------------------------------------- hub


# Rewritten 2026-09-05: no connect/subscribe walkthrough in the text any
# more — the hub's own buttons (hub_keyboard, below) already cover both,
# intuitively enough on their own that spelling them out here was just
# noise by comparison to what people actually come back to read: what the
# bot is, and the commands.


@router.message(Command("help"))
async def help_command(message: Message, repo: Repo, bot: Bot, i18n: I18nContext) -> None:
    if message.chat.type not in GROUP_TYPES:
        await message.answer(help_text(i18n))
        return
    me = await bot.me()
    await message.answer(
        await hub_text(repo, message.chat.id, i18n),
        reply_markup=hub_keyboard(me.username or "", message.chat.id, i18n),
    )


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> IS_MEMBER))
async def greet_new_chat(event: ChatMemberUpdated, repo: Repo, bot: Bot, i18n: I18nContext) -> None:
    """Say what to do the moment the bot lands in a group, not later."""
    if event.chat.type not in GROUP_TYPES:
        return
    await repo.upsert_chat(event.chat.id, event.chat.title, event.from_user.id)
    me = await bot.me()
    await bot.send_message(
        event.chat.id,
        await hub_text(repo, event.chat.id, i18n),
        reply_markup=hub_keyboard(me.username or "", event.chat.id, i18n),
    )


@router.callback_query(F.data == "sub:on")
async def subscribe_button(
    callback: CallbackQuery, repo: Repo, bot: Bot, i18n: I18nContext
) -> None:
    message = callback.message
    if not isinstance(message, Message):
        return
    user = await repo.get_user(callback.from_user.id)
    # Same fix as /subscribe above (2026-09-08, confirmed live bug) — only
    # redirect to connect when *nothing* is linked; a Steam/PSN-only person
    # should just subscribe outright, not get bounced to Xbox forever.
    platform_links = await repo.platform_links_of(callback.from_user.id) if user else []
    if user is None or (not user.xuid and not platform_links):
        # A callback answer can only carry one URL, unlike /subscribe's own
        # reply keyboard above — Xbox's own deep link stays the default
        # here (it auto-subscribes back to this chat once connected, SPEC
        # 6.3), but Steam/PSN are one tap away too via a real message.
        me = await bot.me()
        await callback.answer(url=f"https://t.me/{me.username}?start=connect{message.chat.id}")
        await message.answer(
            i18n.get("chat-subscribe-connect-first"),
            reply_markup=hub_keyboard(me.username or "", message.chat.id, i18n),
        )
        return

    await repo.upsert_chat(message.chat.id, message.chat.title, callback.from_user.id)
    async with _subscription_lock(message.chat.id, callback.from_user.id):
        if await repo.is_subscribed(message.chat.id, callback.from_user.id):
            await callback.answer(i18n.get("chat-subscribe-already"))
            return
        await repo.subscribe(message.chat.id, callback.from_user.id)
    await callback.answer(i18n.get("chat-subscribe-button-done"))
    await _refresh_hub(message, repo, bot, i18n)


async def _refresh_hub(message: Message, repo: Repo, bot: Bot, i18n: I18nContext) -> None:
    me = await bot.me()
    with contextlib.suppress(Exception):
        # Telegram refuses an edit that changes nothing — not an error.
        await message.edit_text(
            await hub_text(repo, message.chat.id, i18n),
            reply_markup=hub_keyboard(me.username or "", message.chat.id, i18n),
        )


@router.message(Command("delete_last"), F.chat.type.in_(GROUP_TYPES), IsAdmin())
async def delete_last(message: Message, repo: Repo, bot: Bot, i18n: I18nContext) -> None:
    """Quick undo, right in the chat — the admin panel's own "стереть
    сообщения бота" (admin.py's a:cwipe) is a 24-hour bulk wipe reached
    through a private-chat menu, overkill for "oops, wrong one just now".
    IsAdmin (admin.py) is the bot's own admin_tg_ids, same as everywhere
    else "admin" means in this project — not generic Telegram chat admins.

    Targets the last *non-system* message (2026-09-05 follow-up) — a system
    message a few seconds old is already about to clean itself up, and
    "oops, wrong one just now" is almost always about an actual result
    (an achievement post, a stats reply), not a prompt or a confirmation.

    The success reply names what it deleted (2026-09-09 user request,
    `bot_messages.preview`) instead of staying silent — the old silent
    version made repeated presses hard to trust: nothing confirmed each one
    actually moved to the *previous* message rather than repeating or
    getting stuck.
    """
    target = await repo.last_non_system_bot_message(message.chat.id)
    if target is None:
        await message.answer(i18n.get("chat-delete-last-none"))
        return

    try:
        await bot.delete_message(message.chat.id, target.message_id)
    except Exception:
        # Too old (Telegram caps deletes at 48h) or already gone either way
        # — same reasoning as the bulk wipe, nothing left worth keeping the
        # log row for.
        log.info("delete_last failed for chat %s message %s", message.chat.id, target.message_id)
        await repo.forget_bot_messages(message.chat.id, [target.message_id])
        await message.answer(i18n.get("chat-delete-last-failed"))
        return

    await repo.forget_bot_messages(message.chat.id, [target.message_id])
    if target.preview:
        await message.answer(i18n.get("chat-delete-last-done", preview=target.preview))
    else:
        await message.answer(i18n.get("chat-delete-last-done-generic"))
    with contextlib.suppress(Exception):
        await message.delete()  # tidy up the /delete_last command itself too
