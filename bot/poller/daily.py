"""Daily summary (SPEC 5.7, format 7.3).

Counted entirely from the database — zero API calls. The job wakes up every
minute and asks "is it time yet", because the hour is a setting the admin can
change at runtime; a cron trigger would have to be rebuilt on every change.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from aiogram import Bot
from aiogram.enums import ParseMode

from bot.db.repo import Repo
from bot.services.admin_settings import (
    DEFAULT_MONTHLY_DELAY_MINUTES,
    MONTHLY_DELAY_KEY,
)
from bot.services.chat_gone import chat_is_gone
from bot.services.message_log import stats_category
from bot.services.stats import local_now
from bot.version import is_test
from bot.views.summary import (
    DAY,
    MONTH,
    build_summary,
)

log = logging.getLogger(__name__)

# No module-level shorthand (#48): this module renders one chat's summary at
# a time, and the scheduled job loops over every chat — the locale has to
# travel with the call, not sit in module state. `locale` arrives alongside
# `threshold` and `tz_offset_min`, which the caller already reads from the
# same chat_settings row.

# The "month" block is the calendar month (#14): since midnight on the 1st,
# in the chat's own timezone (services/stats.py::month_cutoff_utc). The
# figure resets on the 1st instead of sliding.


class DailySummary:
    def __init__(self, bot: Bot, repo: Repo) -> None:
        self._bot = bot
        self._repo = repo

    async def tick(self, now: datetime | None = None) -> None:
        # Every chat has its own time/zone/threshold in chat_settings (SPEC
        # 5.7), so "is it time yet" is answered separately per chat, not once
        # for everyone.
        delay_minutes = await self._repo.get_int_setting(
            MONTHLY_DELAY_KEY, DEFAULT_MONTHLY_DELAY_MINUTES
        )
        for chat in await self._repo.admin_chats():
            if not chat.is_active or not chat.daily_summary:
                continue

            now_local = local_now(chat.tz_offset_min, now=now)
            if now_local.strftime("%H:%M") == chat.daily_summary_time:
                report_date = now_local.date()
                marker = report_date.isoformat()
                if not await self._repo.daily_report_sent(chat.chat_id, marker):
                    await self._send_scheduled(chat, marker, target_date=report_date, window=DAY)

            # On the last calendar day of the month, the month-end wrap-up
            # goes out too (#14) — trailing the daily summary by delay_minutes
            # (#74), under its own dedup marker, and additional to that day's
            # daily summary, not instead of it.
            # Checked against the time delay_minutes ago so the wrap-up still
            # covers the month that just ended even if the timer crossed
            # midnight into the 1st of the next month (e.g. 23:58 + 5m -> 00:03).
            month_ref = now_local - timedelta(minutes=delay_minutes)
            if month_ref.strftime("%H:%M") == chat.daily_summary_time and _is_last_day_of_month(
                month_ref.date()
            ):
                month_date = month_ref.date()
                month_key = _monthly_key(month_date)
                if not await self._repo.daily_report_sent(chat.chat_id, month_key):
                    await self._send_scheduled(
                        chat, month_key, target_date=month_date, window=MONTH
                    )

    async def _send_scheduled(
        self, chat, marker: str, *, target_date: date | None = None, window: str
    ) -> None:
        target = target_date or local_now(chat.tz_offset_min).date()
        built = await build_summary(
            self._repo,
            chat.chat_id,
            chat.rare_threshold_percent,
            target,
            locale=chat.locale,
            tz_offset_min=chat.tz_offset_min,
            window=window,
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
        except Exception as exc:
            if chat_is_gone(exc) and is_test():
                # Not a member of a chat copied from production: leave it
                # active (see the publisher) and count today's report as done.
                log.info("chat %s is unreachable for the test bot, skipping it", chat.chat_id)
                await self._repo.mark_daily_report_sent(chat.chat_id, marker)
            elif chat_is_gone(exc):
                log.info("chat %s is gone (%s), deactivating", chat.chat_id, exc)
                await self._repo.deactivate_chat(chat.chat_id)
            else:
                log.exception("could not send the summary to %s", chat.chat_id)
            return
        await self._repo.mark_daily_report_sent(chat.chat_id, marker)


def _is_last_day_of_month(dt: date) -> bool:
    return (dt + timedelta(days=1)).month != dt.month


def _monthly_key(dt: date) -> str:
    """The daily_reports marker for a month-end wrap-up — deliberately not a
    valid ISO date, so it can't collide with a real daily marker."""
    return f"{dt.year:04d}-{dt.month:02d}-monthly"
