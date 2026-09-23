"""Rarity for the Xbox history nobody ever asked contract 4 about.

Rarity arrives only on contract 4 — the per-title call a live poll makes.
Backfill reads the whole library with one contract-2 request instead, which
carries no rarity at all, so a freshly linked account's entire history lands
without it: 25 692 rows of 25 825 on production, split exactly along that
line. Those achievements can never be rare, in `/stats`, in a summary, or in
the 💎 on their own row, because nothing ever told the bot how rare they are.

Re-polling cannot fix the rows themselves — every insert is
`INSERT OR IGNORE` and nothing in the project UPDATEs `seen_achievements`,
so a row stored without a percentage keeps none forever. It fills
`achievement_rarity_cache` instead, which the reading side prefers over the
row (db/repo/_sql.py's own `rarity()`), the same way names and descriptions
have worked since #48.

**One request per title, not per person.** A contract-4 reply lists every
achievement of the game, including the ones the caller never earned, and
rarity is a fact about the achievement — so whichever owner is asked, the
answer fills the cache for everyone. 963 distinct titles on production
against 1 704 person-title pairs.

**Why a poller and not a script**, the same reason `description_backfill.py`
is one: Xbox rotates a per-user refresh token and Microsoft invalidates the
previous one, so two processes refreshing the same person log that person
out. `XboxAuthService`'s guard is an `asyncio.Lock` — it serializes callers
inside one process and does nothing across two. Running here puts this under
that lock. `scripts/backfill_rarity.py` is the same walk for an operator who
wants it finished in one sitting, and it requires the bot stopped.
"""

from __future__ import annotations

import logging

from bot.constants import Platform
from bot.db.repo import Repo
from bot.services.xbox.client import XboxApiError, XboxClient

log = logging.getLogger(__name__)

# One request per title, once a minute. Deliberately gentler than the
# description walker's 10: that one closes a gap every new registration
# reopens, while this is a finite backlog with nobody waiting on it — at 5 a
# minute production's 963 titles are done in about three hours, entirely
# inside the quota the presence and achievement pollers are not using.
#
# The ceiling that matters is not Microsoft's. `XboxClient` is built once for
# the whole bot and every caller shares one `RateLimiter` (100/15s, 300/5min),
# so overrunning is impossible — `acquire()` simply blocks. What overreaching
# would cost is the pollers that publish things people are waiting for.
TITLES_PER_TICK = 5


class RarityBackfill:
    def __init__(
        self, repo: Repo, client: XboxClient, *, titles_per_tick: int = TITLES_PER_TICK
    ) -> None:
        self._repo = repo
        self._client = client
        self._titles_per_tick = titles_per_tick
        # Titles nothing could answer for — a delisted game, an owner whose
        # token is dead, or an Xbox 360 title, which contract 4 answers with
        # an empty list and contract 1 has no rarity for at all. Without this
        # the same title would be retried every minute forever. Process
        # lifetime only: a restart tries again, which is the right cadence
        # for something that may have been a bad afternoon at Microsoft.
        self._unanswerable: set[str] = set()

    async def tick(self) -> None:
        needed = self._titles_per_tick + len(self._unanswerable)
        titles_modern = await self._repo.titles_missing_rarity(Platform.XBOX_MODERN, needed)
        titles_360 = await self._repo.titles_missing_rarity(Platform.XBOX_360, needed)
        titles: list[tuple[str, int, Platform]] = [
            (t_id, tg_id, Platform.XBOX_MODERN) for t_id, tg_id in titles_modern
        ] + [(t_id, tg_id, Platform.XBOX_360) for t_id, tg_id in titles_360]

        remaining = self._titles_per_tick
        for title_id, tg_id, platform in titles:
            if remaining <= 0:
                break
            if title_id in self._unanswerable:
                continue
            remaining -= 1
            try:
                if hasattr(self._client, "title_rarity_with_name"):
                    rarity, title_name = await self._client.title_rarity_with_name(tg_id, title_id)
                else:
                    rarity = await self._client.title_rarity(tg_id, title_id)
                    title_name = None
            except XboxApiError as exc:
                log.info("rarity backfill: title %s unanswerable (%s)", title_id, exc)
                self._unanswerable.add(title_id)
                continue
            if title_name:
                await self._repo.upsert_title(title_id, title_name, platform)
            if not rarity:
                # Asked and there is none — a game Microsoft reports no percentages
                # for. Nothing to cache and nothing to retry.
                self._unanswerable.add(title_id)
                continue
            await self._repo.cache_rarity(platform, title_id, rarity)
            log.info(
                "rarity backfill: cached %s percentages for %s title %s",
                len(rarity),
                platform,
                title_id,
            )

        # Also heal titles that exist in seen_achievements but are missing
        # from `titles` catalog (#77).
        if remaining > 0:
            missing = await self._repo.titles_missing_from_catalogue(
                remaining + len(self._unanswerable)
            )
            for title_id, tg_id in missing:
                if remaining <= 0:
                    break
                if title_id in self._unanswerable:
                    continue
                remaining -= 1
                seen_plat = await self._repo.title_seen_platform(title_id)
                platform = Platform(seen_plat) if seen_plat else Platform.XBOX_MODERN

                title_name = None
                rarity = {}
                if hasattr(self._client, "title_rarity_with_name"):
                    try:
                        rarity, title_name = await self._client.title_rarity_with_name(
                            tg_id, title_id
                        )
                    except XboxApiError:
                        pass
                if title_name:
                    await self._repo.upsert_title(title_id, title_name, platform)
                    if rarity:
                        await self._repo.cache_rarity(platform, title_id, rarity)
                    continue

                if hasattr(self._client, "resolve_title"):
                    try:
                        entry = await self._client.resolve_title(tg_id, title_id)
                    except XboxApiError as exc:
                        log.info("rarity backfill: title %s unresolvable (%s)", title_id, exc)
                        self._unanswerable.add(title_id)
                        continue
                    if entry is None or not entry.name:
                        self._unanswerable.add(title_id)
                        continue
                    await self._repo.upsert_title(
                        entry.title_id, entry.name, entry.platform, entry.icon_url
                    )
                    if rarity:
                        await self._repo.cache_rarity(entry.platform, title_id, rarity)
                else:
                    self._unanswerable.add(title_id)
