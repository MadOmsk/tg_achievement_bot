"""Patch notes kept fresh for the games people are playing.

A game's patches are first read when its first new achievement is published
(services/steam_extras.py); after that, this walker re-reads the Steam apps of
games somebody earned something in over the last month, each once every
`patch_refresh_hours` (6 by default, /admin). Steam's news API needs no key and
is one request per app, so a few apps a tick is plenty and nothing bursts.
Nothing is sent to a chat — the Mini App's "Обновления" tab shows them.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from bot.db.repo import Repo
from bot.services.steam_extras import SteamExtras
from bot.util import utcnow

log = logging.getLogger(__name__)

REFRESH_HOURS_KEY = "patch_refresh_hours"
DEFAULT_REFRESH_HOURS = 6
APPS_PER_TICK = 3
# Games somebody earned something in this recently are the ones worth watching.
ACTIVE_DAYS = 30


class PatchRefresh:
    def __init__(
        self, repo: Repo, extras: SteamExtras, *, apps_per_tick: int = APPS_PER_TICK
    ) -> None:
        self._repo = repo
        self._extras = extras
        self._apps_per_tick = apps_per_tick

    async def tick(self) -> None:
        hours = await self._repo.get_int_setting(REFRESH_HOURS_KEY, DEFAULT_REFRESH_HOURS)
        now = utcnow()
        apps = await self._repo.steam_apps_due_for_patches(
            played_since=(now - timedelta(days=ACTIVE_DAYS)).isoformat(timespec="seconds"),
            stale_before=(now - timedelta(hours=hours)).isoformat(timespec="seconds"),
            limit=self._apps_per_tick,
        )
        for appid in apps:
            try:
                await self._extras.refresh_patches(appid)
            except Exception:
                log.exception("patch refresh failed for steam app %s", appid)
