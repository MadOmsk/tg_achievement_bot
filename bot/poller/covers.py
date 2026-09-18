"""Game covers: find the URL, download the file, once per game, forever.

The Mini App shows a game's art beside every achievement and on every row of
its feed. On production, of 2544 stored titles exactly **two** had any —
`titles.icon_url` was only ever filled for the handful of Xbox 360 games
whose achievement messages borrow the box art for want of an icon of their
own.

What each platform costs is completely different, and this walker exists for
exactly one of them:

* **Steam** — free. The capsule lives at a fixed path under Steam's CDN, so
  the URL is derived from the appid with no request at all
  (`steam/client.py::cover_url`).
* **PSN** — free. `title_icon_url` already arrives inside the trophy-title
  list the scan walks anyway; it is written as the scan goes, so existing
  games fill in by themselves within a scan cycle.
* **Xbox** — one titlehub request per game, through *somebody's own token*,
  which is what needs rationing and what sets the pace here.

A game is visited once and never again: art does not change when a game is
released, unlike a profile picture. `cover_checked_at` is stamped on every
visit, found or not, so a game nobody can find art for leaves the queue
instead of being retried every minute for the rest of time.

**Why a poller and not a script**, the same reason `rarity_backfill.py` is
one: Xbox rotates a per-user refresh token and Microsoft invalidates the
previous one, so two processes refreshing the same person log that person
out. Running here puts this under `XboxAuthService`'s own lock.
"""

from __future__ import annotations

import logging

from bot.constants import AccountPlatform, account_platform_of
from bot.db.repo import Repo, TitleCoverRow
from bot.services import covers
from bot.services.steam.client import cover_url as steam_cover_url
from bot.services.xbox.client import XboxApiError, XboxClient

log = logging.getLogger(__name__)

# Gentler than the rarity walker's five: every one of these is a download as
# well as a lookup, and nobody is waiting on a cover. At three a minute
# production's 2544 titles are done in about fourteen hours, entirely inside
# the quota the presence and achievement pollers leave unused.
TITLES_PER_TICK = 3


class CoverRefresh:
    def __init__(
        self, repo: Repo, client: XboxClient, *, titles_per_tick: int = TITLES_PER_TICK
    ) -> None:
        self._repo = repo
        self._client = client
        self._titles_per_tick = titles_per_tick

    async def tick(self) -> None:
        for title in await self._repo.titles_needing_cover(self._titles_per_tick):
            try:
                await self._visit(title)
            except Exception:
                # One game's bad minute is not the tick's problem — the same
                # isolation every other poller here keeps.
                log.exception("cover refresh failed for title %s", title.title_id)

    async def _visit(self, title: TitleCoverRow) -> None:
        url = title.icon_url or await self._find_url(title)
        if not url:
            # Stamped anyway: without this the same unanswerable game comes
            # back at the head of the queue on the very next tick.
            await self._repo.set_title_cover(title.title_id)
            return

        saved = await covers.download(url, covers.cover_name(title.platform, title.title_id))
        if saved is None:
            # The URL is worth keeping even when the download failed — the
            # Mini App can load it straight from the platform's CDN, and the
            # next visit tries the bytes again.
            await self._repo.set_title_cover(title.title_id, icon_url=url)
            return

        path, digest = saved
        await self._repo.set_title_cover(
            title.title_id, icon_url=url, cover_path=path, cover_hash=digest
        )
        log.info("cover stored for %s (%s)", title.title_id, title.name)

    async def _find_url(self, title: TitleCoverRow) -> str | None:
        """Where this platform keeps its art, or None when it cannot say."""
        platform = account_platform_of(title.platform or "")
        if platform == AccountPlatform.STEAM:
            return steam_cover_url(title.title_id)
        if platform == AccountPlatform.PSN:
            # Sony's own icon arrives with the trophy titles the scan already
            # walks, so there is nothing useful to ask here — a PSN game
            # without one has simply not been scanned since covers existed.
            return None
        if title.owner_tg_id is None:
            return None
        try:
            entry = await self._client.resolve_title(title.owner_tg_id, title.title_id)
        except XboxApiError as exc:
            log.info("cover lookup for title %s unanswerable (%s)", title.title_id, exc)
            return None
        return entry.icon_url if entry else None
