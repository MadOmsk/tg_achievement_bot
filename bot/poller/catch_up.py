"""A slow delta for everyone, not only at startup (#82).

The presence poller only ever asks about the game somebody is in *right
now*, plus one last look as they leave it. An Xbox console uploads what was
earned offline when it next reaches the network — normally well after that
last look — so nothing asks about the game again and the unlocks sit in
titlehub unread until the bot happens to restart. Two people lost a session
of Gears of War 3 to exactly that, which is what #82 was reported as.

One account per tick, not all of them: `title_history` for a large account
is a heavy response (~46s for a real 1011-title one), and nine of those in
a row would make a single minute's tick run for several. Spread across the
hour there is no burst at all, and with a tick a minute even a much larger
community is swept long before its next turn comes round.

A pass where nobody played anything costs exactly one request per account:
`_played_since` finds no candidate title and `catch_up` returns.
"""

from __future__ import annotations

import asyncio
import logging
import time

from bot.config import Settings
from bot.db.repo import PollTarget, Repo
from bot.i18n import DEFAULT_LOCALE, gettext
from bot.poller.fetcher import Fetcher, catch_up_since

log = logging.getLogger(__name__)

#: The same ceiling startup catch-up puts on one account's whole call, and
#: for the same reason: one bad run must not hold up everybody behind it.
DEADLINE_SECONDS = 120.0


class CatchUpPoller:
    def __init__(self, settings: Settings, repo: Repo, fetcher: Fetcher) -> None:
        self._settings = settings
        self._repo = repo
        self._fetcher = fetcher
        # Kept in memory rather than in the database on purpose: the only
        # thing a restart loses is the knowledge that an account was swept
        # recently, and a restart runs `startup_catch_up` over everybody
        # anyway. Seeding from process start is what stops that boot sweep
        # being repeated an instant later.
        self._started = time.monotonic()
        self._last: dict[str, float] = {}

    async def tick(self) -> None:
        target = await self._next_due()
        if target is None:
            return
        self._last[target.xuid] = time.monotonic()
        user = await self._repo.get_user(target.tg_id)
        gamertag = (user.gamertag if user else None) or gettext(
            "main", "main-default-player-name", locale=DEFAULT_LOCALE
        )
        try:
            titles, published = await asyncio.wait_for(
                self._fetcher.catch_up(
                    target.tg_id,
                    target.xuid,
                    gamertag,
                    await catch_up_since(
                        self._repo, target.xuid, self._settings.catchup_publish_window_hours
                    ),
                    self._settings.catchup_publish_window_hours,
                    self._settings.catchup_max_titles,
                ),
                timeout=DEADLINE_SECONDS,
            )
        except TimeoutError:
            log.error("hourly catch-up for tg_id=%s exceeded %.0fs", target.tg_id, DEADLINE_SECONDS)
            return
        except Exception:
            # One account's bad hour is not the tick's problem — the same
            # isolation every other poller here keeps.
            log.exception("hourly catch-up for tg_id=%s failed", target.tg_id)
            return
        if titles or published:
            log.info(
                "hourly catch-up for tg_id=%s: %s titles, %s published",
                target.tg_id,
                titles,
                published,
            )

    async def _next_due(self) -> PollTarget | None:
        """The account that has waited longest past its interval.

        Longest-waiting rather than first-in-the-list so a newly linked
        account cannot keep jumping the queue ahead of somebody who has been
        waiting since the last sweep.
        """
        interval = self._settings.catchup_interval_minutes * 60
        now = time.monotonic()
        overdue = [
            target
            for target in await self._repo.pollable_users()
            if now - self._last.get(target.xuid, self._started) >= interval
        ]
        if not overdue:
            return None
        return min(overdue, key=self._waiting_since)

    def _waiting_since(self, target: PollTarget) -> tuple[float, bool]:
        """How long this account has been waiting, oldest first.

        The second element breaks a tie towards an account never swept in
        this process: two accounts can genuinely share a timestamp — a clock
        with millisecond resolution, two ticks in the same instant — and
        without a tiebreak the sort is merely stable, which means it hands
        back the same account every time and the rest are never reached.
        """
        seen = self._last.get(target.xuid)
        return (seen if seen is not None else self._started, seen is not None)
