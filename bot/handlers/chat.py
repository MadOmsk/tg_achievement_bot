"""Group commands (SPEC 6.3). UI only — no SQL outside repo, no API calls."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from html import escape as html_escape
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
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram_i18n import I18nContext

from bot.constants import SettingKey
from bot.db.repo import (
    ChatPresenceRow,
    PlatformLink,
    RecentAchievement,
    Repo,
    TopGame,
    User,
)
from bot.handlers.admin import IsAdmin
from bot.i18n import DEFAULT_LOCALE, gettext
from bot.poller.daily import build_summary, full_leaderboard
from bot.poller.online_refresh import refresh_interval_minutes
from bot.services.achievements import (
    PLATFORM_ICON,
    PLATFORM_ICON_UNKNOWN,
    platform_breakdown_suffix,
    platform_header_lines,
    plural_achievements,
    rarity_badge,
    score_suffix,
)
from bot.services.message_log import stats_category
from bot.services.naming import (
    person_name,
    person_name_of,
    subscriber_names,
    xbox_nickname,
)
from bot.services.online_view import render_online_table
from bot.services.single_message import send_replacing
from bot.services.stats import counters_for, local_now
from bot.services.tables import blockquote, truncate_name
from bot.util import humanize_ago, thousands, utcnow

log = logging.getLogger(__name__)

router = Router(name="chat")


def _hub_text(i18n: I18nContext | None, key: str, **kwargs: object) -> str:
    return (
        i18n.get(key, **kwargs)
        if i18n is not None
        else gettext("chat", key, locale=DEFAULT_LOCALE, **kwargs)
    )


def _locale_of(i18n: I18nContext | None) -> str:
    """The locale this render belongs to (#48). In a group the middleware has
    already resolved `i18n.locale` to that chat's own setting, which is
    exactly what everything built here needs; the None case is the handful of
    internal callers that render without an aiogram context at all."""
    return i18n.locale if i18n is not None else DEFAULT_LOCALE


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


RECENT_GAMES_DAYS = 30
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


def _games_list(games: list[TopGame], i18n: I18nContext | None = None) -> str:
    rows = []
    for place, game in enumerate(games, start=1):
        untitled = _hub_text(i18n, "chat-untitled")
        tail = _hub_text(
            i18n,
            "chat-stats-game-row-tail",
            count=game.unlocked or 0,
            score_suffix=score_suffix(game.gamerscore or 0),
        )
        # Not truncated (2026-09-08, user request) — unlike /recent's row
        # below, this list already lives inside its own collapsible quote,
        # so a long title wrapping onto a second line costs nothing a
        # scrollable phone screen can't handle.
        rows.append(
            f"{place}. {PLATFORM_ICON.get(game.platform, '')} "
            f"{html_escape(game.name or untitled)} — {tail}"
        )
    return blockquote(rows)


def _display_name(target: User, links: list[PlatformLink]) -> str:
    """The Telegram identity, not a platform gamertag (Follow-up
    2026-09-06, user request) — the card already lists every connected
    platform's own name on its own line below (XBOX/Steam/PSN), so the
    header identifying *the person* rather than defaulting to whichever
    platform happened to be Xbox reads better once someone has more than
    one. first_name/last_name only exist once UsernameMiddleware (below)
    has seen at least one message from them — a brand-new /start with
    nothing yet falls through to a platform name as a last resort.

    One of four hand-rolled versions of this chain until #51; now just the
    shared one, handed whichever platform links this person happens to
    have."""
    return person_name_of(target, links)


def _who_label(row: ChatPresenceRow) -> str:
    """/who's picker button (#40) — identify *the person*, the same chain
    /stats' header uses, never a bare "idNNNN" for someone who has anything
    else. `chat_member_presence` already carries every field it needs (the
    #38 /online work joined them in), so no extra lookup per row."""
    return person_name(
        tg_id=row.tg_id,
        first_name=row.first_name,
        last_name=row.last_name,
        username=row.username,
        xbox=xbox_nickname(gamertag_modern=row.gamertag_modern, gamertag=row.gamertag),
        steam=row.steam_display_name,
        psn=row.psn_display_name,
    )


async def _build_stats_text(
    repo: Repo, target: User, i18n: I18nContext | None = None
) -> str | None:
    """Shared by /stats and /who's buttons (SPEC 6.3) — one implementation,
    so a player's card looks the same no matter how it was opened.

    Works for a Steam-only person too (SPEC 9, M-Steam-2e) — used to bail
    out on `not target.xuid` alone, which meant no card at all for anyone
    without Xbox connected."""
    platform_links = await repo.platform_links_of(target.tg_id)
    if not target.xuid and not platform_links:
        return None

    # Gates whether any nickname below becomes a clickable link at all — the
    # target's own choice (Follow-up 2026-09-06), off by default, and not
    # relaxed for the target viewing their own card: this card is one and
    # the same message regardless of who asked for it (no per-viewer
    # rendering), so "only hide it from others" isn't a distinction that
    # exists here. Own links live in /panel instead, which really is
    # per-viewer (never rendered in a group at all).
    settings_row = await repo.get_user_settings(target.tg_id)
    show_links = bool(settings_row and settings_row.show_profile_links)

    locale = _locale_of(i18n)
    counters = await counters_for(repo, target.tg_id)
    lines = [f"📊 <b>{html_escape(_display_name(target, platform_links))}</b>"]
    # Shared with /panel's own header (2026-09-08, user request: "пусть одни
    # одинаково формируются") — services/achievements.py::platform_header_lines.
    lines += await platform_header_lines(
        repo,
        tg_id=target.tg_id,
        xuid=target.xuid,
        gamertag=target.gamertag,
        gamerscore=target.gamerscore,
        platform_links=platform_links,
        show_links=show_links,
        locale=locale,
    )

    today_breakdown = platform_breakdown_suffix(
        counters.today_xbox, counters.today_steam, counters.today_psn
    )
    month_breakdown = platform_breakdown_suffix(
        counters.month_xbox, counters.month_steam, counters.month_psn
    )
    lines += [
        "",
        _hub_text(
            i18n,
            "chat-stats-today",
            achievements=plural_achievements(counters.today, locale),
            breakdown=today_breakdown,
            score_suffix=score_suffix(counters.today_score),
        ),
        _hub_text(
            i18n,
            "chat-stats-month",
            achievements=plural_achievements(counters.month, locale),
            breakdown=month_breakdown,
            score_suffix=score_suffix(counters.month_score),
        ),
        # No lifetime "Всего" here: seen_achievements is permanently
        # best-effort (title_history's cap, achievements with no unlock
        # date), so a lifetime count from it can't be trusted the way a
        # date-bounded one can — better absent than quietly wrong (SPEC 5.4).
    ]

    # Found live, long-standing gap: this used to be Xbox-only (SPEC 9,
    # M-Steam-2c scoped it out for lack of a Steam recently-played source —
    # recent_games() itself was never Xbox-specific, just never called for
    # anything else). One combined ranked list, not a section per platform —
    # same "one number, not one per platform" spirit as the counters above.
    external_ids = [target.xuid] if target.xuid else []
    external_ids += [link.external_id for link in platform_links]
    if external_ids:
        # 0 = no cap (SPEC 6.4) — the list lives in a collapsible quote
        # either way, no separate "показать все игры" tap needed any more.
        limit = await _stats_games_limit(repo)
        since = utcnow() - timedelta(days=RECENT_GAMES_DAYS)
        per_source = await asyncio.gather(
            *(repo.recent_games(external_id, since, limit=limit) for external_id in external_ids)
        )
        games = sorted(
            (game for source in per_source for game in source),
            key=lambda g: (g.gamerscore or 0, g.unlocked or 0),
            reverse=True,
        )[: limit or None]
        if games:
            lines += [
                "",
                _hub_text(i18n, "chat-stats-games-header", days=RECENT_GAMES_DAYS),
                _games_list(games, i18n),
            ]
    return "\n".join(lines)


DEFAULT_STATS_GAMES_LIMIT = 15


async def _stats_games_limit(repo: Repo) -> int:
    return await repo.get_int_setting(SettingKey.STATS_GAMES_LIMIT, DEFAULT_STATS_GAMES_LIMIT)


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
    text = await _build_stats_text(repo, target, i18n)
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
    # has turned the interval down to 0 (services/online_view.py's own
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

    builder = InlineKeyboardBuilder()
    for row in rows:
        builder.button(
            text=_who_label(row),
            callback_data=f"who:stats:{row.tg_id}",
        )
    builder.adjust(3)
    # Found live: no way out except picking someone, and the prompt itself
    # never went away after a pick — just sat there stale.
    builder.row(
        InlineKeyboardButton(text=i18n.get("chat-cancel-button"), callback_data="who:cancel")
    )
    await message.answer(i18n.get("chat-who-prompt"), reply_markup=builder.as_markup())


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
    text = await _build_stats_text(repo, target, i18n)
    await callback.answer()
    if isinstance(callback.message, Message):
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

    rows = await repo.chat_recent(message.chat.id, limit)
    if not rows:
        with stats_category():
            await message.answer(i18n.get("chat-recent-empty"))
        return
    text = i18n.get("chat-recent-header") + "\n" + _recent_list(rows, i18n)
    # Replaces the chat's previous /recent outright (Follow-up 2026-09-06).
    with stats_category():
        await send_replacing(bot, repo, message.chat.id, "recent", text, parse_mode=ParseMode.HTML)


def _recent_list(rows: list[RecentAchievement], i18n: I18nContext | None = None) -> str:
    return blockquote([_recent_row(row, i18n) for row in rows])


def _recent_row(row: RecentAchievement, i18n: I18nContext | None = None) -> str:
    # A real Telegram spoiler works fine inside a blockquote (unlike the old
    # <pre> table it replaced, SPEC 7.1) — the real name stays hidden behind
    # a tap, instead of a placeholder that gave nothing away to look up.
    name = html_escape(truncate_name(row.name))
    if row.is_secret:
        name = f'<span class="tg-spoiler">{name}</span>'
    # Leads the line instead of a fixed "🏆" bullet (2026-09-05) — now that
    # rarity_badge() always returns something (diamond or cup, never
    # empty), a separate generic bullet would double up with it on every
    # "common" row: two trophies back to back on the same line.
    badge = rarity_badge(row.rarity_percent)
    gamertag = html_escape(
        truncate_name(
            person_name(
                tg_id=row.tg_id,
                first_name=row.first_name,
                last_name=row.last_name,
                username=row.username,
                xbox=xbox_nickname(gamertag_modern=row.gamertag_modern, gamertag=row.gamertag),
                steam=row.steam_name,
                psn=row.psn_name,
            )
        )
    )
    game = html_escape(truncate_name(row.game or _hub_text(i18n, "chat-untitled")))
    icon = PLATFORM_ICON.get(row.platform, PLATFORM_ICON_UNKNOWN)
    # Found live: every Steam row showed a flat "+0 G" — Steam achievements
    # have no gamerscore at all (services/steam/achievements.py), same
    # "0 is 0 on any platform, don't name it" rule the achievement message
    # itself already follows (services/achievements.py's _rarity_line).
    # Rarity here is a bare percentage, with no label — the badge
    # already says "rare or not", the number is just the detail behind it.
    tail = []
    if row.gamerscore:
        tail.append(f"+{thousands(row.gamerscore)} G")
    if row.rarity_percent is not None:
        tail.append(f"{row.rarity_percent:g}%")
    tail_text = f" ({' · '.join(tail)})" if tail else ""
    return _hub_text(
        i18n,
        "chat-recent-row",
        badge=badge,
        gamertag=gamertag,
        icon=icon,
        game=game,
        name=name,
        tail=tail_text,
        ago=humanize_ago(row.unlocked_at, _locale_of(i18n)),
    )


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
def hub_keyboard(
    bot_username: str, chat_id: int, i18n: I18nContext | None = None
) -> InlineKeyboardMarkup:
    """A short walkthrough, not a control panel: SPEC 6.3 walks through
    connect → publish in that order, so the keyboard should not offer more
    choices than that story needs. Steam's and PSN's connect buttons
    (SPEC 9, M-Steam-2e, M-PSN-1) sit next to Xbox's rather than adding a
    whole extra row each — it is still the same "connect" step, just
    another platform for it.

    Buttons act on whoever presses them — that is why "Публиковать мои
    достижения" is allowed here at all: SPEC 6.3 forbids rendering *someone
    else's* settings where any member could page through them, not a button
    that only ever touches the presser's own subscription.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_hub_text(i18n, "chat-hub-publish-button"), callback_data="sub:on"
                )
            ],
            [
                InlineKeyboardButton(
                    text=_hub_text(i18n, "chat-hub-xbox-button"),
                    # The chat id rides along in the deep-link payload so a
                    # successful login can auto-subscribe him right back here
                    # (SPEC 6.3) — see _parse_connect_payload in connect.py.
                    url=f"https://t.me/{bot_username}?start=connect{chat_id}",
                ),
                InlineKeyboardButton(
                    text=_hub_text(i18n, "chat-hub-steam-button"),
                    # No chat id here (unlike Xbox above) — /connect_steam
                    # needs a profile link a button tap can't supply anyway,
                    # so this just opens the DM at the right prompt (SPEC 9,
                    # handlers/steam.py, connect.py's ?start=connectsteam).
                    url=f"https://t.me/{bot_username}?start=connectsteam",
                ),
                InlineKeyboardButton(
                    text=_hub_text(i18n, "chat-hub-psn-button"),
                    # Same reasoning as Steam's own button above (SPEC 9,
                    # M-PSN-1, handlers/psn.py, connect.py's ?start=connectpsn).
                    url=f"https://t.me/{bot_username}?start=connectpsn",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_hub_text(i18n, "chat-hub-settings-button"),
                    url=f"https://t.me/{bot_username}?start=panel",
                ),
            ],
        ]
    )


async def hub_text(repo: Repo, chat_id: int, i18n: I18nContext) -> str:
    names = subscriber_names(await repo.chat_subscribers(chat_id))
    if not names:
        return i18n.get("chat-help-text") + "\n\n" + i18n.get("chat-hub-nobody")
    return (
        i18n.get("chat-help-text")
        + "\n\n"
        + i18n.get("chat-hub-publishing", names=", ".join(names))
    )


@router.message(Command("help"))
async def help_command(message: Message, repo: Repo, bot: Bot, i18n: I18nContext) -> None:
    if message.chat.type not in GROUP_TYPES:
        await message.answer(i18n.get("chat-help-text"))
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
