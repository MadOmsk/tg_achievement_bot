"""A game's Steam side — its Steam app, its achievements' tips from the Steam
community's guides, its patch notes — found and kept in the database.

Filled like the HLTB entry (#131): right after a game's first new achievement
is published (the fetchers call `ensure_title`), and on a visit to its page if
it still is not. Patch notes are then kept fresh by poller/patch_refresh.py;
guides hardly change and are re-read only when a page is visited a month on.
Nothing is sent to a chat (owner, 2026-09-30).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from bot.db.repo import Repo, StoredPatch
from bot.services.steam.auth import SteamAuth
from bot.services.steam_guides import Wanted, everything_named, guides_of, tip_for
from bot.services.steam_news import fetch_patches, find_appid
from bot.util import parse_iso, utcnow

log = logging.getLogger(__name__)

# Guides hardly change once written; a month keeps new ones coming in.
TIPS_TTL = timedelta(days=30)


class SteamExtras:
    def __init__(self, repo: Repo, steam_auth: SteamAuth | None) -> None:
        self._repo = repo
        self._steam_auth = steam_auth
        self._locks: dict[str, asyncio.Lock] = {}
        # Background fills in flight: a reference keeps each alive until done.
        self._running: dict[str, asyncio.Task[bool]] = {}

    def ensure_title(self, title_id: str) -> None:
        """Fill the game in the background if it is not filled yet — never on
        the publishing path itself: reading guides takes a while (the site is
        read slowly on purpose). A no-op while a fill of it is running."""
        if title_id in self._running:
            return
        task = asyncio.create_task(self._fill_logged(title_id))
        self._running[title_id] = task
        task.add_done_callback(lambda _t: self._running.pop(title_id, None))

    async def _fill_logged(self, title_id: str) -> bool:
        try:
            return await self.fill_title(title_id)
        except Exception:
            log.exception("steam extras failed for title %s", title_id)
            return False

    async def appid(self, title_id: str) -> int | None:
        """The game's Steam app, looked up now if it is time to."""
        title = await self._repo.title_steam(title_id)
        if title is None:
            return None
        if title.steam_appid is not None or not title.appid_due:
            return title.steam_appid
        appid = await find_appid(list(title.names), title.hltb_id)
        await self._repo.record_steam_appid(title_id, appid)
        return appid

    async def fill_title(self, title_id: str) -> bool:
        """Everything the game's Steam side has that is not stored yet: its app,
        its patches (if the app was never read), its tips (if never worked out
        or a month old). True once the tips are complete — False while Steam
        still holds some guides back, and a later call picks up the rest."""
        async with self._locks.setdefault(title_id, asyncio.Lock()):
            appid = await self.appid(title_id)
            if appid is None:
                return True
            _guides_at, patches_at = await self._repo.steam_app_checked(appid)
            if patches_at is None:
                await self.refresh_patches(appid)
            title = await self._repo.title_steam(title_id)
            if title is None or not _tips_due(title.tips_checked_at):
                return True
            return await self._fill_tips(title.platform, title_id, appid)

    async def tips_due(self, title_id: str) -> bool:
        title = await self._repo.title_steam(title_id)
        if title is None:
            return False
        if title.steam_appid is None:
            return title.appid_due
        return _tips_due(title.tips_checked_at)

    async def _fill_tips(self, platform: str, title_id: str, appid: int) -> bool:
        api_key = await self._steam_auth.get_key() if self._steam_auth else None
        if not api_key:
            return True
        catalog = await self._repo.get_title_achievements(platform, title_id)
        if not catalog:
            # Nothing to match the guides against yet; the catalog refresh
            # comes, and the next call finds it.
            return True
        found = await guides_of(appid, api_key)
        wanted = [
            Wanted(
                names=tuple(n for n in (row.name_en, row.name_ru) if n),
                descriptions=tuple(d for d in (row.description_en, row.description_ru) if d),
            )
            for row in catalog
        ]
        everything = everything_named(wanted)
        tips: dict[str, tuple[str, str]] = {}
        for row, want in zip(catalog, wanted, strict=True):
            tip = tip_for(found.guides, want, everything)
            if tip is not None:
                tips[row.achievement_id] = (tip.text, tip.guide_id)
        await self._repo.replace_title_tips(platform, title_id, tips, complete=found.complete)
        if found.complete:
            await self._repo.mark_steam_guides_read(appid)
        log.info(
            "steam tips for %s (app %s): %s of %s%s",
            title_id,
            appid,
            len(tips),
            len(catalog),
            "" if found.complete else ", more to read",
        )
        return found.complete

    async def refresh_patches(self, appid: int) -> None:
        """Read the app's patch notes now. Steam unreachable: nothing changes,
        and the next refresh tries again."""
        patches = await fetch_patches(appid)
        if patches is None:
            return
        await self._repo.save_game_patches(
            appid,
            [
                StoredPatch(
                    gid=p.gid,
                    title=p.title,
                    published_at=p.date,
                    text_en=p.text,
                    title_ru=None,
                    text_ru=None,
                )
                for p in patches
            ],
        )


def _tips_due(checked_at: str | None) -> bool:
    if checked_at is None:
        return True
    when = parse_iso(checked_at)
    return when is None or utcnow() - when > TIPS_TTL
