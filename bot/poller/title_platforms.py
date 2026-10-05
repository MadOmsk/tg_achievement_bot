"""An Xbox game's platforms, for the games whose achievements are not being
published right now (#114).

The platforms decide which version of a game the achievement card and
/recent name — a Smart Delivery or Play Anywhere game can only be told apart
by them — and the games lists show them outright. titlehub's `devices`
carries them, which `title_history` writes for every game it lists; a game
it never listed (history older than the list's reach, a game only a backfill
found) has none. `Fetcher.ensure_title_platforms` asks before publishing;
this walks the rest, a few games a minute, through an owner's own token.

Three failed lookups an hour apart at least, and the game is stored as '[]'
(known to be unknown) — the card then names the version native to the
device played on. The same reason as covers.py for being a poller and not a
script: Xbox's rotating refresh token must stay under one process's lock.
"""

from __future__ import annotations

import logging

from bot.constants import Platform
from bot.db.repo import Repo
from bot.services.platform_format import game_platforms_json
from bot.services.xbox.auth import TokenRefreshError
from bot.services.xbox.client import XboxApiError, XboxClient

log = logging.getLogger(__name__)

# Lookups only, no downloads: a little brisker than the cover walker.
TITLES_PER_TICK = 5


class TitlePlatformsRefresh:
    def __init__(
        self, repo: Repo, client: XboxClient, *, titles_per_tick: int = TITLES_PER_TICK
    ) -> None:
        self._repo = repo
        self._client = client
        self._titles_per_tick = titles_per_tick

    async def tick(self) -> None:
        for title_id, owner_tg_id in await self._repo.titles_needing_platforms(
            self._titles_per_tick
        ):
            try:
                await self._visit(title_id, owner_tg_id)
            except Exception:
                log.exception("platform lookup failed for title %s", title_id)

    async def _visit(self, title_id: str, owner_tg_id: int) -> None:
        try:
            entry = await self._client.resolve_title(owner_tg_id, title_id)
        except (XboxApiError, TokenRefreshError) as exc:
            log.info("platform lookup for title %s unanswerable (%s)", title_id, exc)
            entry = None
        found = (
            game_platforms_json(entry.devices, is_x360=entry.platform == Platform.XBOX_360)
            if entry
            else None
        )
        await self._repo.record_platforms_lookup(title_id, found)
