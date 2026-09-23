"""The daily and month-end summaries (#63).

One form, two cutoffs (#14, narrowed by the owner 2026-09-17): a header, the
chat's combined total, its players, and the games they played. The scheduled
daily job and /summary_day send the 24-hour one; the month-end job and
/summary_month send the calendar month. Composed rather than written twice,
so their style cannot drift apart.

poller/daily.py keeps the schedule — whose summary is due, in which chat,
at which local hour — and the sending.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from html import escape as html_escape

from aiogram.types import InlineKeyboardMarkup

from bot.db.repo import ChatMemberStat, GameAchievements, Repo
from bot.i18n import translator
from bot.services.admin_settings import DEFAULT_TABLE_TOP, TOP_LIMIT_KEY
from bot.services.naming import person_name, xbox_nickname
from bot.services.stats import local_now, month_cutoff_utc, month_window_utc
from bot.util import utcnow
from bot.views.date_picker import (
    summary_day_navigation_keyboard,
    summary_month_navigation_keyboard,
)
from bot.views.lists import Listing, games_listing, total_line, truncate_name
from bot.views.parts import (
    bracketed,
    platform_breakdown_suffix,
    plural_achievements,
    value_parts,
)

DAY_WINDOW_HOURS = 24  # rolling — everyone's "today" is the same 24 hours

#: Which window a report covers. Two values and no third: "both at once" was
#: /summary's own shape and went with it (owner, 2026-09-17).
DAY = "day"
MONTH = "month"


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
    window: str = DAY,
) -> tuple[str, InlineKeyboardMarkup | None] | None:
    """One window's leaderboard report — `DAY` or `MONTH`, never both.

    Lists everyone subscribed, zero-scorers included, so it reads as a
    roster; a day nobody unlocked anything still sends (#34). Returns None
    only when the chat has no subscribed members at all.
    """
    _ = translator("daily", locale)
    top_limit = await current_top_limit(repo)
    is_day = window == DAY

    now_local = local_now(tz_offset_min)
    now_date = now_local.date()

    if is_day:
        if today == now_date:
            cutoff = utcnow() - timedelta(hours=DAY_WINDOW_HOURS)
            until = None
        else:
            start_local = datetime(
                today.year, today.month, today.day, 0, 0, 0, tzinfo=UTC
            ) - timedelta(minutes=tz_offset_min or 0)
            cutoff = start_local
            until = start_local + timedelta(hours=24)
    else:
        cutoff, until = month_window_utc(today.year, today.month, tz_offset_min)
        if (today.year, today.month) == (now_date.year, now_date.month):
            until = None

    rows = await repo.chat_member_stats(chat_id, cutoff, threshold, until=until)
    if not rows:
        return None

    # (kind, section_lines, has_more) — kind drives the leaderboard truncation.
    blocks: list[tuple[str, list[str], bool]] = [
        (window, *_section(_("daily-total-label"), rows, top_limit, locale))
    ]

    games = await repo.users_games_achievements(
        [row.tg_id for row in rows],
        cutoff,
        until=until,
        rare_threshold=threshold,
        limit=top_limit,
        locale=locale,
    )
    if games:
        blocks.append(("games", _games_section(games, locale), False))

    if not blocks:
        return None

    header = _("daily-header") if is_day else _("daily-monthly-header")
    lines = [header]
    for _kind, section_lines, _more in blocks:
        lines += ["", *section_lines]

    has_more = blocks[0][2]
    if is_day:
        markup = summary_day_navigation_keyboard(today, now_date, locale=locale, has_more=has_more)
    else:
        markup = summary_month_navigation_keyboard(
            today.year,
            today.month,
            now_date.year,
            now_date.month,
            locale=locale,
            has_more=has_more,
        )

    return "\n".join(lines), markup


async def full_leaderboard(
    repo: Repo,
    chat_id: int,
    threshold: float,
    window: str,
    tz_offset_min: int | None = None,
    *,
    locale: str,
    target_year: int | None = None,
    target_month: int | None = None,
    target_date: date | None = None,
) -> str | None:
    """The uncapped list behind a summary's «Показать всех» button (SPEC
    6.3) — re-fetched fresh rather than carried over from the original send,
    same as /hltb's sessions do for their own "current data" reasons."""
    _ = translator("daily", locale)
    until = None
    if window == "day":
        if target_date is not None:
            start_local = datetime(
                target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=UTC
            ) - timedelta(minutes=tz_offset_min or 0)
            cutoff = start_local
            until = start_local + timedelta(hours=24)
        else:
            cutoff = utcnow() - timedelta(hours=DAY_WINDOW_HOURS)
        label = (
            _("daily-window-day")
            if target_date is None
            else f"{target_date.day} {_MONTH_KEYS[target_date.month - 1]}"
        )
    else:
        if target_year is not None and target_month is not None:
            cutoff, until = month_window_utc(target_year, target_month, tz_offset_min)
            month_str = _(_MONTH_KEYS[target_month - 1])
            label = _("daily-window-month", month=month_str)
        else:
            cutoff = month_cutoff_utc(tz_offset_min)
            label = month_window_label(tz_offset_min, locale)

    rows = await repo.chat_member_stats(chat_id, cutoff, threshold, until=until)
    if not rows:
        return None
    section_lines, _full = _section(
        _("daily-leaderboard-total-label"),
        rows,
        len(rows),
        locale,
        expandable=False,
    )
    return "\n".join([_("daily-leaderboard-full-header", label=label), "", *section_lines])


