"""The trophy group of PSN trophies stored before #46 (#115).

Until #46 the bot asked Sony for the base game's trophies only, and stored
them with no group. The scan re-asks a game only when its progress moves, and
the one pass that widens a game (`repo.psn_title_needs_widening`) runs only
when *none* of its rows has a group — so a game with even one newer trophy
kept its older ones ungrouped for good, and a card's group counter read
`Основная игра · 3/51` for somebody holding 46 of them.

This walks those games a few a minute, one request each through the shared
NPSSO, via `services/psn/achievements.py::regroup_title`. A game Sony cannot
answer for is skipped for the life of the process — a restart tries again.
"""

from __future__ import annotations

import json
import logging

from bot.db.repo import Repo
from bot.services.psn.achievements import regroup_title
from bot.services.psn.auth import STATUS_NOT_CONFIGURED, PsnAuth, PsnNotConfiguredError
from bot.services.psn.client import PsnApiError, PsnTokenDeadError, title_ref

log = logging.getLogger(__name__)

# Politeness toward Sony's private API, and the backlog is finite: about a
# hundred games on production, gone in under an hour.
TITLES_PER_TICK = 2


class PsnTrophyGroups:
    def __init__(
        self, repo: Repo, psn_auth: PsnAuth, *, titles_per_tick: int = TITLES_PER_TICK
    ) -> None:
        self._repo = repo
        self._psn_auth = psn_auth
        self._titles_per_tick = titles_per_tick
        self._unanswerable: set[tuple[str, str]] = set()

    async def tick(self) -> None:
        if await self._psn_auth.status() == STATUS_NOT_CONFIGURED:
            return
        pending = await self._repo.psn_titles_missing_groups(
            self._titles_per_tick, skip=self._unanswerable
        )
        if not pending:
            return
        try:
            client = await self._psn_auth.get_client()
        except (PsnNotConfiguredError, PsnApiError):
            return
        for tg_id, account_id, title_id, platforms in pending:
            title = title_ref(title_id, json.loads(platforms) if platforms else None)
            try:
                changed = await regroup_title(self._repo, client, tg_id, account_id, title)
            except PsnTokenDeadError:
                return  # service_health's business; nothing more this tick
            except Exception:
                log.info("psn groups for %s (%s) unavailable", title_id, account_id, exc_info=True)
                self._unanswerable.add((account_id, title_id))
                continue
            if not changed:
                # Sony answered and still left these rows ungrouped (a trophy
                # it no longer lists): asking again would change nothing.
                self._unanswerable.add((account_id, title_id))
            log.info("psn groups for %s (%s): %s trophies grouped", title_id, account_id, changed)
