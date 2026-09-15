"""The daily and month-end summaries (#63).

Three shapes out of two independent window blocks (#14): the scheduled
daily job sends the day block, the month-end job the month block under its
own header, and /summary on demand sends both. Composed rather than written
three times, so their style cannot drift apart.

poller/daily.py keeps the schedule — whose summary is due, in which chat,
at which local hour — and the sending.
"""

from __future__ import annotations

from datetime import date, timedelta
from html import escape as html_escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.constants import AchievementBadge, Platform, PsnTrophyTier
from bot.db.repo import ChatMemberStat, ChatTopGame, Repo
from bot.i18n import translator
from bot.services.admin_settings import DEFAULT_TABLE_TOP, TOP_LIMIT_KEY
from bot.services.naming import person_name, xbox_nickname
from bot.services.stats import local_now, month_cutoff_utc
from bot.util import thousands, utcnow
from bot.views.parts import (
    PLATFORM_ICON,
    TROPHY_TIER_BADGE,
    platform_breakdown_suffix,
    plural_achievements,
    plural_trophies,
    score_suffix,
)
from bot.views.tables import blockquote, total_line, truncate_name

DAY_WINDOW_HOURS = 24  # rolling — everyone's "today" is the same 24 hours


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


async def current_top_limit(repo: Repo) -> int:
    return await repo.get_int_setting(TOP_LIMIT_KEY, DEFAULT_TABLE_TOP)


async def build_summary(
    repo: Repo,
    chat_id: int,
    threshold: float,
    today: date,
    *,
    locale: str,
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
    _ = translator("daily", locale)
    top_limit = await current_top_limit(repo)
    # (kind, section_lines, has_more) — kind drives the «показать всех» button.
    blocks: list[tuple[str, list[str], bool]] = []

    if with_day:
        day_cutoff = utcnow() - timedelta(hours=DAY_WINDOW_HOURS)
        rows = await repo.chat_member_stats(chat_id, day_cutoff, threshold)
        if not rows:
            return None
        blocks.append(
            ("day", *_section(_("daily-window-day"), rows, top_limit, locale, show_rare=False))
        )

    if with_month:
        month_cutoff = month_cutoff_utc(tz_offset_min)
        rows = await repo.chat_member_stats(chat_id, month_cutoff, threshold)
        if not rows:
            if not blocks:
                return None  # month-only report for a chat with no members
        else:
            blocks.append(
                (
                    "month",
                    *_section(_month_window_label(tz_offset_min, locale), rows, top_limit, locale),
                )
            )
            # #7: which games the chat actually played this month, not just
            # who — its own block, only when there's something to show (a
            # month of zero-scorers has nothing to rank).
            games = await repo.chat_top_games(chat_id, month_cutoff, top_limit, locale=locale)
            if games:
                blocks.append(("games", _games_section(games, locale), False))

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
    repo: Repo,
    chat_id: int,
    threshold: float,
    window: str,
    tz_offset_min: int | None = None,
    *,
    locale: str,
) -> str | None:
    """The uncapped list behind a summary's «Показать всех» button (SPEC
    6.3) — re-fetched fresh rather than carried over from the original send,
    same as /hltb's sessions do for their own "current data" reasons."""
    _ = translator("daily", locale)
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
        len(rows),
        locale,
        expandable=False,
        show_rare=window != "day",
    )
    label = _("daily-window-day") if window == "day" else _month_window_label(tz_offset_min, locale)
    return "\n".join([_("daily-leaderboard-full-header", label=label), "", *section_lines])


def _month_window_label(tz_offset_min: int | None, locale: str) -> str:
    """ "С 1 июня" (#6, user request) instead of a static "этот месяц" —
    names the actual calendar month the window covers, in the same
    genitive-case month names "{day} {month}" (daily-header) already uses.
    The *current* local month is always the one month_cutoff_utc's "since
    the 1st" points at, so no need to re-derive it from the cutoff itself.

    English puts the day after the month ("since June 1"), Russian before it
    — that ordering lives in each locale's own daily-window-month, not here."""
    _ = translator("daily", locale)
    month = local_now(tz_offset_min).month
    return _("daily-window-month", month=_(_MONTH_KEYS[month - 1]))


