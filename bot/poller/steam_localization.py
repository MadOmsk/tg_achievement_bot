"""Steam game names in both languages, for games nobody is playing any more
(#61).

Everything else fills in as somebody unlocks something: the Russian name of a
game arrives on the next poll of it, along with the achievement names. A game
that was finished a year ago is never polled again, so its name would stay in
whatever language the API answered in forever — and the Steam Web API answers
in exactly one, whatever `l=` says. Only the storefront knows the other one.

So this walks the library instead, a few games per tick, forever. It is the
Steam counterpart of poller/description_backfill.py, and much cheaper than
that one: the storefront needs no key and no owner — an appid is the whole
question — so there is no token to rotate, nobody's quota to spend, and
nothing to serialize.

The pace is politeness toward somebody else's storefront rather than a
documented limit: Valve publishes none for this endpoint, and the observed
one is generous (a couple of hundred requests per five minutes per address).
Two games a minute walks a 500-game library in four hours and is invisible
next to anything else the bot does.
"""

from __future__ import annotations

import logging

from bot.constants import Platform
from bot.db.repo import Repo
from bot.services.steam.client import store_name

log = logging.getLogger(__name__)

# Two games a minute, each two storefront requests (one per language).
TITLES_PER_TICK = 2


class SteamLocalization:
    def __init__(self, repo: Repo, *, titles_per_tick: int = TITLES_PER_TICK) -> None:
        self._repo = repo
        self._titles_per_tick = titles_per_tick
        # Games the storefront will not answer for — delisted, region-locked,
        # or simply gone. Without this the same appid would be asked about
        # every minute forever, which is a hot loop against a service that is
        # doing us a favour. Process-lifetime only, like the description
        # backfill's own: a restart tries again, which is the right cadence
        # for something that may have been a bad afternoon at Valve.
        self._unanswerable: set[str] = set()

    async def tick(self) -> None:
        appids = await self._repo.titles_missing_localized_name(
            Platform.STEAM, self._titles_per_tick + len(self._unanswerable)
        )
        remaining = self._titles_per_tick
        for appid in appids:
            if remaining <= 0:
                break
            if appid in self._unanswerable:
                continue
            remaining -= 1
            russian = await store_name(appid, "russian")
            english = await store_name(appid, "english")
            if russian is None and english is None:
                self._unanswerable.add(appid)
                continue
            await self._repo.set_title_names(appid, russian, english)
            if russian and english and russian != english:
                log.info("steam: %s is %r in Russian", appid, russian)
