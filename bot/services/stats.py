"""Aggregates for the panels, /stats, /top and the daily summary (SPEC 5.9).

Everything is counted from `seen_achievements.unlocked_at` regardless of
`is_backfill`: that flag means "do not publish", not "did not happen".

"today" (24h) is a rolling window — everyone's "today" is the same 24 hours,
no timezone needed. "month" is the calendar month (#14, user request,
reversing an earlier "rolling" call): since midnight on the 1st, in the
person's own timezone, so the number resets on the 1st rather than sliding.
It is deliberately *not* the same window as /stats' recent-games table
(still 30 rolling days) — the two now carry different labels ("этот месяц"
vs "за 30 дней"), so the disagreement that once read as a counting bug (two
unlabelled "month"s) no longer does.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from bot.db.repo import Repo
from bot.util import start_of_month_utc, utcnow


@dataclass(slots=True)
class Counters:
    today: int = 0
    today_score: int = 0
    month: int = 0
    month_score: int = 0
    # No lifetime total: seen_achievements is permanently best-effort (a
    # capped title_history, achievements with no unlock date), unlike these
    # two date-bounded counts — better absent than quietly wrong (SPEC 5.4).
    # Behind `today`/`month`'s own combined total (2026-09-05 follow-up) —
    # a parenthetical for reference, not a second sort key. today_psn/
    # month_psn were missing until #32 — the combined totals above already
    # included PSN (they sum by plain tg_id), only this breakdown didn't.
    today_xbox: int = 0
    today_steam: int = 0
    today_psn: int = 0
    month_xbox: int = 0
    month_steam: int = 0
    month_psn: int = 0


def local_now(tz_offset_min: int | None, now: datetime | None = None) -> datetime:
    return (now or utcnow()) + timedelta(minutes=tz_offset_min or 0)


def today_cutoff_utc(now: datetime | None = None) -> datetime:
    """Start of the rolling 24-hour "today" window.

    No timezone parameter: a rolling window does not need one, and that is
    the point — everyone's "today" is the same 24 hours, unlike a calendar day.
    """
    return (now or utcnow()) - timedelta(hours=24)


def month_cutoff_utc(tz_offset_min: int | None, now: datetime | None = None) -> datetime:
    """Midnight on the 1st of the current month in `tz_offset_min` (#14) —
    the calendar-month counter's cutoff, so the figure resets on the 1st
    instead of sliding. Takes a timezone now (a calendar boundary needs
    one), unlike the still-rolling `today_cutoff_utc`."""
    return start_of_month_utc(tz_offset_min, now)


async def counters_for(repo: Repo, tg_id: int, now: datetime | None = None) -> Counters:
    """Summed across every platform the person has connected (SPEC 9,
    M-Steam-2e) — keyed by tg_id, not any one platform's own external id.

    The month window is calendar-bound in the person's own timezone (#14),
    read from `user_settings` here so callers don't all have to thread it."""
    settings_row = await repo.get_user_settings(tg_id)
    tz_offset_min = settings_row.tz_offset_min if settings_row else None
    today_cutoff = today_cutoff_utc(now)
    month_cutoff = month_cutoff_utc(tz_offset_min, now)
    today, today_score = await repo.achievement_counts_for_person(tg_id, today_cutoff)
    month, month_score = await repo.achievement_counts_for_person(tg_id, month_cutoff)
    today_xbox, today_steam, today_psn = await repo.achievement_platform_breakdown(
        tg_id, today_cutoff
    )
    month_xbox, month_steam, month_psn = await repo.achievement_platform_breakdown(
        tg_id, month_cutoff
    )
    return Counters(
        today,
        today_score,
        month,
        month_score,
        today_xbox,
        today_steam,
        today_psn,
        month_xbox,
        month_steam,
        month_psn,
    )
