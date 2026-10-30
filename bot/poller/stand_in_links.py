"""Games made of nothing but a list's stand-in put where they belong (owner,
2026-10-30).

A list nobody has linked becomes a game of its own when its page is first
opened (`adopt_list_as_game`) — so the same game on two platforms (Aniimo on
Xbox and on PS5) is two games until the linker has met them. The linker is a
local model with no network, so it need not wait for the store collection:
each tick takes a few such versions that no pass has looked at lately and lets
it join them to their namesakes. A version looked at is not looked at again for
a week, then two, a month (`fetch_state`, the store schedule), so a game that
stays alone costs nothing after the first passes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bot.services.game_link import GameLinker

if TYPE_CHECKING:
    from bot.db.repo import Repo

log = logging.getLogger(__name__)

SOURCE = "stand_in_link"
# Versions a tick: the linker reads every version once, so a batch is cheap.
PER_TICK = 40


class StandInLinks:
    def __init__(self, repo: Repo) -> None:
        self._repo = repo

    async def tick(self) -> None:
        versions = await self._repo.stand_in_versions_due(SOURCE, PER_TICK)
        if not versions:
            return
        report = await GameLinker(self._repo).link_versions(versions)
        for version_id in versions:
            await self._repo.record_fetch(f"version:{version_id}", SOURCE, status="ok")
        log.info(
            "stand-ins linked: %s versions looked at, games now %s",
            len(versions),
            len(report.games),
        )
