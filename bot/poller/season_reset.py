"""TEMPORARY (owner, 2026-10-30): the one-time wipe of the first season's pass
when the second begins — see `services/season_reset.py`, which says what to
delete afterwards."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot.services.season_reset import reset_for_second_season

if TYPE_CHECKING:
    from bot.db.repo import Repo


class SeasonReset:
    def __init__(self, repo: Repo) -> None:
        self._repo = repo

    async def tick(self) -> None:
        await reset_for_second_season(self._repo)
