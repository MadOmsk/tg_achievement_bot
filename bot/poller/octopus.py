"""The octopus's queue worked through inside the bot (#215, stage 3).

What puts a game in the queue: its achievement list published for the first
time and its page opened in the Mini App (`StoreCollector.ensure`, which
also enqueues `list:<platform>:<title_id>`). This job takes a few entries a
tick (`octopus_entries_per_tick`, /admin → Таймеры; 0 switches it off), one
run at a time (`max_instances=1`): an entry may take minutes — PSN is paced
at a request every two seconds — and a tick that finds the last run still
going is skipped. A game assembled a moment ago is not due again
(`fetch_state`), so a crowd in one game costs one assembly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.db.repo import Repo
    from bot.services.octopus import OctopusCollector

log = logging.getLogger(__name__)

PER_TICK_KEY = "octopus_entries_per_tick"
DEFAULT_PER_TICK = 1


class OctopusWorker:
    def __init__(self, repo: Repo, octopus: OctopusCollector) -> None:
        self._repo = repo
        self._octopus = octopus

    async def tick(self) -> None:
        per_tick = await self._repo.get_int_setting(PER_TICK_KEY, DEFAULT_PER_TICK)
        if per_tick <= 0:
            return
        report = await self._octopus.run(limit=per_tick)
        for game in report.games:
            log.info(
                "octopus: %s → game %s %r, versions %s → %s, to review %s",
                game.entry,
                game.game_id,
                game.name,
                game.versions_before,
                game.versions_after,
                game.review,
            )
        for line in report.failed:
            log.warning("octopus: %s", line)
