"""Daily summary (SPEC 5.7, format 7.3).

Counted entirely from the database — zero API calls. The job wakes up every
minute and asks "is it time yet", because the hour is a setting the admin can
change at runtime; a cron trigger would have to be rebuilt on every change.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from html import escape as html_escape

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.constants import AchievementBadge
from bot.db.repo import ChatMemberStat, ChatTopGame, Repo
from bot.i18n import gettext
from bot.services.achievements import platform_breakdown_suffix, plural_achievements
from bot.services.message_log import stats_category
from bot.services.stats import local_now, month_cutoff_utc
from bot.services.tables import blockquote, total_line, truncate_name
from bot.util import thousands, utcnow

log = logging.getLogger(__name__)

_ = lambda key, **kwargs: gettext("daily", key, **kwargs)  # noqa: E731

DAY_WINDOW_HOURS = 24  # rolling — everyone's "today" is the same 24 hours
# The "month" block is the calendar month (#14): since midnight on the 1st,
# in the chat's own timezone (services/stats.py::month_cutoff_utc). The
# figure resets on the 1st instead of sliding.
TOP_LIMIT_KEY = "summary_top_limit"
DEFAULT_TABLE_TOP = 15
_MONTH_KEYS = (
    "daily-month-01",
    "daily-month-02",
    "daily-month-03",
    "daily-month-04",
    "daily-month-05",
    "daily-month-06",
    "daily-month-07",
    "daily-month-08",
    "daily-month-09",
    "daily-month-10",
    "daily-month-11",
    "daily-month-12",
)


class DailySummary:
    def __init__(self, bot: Bot, repo: Repo) -> None:
        self._bot = bot
        self._repo = repo

    async def tick(self) -> None:
        # Every chat has its own time/zone/threshold in chat_settings (SPEC
        # 5.7), so "is it time yet" is answered separately per chat, not once
        # for everyone.
        for chat in await self._repo.admin_chats():
            if not chat.is_active or not chat.daily_summary:
                continue

            now_local = local_now(chat.tz_offset_min)
            if now_local.strftime("%H:%M") != chat.daily_summary_time:
                continue

            report_date = now_local.date().isoformat()
            if not await self._repo.daily_report_sent(chat.chat_id, report_date):
                await self._send_scheduled(chat, report_date, with_day=True, with_month=False)

            # On the last calendar day of the month, the month-end wrap-up
            # goes out too (#14) — same time, its own dedup marker, and
            # additional to that day's daily summary, not instead of it.
            if _is_last_day_of_month(now_local):
                month_key = _monthly_key(now_local)
                if not await self._repo.daily_report_sent(chat.chat_id, month_key):
                    await self._send_scheduled(chat, month_key, with_day=False, with_month=True)

    async def _send_scheduled(self, chat, marker: str, *, with_day: bool, with_month: bool) -> None:
        now_local = local_now(chat.tz_offset_min)
        built = await build_summary(
            self._repo,
            chat.chat_id,
            chat.rare_threshold_percent,
            now_local.date(),
            tz_offset_min=chat.tz_offset_min,
            with_day=with_day,
            with_month=with_month,
        )
        if built is None:
            # No subscribed members at all — nothing to roster (#34 made a
            # zero-activity day still send). Mark it done so the per-minute
            # tick doesn't keep re-checking.
            await self._repo.mark_daily_report_sent(chat.chat_id, marker)
            return
        text, markup = built
        try:
            with stats_category():
                await self._bot.send_message(
                    chat.chat_id, text, parse_mode=ParseMode.HTML, reply_markup=markup
                )
        except TelegramForbiddenError:
            log.info("chat %s refused the summary, deactivating", chat.chat_id)
            await self._repo.deactivate_chat(chat.chat_id)
            return
        except Exception:
            log.exception("could not send the summary to %s", chat.chat_id)
            return
        await self._repo.mark_daily_report_sent(chat.chat_id, marker)


def _is_last_day_of_month(dt: date) -> bool:
    return (dt + timedelta(days=1)).month != dt.month


def _monthly_key(dt: date) -> str:
    """The daily_reports marker for a month-end wrap-up — deliberately not a
    valid ISO date, so it can't collide with a real daily marker."""
    return f"{dt.year:04d}-{dt.month:02d}-monthly"


async def current_top_limit(repo: Repo) -> int:
    return await repo.get_int_setting(TOP_LIMIT_KEY, DEFAULT_TABLE_TOP)


