"""Self-healing bilingual descriptions for Xbox (2026-09-11, user request).

Every new Xbox account arrives with a fully uncached achievement history:
its backfill uses the one broad contract-2 call for the whole library, which
takes no language parameter at all (see services/description_backfill.py for
why that is the right shape for backfill itself). Steam and PSN have no such
gap. So the hole reopens with every registration, and a one-off script run
by hand is the wrong instrument for something that keeps coming back.

This job closes it continuously instead, a few titles per tick.

**Why a poller and not a cron'd script.** Xbox refreshes a per-user token,
and Microsoft invalidates the previous refresh token when it issues a new
one — two processes refreshing the same person concurrently logs that person
out of the bot. `XboxAuthService`'s own guard is an `asyncio.Lock`, which
serializes callers *inside one process* and does nothing across two. Running
this inside the bot puts it under that lock; running it as a separate
process would mean stopping the bot first, every time, forever. (That is
exactly what the one-time script needs, and why it is a script.)

The pace is deliberately unhurried: `TITLES_PER_TICK` titles a minute, two
requests each, against a budget of 300 requests per five minutes *per user
token*. A new account with a 200-title library catches up in about an hour,
invisibly, and nothing else the bot does ever notices.
"""

from __future__ import annotations

import logging

from bot.constants import Platform
from bot.db.repo import Repo
from bot.services.description_backfill import fill_xbox_title_any_owner
from bot.services.translate.auth import AnthropicAuth
from bot.services.xbox.client import XboxClient

log = logging.getLogger(__name__)

# Two requests per title, once a minute — 6 requests/min against Xbox's own
# 300-per-5-minutes-per-token. Small enough that it never competes with the
# presence and achievement pollers for the same budget.
TITLES_PER_TICK = 3

XBOX_PLATFORMS = (Platform.XBOX_MODERN, Platform.XBOX_360)


class DescriptionBackfill:
    def __init__(
        self,
        repo: Repo,
        client: XboxClient,
        anthropic_auth: AnthropicAuth,
        *,
        titles_per_tick: int = TITLES_PER_TICK,
    ) -> None:
        self._repo = repo
        self._client = client
        self._anthropic_auth = anthropic_auth
        self._titles_per_tick = titles_per_tick
        # Titles nothing could answer for — a delisted game, a title only an
        # account with a dead token owns. Without this the same title would
        # be retried every single minute forever, which is a hot loop against
        # someone else's API. Process-lifetime only: a restart tries again,
        # which is the right cadence for something that may simply have been
        # a bad afternoon at Microsoft.
        self._unanswerable: set[tuple[str, str]] = set()

    async def tick(self) -> None:
        titles = await self._repo.uncached_description_titles(
            XBOX_PLATFORMS, self._titles_per_tick + len(self._unanswerable)
        )
        remaining = self._titles_per_tick
        for platform, title_id, tg_id in titles:
            if remaining <= 0:
                break
            if (platform, title_id) in self._unanswerable:
                continue
            remaining -= 1
            try:
                cached = await fill_xbox_title_any_owner(
                    self._repo,
                    self._anthropic_auth,
                    self._client,
                    owners=[tg_id],
                    title_id=title_id,
                    platform=platform,
                )
            except Exception:
                # One title must never end a tick — the same rule every
                # other poller here follows.
                log.exception("description backfill failed for %s/%s", platform, title_id)
                self._unanswerable.add((platform, title_id))
                continue
            if cached is None:
                self._unanswerable.add((platform, title_id))
                continue
            if cached:
                log.info("cached %s descriptions for %s/%s", cached, platform, title_id)
            else:
                # The platform answered, but had nothing with a description
                # for us. Nothing will change on a retry either.
                self._unanswerable.add((platform, title_id))
