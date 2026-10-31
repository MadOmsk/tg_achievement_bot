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
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bot.services import api_usage
from bot.util import utcnow_iso

if TYPE_CHECKING:
    from bot.db.repo import Repo
    from bot.services.octopus import OctopusCollector

log = logging.getLogger(__name__)

PER_TICK_KEY = "octopus_entries_per_tick"
DEFAULT_PER_TICK = 1


@dataclass(frozen=True, slots=True)
class LastGame:
    """The game the octopus assembled last, for the admin's home."""

    name: str
    versions: int
    review: int
    at: str  # UTC ISO


# In memory, like the API counters: a restart starts it over.
last_game: LastGame | None = None


class _SkippedTick(logging.Filter):
    """A tick that finds the last run still going is skipped by design (an
    entry may take minutes): told at INFO, not as a warning."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno == logging.WARNING and "OctopusWorker.tick" in record.getMessage():
            record.levelno, record.levelname = logging.INFO, "INFO"
        return True


logging.getLogger("apscheduler.scheduler").addFilter(_SkippedTick())


class OctopusWorker:
    def __init__(
        self,
        repo: Repo,
        octopus: OctopusCollector,
        *,
        on_games: Callable[[list[int]], None] | None = None,
    ) -> None:
        self._repo = repo
        self._octopus = octopus
        # Told the games assembled, so their descriptions are translated.
        self._on_games = on_games

    async def tick(self) -> None:
        # Imported here: admin_settings reads this module's default.
        from bot.services.store_collect import collection_on

        if not await collection_on(self._repo):
            return
        per_tick = await self._repo.get_int_setting(PER_TICK_KEY, DEFAULT_PER_TICK)
        if per_tick <= 0:
            return
        global last_game
        report = await self._octopus.run(limit=per_tick)
        for game in report.games:
            api_usage.record(api_usage.OCTOPUS)
            last_game = LastGame(
                game.name or str(game.game_id), game.versions_after, game.review, utcnow_iso()
            )
            log.info(
                "octopus: %s → game %s %r, versions %s → %s, to review %s",
                game.entry,
                game.game_id,
                game.name,
                game.versions_before,
                game.versions_after,
                game.review,
            )
        if self._on_games is not None and report.games:
            self._on_games([game.game_id for game in report.games if game.game_id])
        for line in report.failed:
            api_usage.record(api_usage.OCTOPUS_FAILED)
            log.warning("octopus: %s", line)