async def build_summary(
    repo: Repo,
    chat_id: int,
    threshold: float,
    today: date,
    *,
    tz_offset_min: int | None = None,
    with_day: bool = True,
    with_month: bool = True,
) -> tuple[str, InlineKeyboardMarkup | None] | None:
    """The leaderboard report, composed from independent window blocks so
    the three triggers stay in one style (#14):

    - the scheduled daily job asks for the day block only;
    - the month-end job (last calendar day of the month) asks for the month
      block only, under a "Итоги за месяц" header;
    - `/summary` on demand asks for both.

    Every block lists everyone subscribed, zero-scorers included, so it reads
    as a roster; a day nobody unlocked anything still sends (#34). Returns
    None only when the chat has no subscribed members at all.
    """
    top_limit = await current_top_limit(repo)
    # (kind, section_lines, has_more) — kind drives the «показать всех» button.
    blocks: list[tuple[str, list[str], bool]] = []

    if with_day:
        day_cutoff = utcnow() - timedelta(hours=DAY_WINDOW_HOURS)
        rows = await repo.chat_member_stats(chat_id, day_cutoff, threshold)
        if not rows:
            return None
        blocks.append(("day", *_section(_("daily-window-day"), rows, top_limit, show_rare=False)))

    if with_month:
        month_cutoff = month_cutoff_utc(tz_offset_min)
        rows = await repo.chat_member_stats(chat_id, month_cutoff, threshold)
        if not rows:
            if not blocks:
                return None  # month-only report for a chat with no members
        else:
            blocks.append(("month", *_section(_month_window_label(tz_offset_min), rows, top_limit)))
            # #7: which games the chat actually played this month, not just
            # who — its own block, only when there's something to show (a
            # month of zero-scorers has nothing to rank).
            games = await repo.chat_top_games(chat_id, month_cutoff, top_limit)
            if games:
                blocks.append(("games", _games_section(games), False))

    if not blocks:
        return None

    header = (
        _("daily-header", day=today.day, month=_(_MONTH_KEYS[today.month - 1]))
        if with_day
        else _("daily-monthly-header")
    )
    lines = [header]
    for _kind, section_lines, _more in blocks:
        lines += ["", *section_lines]

    button_for = {
        "day": ("daily-show-all-day", "summary:all:day"),
        "month": ("daily-show-all-month", "summary:all:month"),
    }
    buttons = [
        InlineKeyboardButton(text=_(button_for[kind][0]), callback_data=button_for[kind][1])
        for kind, _section_lines, has_more in blocks
        if has_more
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=[[b] for b in buttons]) if buttons else None
    return "\n".join(lines), markup


async def full_leaderboard(
    repo: Repo, chat_id: int, threshold: float, window: str, tz_offset_min: int | None = None
) -> str | None:
    """The uncapped list behind a summary's «Показать всех» button (SPEC
    6.3) — re-fetched fresh rather than carried over from the original send,
    same as /hltb's sessions do for their own "current data" reasons."""
    cutoff = (
        utcnow() - timedelta(hours=DAY_WINDOW_HOURS)
        if window == "day"
        else month_cutoff_utc(tz_offset_min)
    )
    rows = await repo.chat_member_stats(chat_id, cutoff, threshold)
    if not rows:
        return None
    # limit=len(rows): never truncate here — this is the "show everything"
    # view; expandable=False for the same reason (SPEC 6.3).
    section_lines, _full = _section(
        _("daily-leaderboard-total-label"),
        rows,
        limit=len(rows),
        expandable=False,
        show_rare=window != "day",
    )
    label = _("daily-window-day") if window == "day" else _month_window_label(tz_offset_min)
    return "\n".join([_("daily-leaderboard-full-header", label=label), "", *section_lines])


def _month_window_label(tz_offset_min: int | None) -> str:
    """ "С 1 июня" (#6, user request) instead of a static "этот месяц" —
    names the actual calendar month the window covers, in the same
    genitive-case month names "{day} {month}" (daily-header) already uses.
    The *current* local month is always the one month_cutoff_utc's "since
    the 1st" points at, so no need to re-derive it from the cutoff itself."""
    month = local_now(tz_offset_min).month
    return _("daily-window-month", month=_(_MONTH_KEYS[month - 1]))


def _section(
    label: str,
    rows: list[ChatMemberStat],
    limit: int,
    *,
    expandable: bool = True,
    show_rare: bool = True,
) -> tuple[list[str], bool]:
    """The totals line comes first, then the list — reversed from the old
    table-then-total order, so the headline number reads before you tap the
    list open (SPEC 6.3, 7.3). `limit == 0` means "no cap" (admin-configured,
    6.4) — a list this long only ever lives inside a collapsible quote, so
    there is nothing left to truncate for.

    `show_rare=False` (day block, #9 user request) drops the 💎N rare-count
    tail from each row — the month block (where it still shows) is a longer
    window a rare pull is more worth calling out in; a single day's list
    reads better without it.
    """
    total = sum(row.count for row in rows)
    score = sum(row.score for row in rows)
    summary = total_line(label, f"{plural_achievements(total)}, +{thousands(score)} G")
    capped = rows if limit == 0 else rows[:limit]
    rows_block = blockquote(
        [_leader_row(place, row, show_rare=show_rare) for place, row in enumerate(capped, start=1)],
        expandable=expandable,
    )
    has_more = limit != 0 and len(rows) > limit
    return [summary, rows_block], has_more


def _leader_row(place: int, row: ChatMemberStat, *, show_rare: bool = True) -> str:
    name = html_escape(truncate_name(row.gamertag or f"id{row.tg_id}"))
    tail = f" {AchievementBadge.DIAMOND}{row.rare}" if show_rare and row.rare else ""
    breakdown = platform_breakdown_suffix(
        row.xbox_count, row.steam_count, row.psn_count, always=True
    )
    return (
        f"{place}. {name} — {plural_achievements(row.count)}{tail}{breakdown}"
        f" (+{thousands(row.score)} G)"
    )


def _games_section(games: list[ChatTopGame]) -> list[str]:
    """The monthly summary's own new block (#7, user request): which games
    the chat actually played this month, ranked by achievements/trophies
    earned in each — not who, `_section` above's own job. No "show all"
    button of its own (unlike `_section`'s people list) — `chat_top_games`
    is already capped by the same admin-configured `summary_top_limit`
    (SPEC 6.4), and a second uncapped view for this one block wasn't asked
    for. Not truncated (user request, 2026-09-08, same reasoning /stats'
    own games list uses) — it already lives inside its own collapsible
    quote, so a long title wrapping onto a second line costs nothing."""
    rows = [
        f"{place}. {html_escape(game.name or _('daily-unknown-game'))} — "
        f"{plural_achievements(game.count)}"
        for place, game in enumerate(games, start=1)
    ]
    return [_("daily-games-header"), blockquote(rows)]
