"""The season started: told at noon on the 1st, in each person's own time zone.

Every ten minutes it looks for whoever has reached 12:00 on the 1st of their month,
and tells those who have not opened the pass since it began (`pass_seen`), once a
season (`season_notified`). A month whose pass has no live level has not started.
The whole afternoon counts, so a bot that was down at noon still tells them; the 2nd
does not.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bot.services import time_zones

if TYPE_CHECKING:
    from bot.db.repo import Repo
    from bot.services.notifier import Notifier

log = logging.getLogger(__name__)

NOON = 12


class SeasonStart:
    def __init__(self, repo: Repo, notifier: Notifier | None = None) -> None:
        self._repo = repo
        self.notifier = notifier

    async def tick(self) -> None:
        if self.notifier is None:
            return
        for person in await self._repo.all_person_ids():
            # One person's failure never stops the rest.
            try:
                await self._tell_one(person)
            except Exception:
                log.exception("season start notice to person_id=%s failed", person)

    async def _tell_one(self, person: int) -> None:
        settings = await self._repo.get_user_settings(person)
        local = time_zones.local_now(settings.tz if settings else None)
        if local.day != 1 or local.hour < NOON:
            return
        month = f"{local.year:04d}-{local.month:02d}"
        if not await self._repo.pass_month_published(month):
            return
        if await self._repo.pass_seen_in(person, month):
            return
        # Marked before it goes: a failure costs one notice, never a second one.
        if await self._repo.mark_season_notified(person, month):
            await self.notifier.tell_about_season_start(person, month)