def _section(
    label: str,
    rows: list[ChatMemberStat],
    limit: int,
    locale: str,
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
    summary = total_line(label, f"{plural_achievements(total, locale)}, +{thousands(score)} G")
    capped = rows if limit == 0 else rows[:limit]
    rows_block = blockquote(
        [
            _leader_row(place, row, locale, show_rare=show_rare)
            for place, row in enumerate(capped, start=1)
        ],
        expandable=expandable,
    )
    has_more = limit != 0 and len(rows) > limit
    return [summary, rows_block], has_more


def _member_name(row: ChatMemberStat) -> str:
    """#51: the one person chain, not this row's own. It used to read
    `row.gamertag or f"id{row.tg_id}"` — an Xbox-only display cache — so a
    member with no Xbox account appeared as a bare id while the bot held his
    Telegram name, his username and his PSN nickname."""
    return person_name(
        tg_id=row.tg_id,
        first_name=row.first_name,
        last_name=row.last_name,
        username=row.username,
        xbox=xbox_nickname(gamertag_modern=row.gamertag_modern, gamertag=row.gamertag),
        steam=row.steam_name,
        psn=row.psn_name,
    )


def _leader_row(place: int, row: ChatMemberStat, locale: str, *, show_rare: bool = True) -> str:
    name = html_escape(truncate_name(_member_name(row)))
    tail = f" {AchievementBadge.DIAMOND}{row.rare}" if show_rare and row.rare else ""
    breakdown = platform_breakdown_suffix(
        row.xbox_count, row.steam_count, row.psn_count, always=True
    )
    return (
        f"{place}. {name} — {plural_achievements(row.count, locale)}{tail}{breakdown}"
        f" (+{thousands(row.score)} G)"
    )


def _games_section(games: list[ChatTopGame], locale: str) -> list[str]:
    """The monthly summary's own new block (#7, user request): which games
    the chat actually played this month, ranked by achievements/trophies
    earned in each — not who, `_section` above's own job. No "show all"
    button of its own (unlike `_section`'s people list) — `chat_top_games`
    is already capped by the same admin-configured `summary_top_limit`
    (SPEC 6.4), and a second uncapped view for this one block wasn't asked
    for. Not truncated (user request, 2026-09-08, same reasoning /stats'
    own games list uses) — it already lives inside its own collapsible
    quote, so a long title wrapping onto a second line costs nothing."""
    _ = translator("daily", locale)
    rows = [
        f"{place}. {PLATFORM_ICON.get(game.platform, '')} "
        f"{html_escape(game.name or _('daily-unknown-game'))} — {_game_row_tail(game, locale)}"
        for place, game in enumerate(games, start=1)
    ]
    return [_("daily-games-header"), blockquote(rows)]


def _game_row_tail(game: ChatTopGame, locale: str) -> str:
    """PSN games show a trophy-tier breakdown instead of gamerscore (user
    request, 2026-09-08) — the same per-tier icons
    `services/achievements.py::TROPHY_TIER_BADGE` uses everywhere else.
    Xbox/Steam show gamerscore instead, same "(+N G)" tail /stats already
    uses, skipped entirely for a zero score (a Steam row's is always 0)."""
    if game.platform == Platform.PSN:
        tiers = [
            (game.platinum, TROPHY_TIER_BADGE[PsnTrophyTier.PLATINUM]),
            (game.gold, TROPHY_TIER_BADGE[PsnTrophyTier.GOLD]),
            (game.silver, TROPHY_TIER_BADGE[PsnTrophyTier.SILVER]),
            (game.bronze, TROPHY_TIER_BADGE[PsnTrophyTier.BRONZE]),
        ]
        tier_tail = "".join(f" {badge}{count}" for count, badge in tiers if count)
        return f"{plural_trophies(game.count, locale)}{tier_tail}"
    return f"{plural_achievements(game.count, locale)}{score_suffix(game.score)}"