def month_name(tz_offset_min: int | None, locale: str) -> str:
    """Just the month, in the genitive the "{day} {month}" forms already use
    — for a caller that builds its own phrase around it (/stats' counter line
    says "С 1 сентября:", where month_window_label's own "с 1 сентября" would
    arrive lowercase in the middle of a label)."""
    _ = translator("daily", locale)
    return _(_MONTH_KEYS[local_now(tz_offset_min).month - 1])


def month_window_label(tz_offset_min: int | None, locale: str) -> str:
    """ "С 1 июня" (#6, user request) instead of a static "этот месяц" —
    names the actual calendar month the window covers, in the same
    genitive-case month names "{day} {month}" (daily-header) already uses.
    The *current* local month is always the one month_cutoff_utc's "since
    the 1st" points at, so no need to re-derive it from the cutoff itself.

    English puts the day after the month ("since June 1"), Russian before it
    — that ordering lives in each locale's own daily-window-month, not here.

    Public: also used by views/chat.py's own games list,
    which needs the same "с 1 { month }" label /summary's month block uses —
    one label for "calendar month since the 1st" everywhere, not a second
    hand-rolled copy."""
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
) -> tuple[list[str], bool]:
    """The totals line comes first, then the list — reversed from the old
    table-then-total order, so the headline number reads before you tap the
    list open (SPEC 6.3, 7.3). `limit == 0` means "no cap" (admin-configured,
    6.4) — a list this long only ever lives inside a collapsible quote, so
    there is nothing left to truncate for.

    The day and the month render identically, differing only in the window
    they were given (owner, 2026-09-17) — which reverses #9's own
    "the day block drops the 💎 tail": one form is easier to read across two
    messages than two forms that are nearly the same.
    """
    _ = translator("daily", locale)
    total = sum(row.count for row in rows)
    score = sum(row.score for row in rows)
    rare = sum(row.rare for row in rows)
    tiers = tuple(sum(row.tiers[n] for row in rows) for n in range(4))
    capped = rows if limit == 0 else rows[:limit]
    listing = Listing(
        total=total_line(
            label,
            plural_achievements(total, locale)
            + platform_breakdown_suffix(
                sum(row.xbox_count for row in rows),
                sum(row.steam_count for row in rows),
                sum(row.psn_count for row in rows),
            )
            + bracketed(value_parts(score, rare, tiers)),  # type: ignore[arg-type]
        ),
        header=_("daily-players-header"),
        rows=[_leader_row(place, row, locale) for place, row in enumerate(capped, start=1)],
        expandable=expandable,
    )
    has_more = limit != 0 and len(rows) > limit
    # Separate lines, because build_summary stitches blocks together with
    # blank lines of its own and needs them separable. The blank one between
    # the total and the roster is the owner's (2026-09-17): the total is the
    # headline, and it reads as one when the list does not start against it.
    return [listing.total or "", "", listing.header or "", listing.body()], has_more


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


def _leader_row(place: int, row: ChatMemberStat, locale: str) -> str:
    name = html_escape(truncate_name(_member_name(row)))
    breakdown = platform_breakdown_suffix(
        row.xbox_count, row.steam_count, row.psn_count, always=True
    )
    # The same two brackets /stats' own counter line uses (owner, 2026-09-17)
    # — where the achievements came from, then what they were worth. The 💎
    # used to sit loose between the count and the breakdown.
    return f"{place}. {name} — {plural_achievements(row.count, locale)}{breakdown}" + bracketed(
        value_parts(row.score, row.rare, row.tiers)
    )


def _games_section(games: list[GameAchievements], locale: str) -> list[str]:
    """Which games the chat actually played in this window, ranked by what
    was earned in each — not by who earned it, which is `_section`'s job (#7).

    No "show all" button of its own, unlike that people list: the query is
    already capped by the same admin-set `summary_top_limit` (SPEC 6.4), and
    a second uncapped view for this one block was not asked for. The row and
    the query are both the shared ones (#64, then 2026-09-17) — /stats
    renders the identical line from the same call over one person.
    """
    _ = translator("daily", locale)
    listing = games_listing(games, _("daily-unknown-game"), locale)
    return [_("daily-games-header"), listing.body()]
