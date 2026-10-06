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
import hashlib
import logging

from bot.db.repo import Repo, StoredPatch
from bot.services.hltb_match import normalize
from bot.services.steam.auth import SteamAuth
from bot.services.steam_guides import Guide, guides_of, tip_from_lines
from bot.services.steam_news import fetch_patches, find_appid
from bot.services.translate.auth import AnthropicAuth
from bot.services.translate.guide_tips import locate_sections

log = logging.getLogger(__name__)

# Guides hardly change once written; a month keeps new ones coming in.


class SteamExtras:
    def __init__(
        self,
        repo: Repo,
        steam_auth: SteamAuth | None,
        anthropic_auth: AnthropicAuth | None = None,
    ) -> None:
        self._repo = repo
        self._steam_auth = steam_auth
        self._anthropic_auth = anthropic_auth
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
        yet). True once the tips are complete — False while Steam
        still holds some guides back, and a later call picks up the rest."""
        async with self._locks.setdefault(title_id, asyncio.Lock()):
            appid = await self.appid(title_id)
            if appid is None:
                return True
            _guides_at, patches_at = await self._repo.steam_app_checked(appid)
            if patches_at is None:
                await self.refresh_patches(appid)
            title = await self._repo.title_steam(title_id)
            # A visit only fills tips that were never worked out; a month-old
            # set is the schedule's job (`refresh_tips`), so a crowd opening
            # one game cannot send Steam a read each.
            if title is None or title.tips_checked_at is not None:
                return True
            return await self._fill_tips(title.platform, title_id, appid)

    async def refresh_tips(self, title_id: str) -> None:
        """Read the game's guides again, whatever is stored. The scheduled path."""
        async with self._locks.setdefault(title_id, asyncio.Lock()):
            title = await self._repo.title_steam(title_id)
            if title is None or title.steam_appid is None:
                return
            await self._fill_tips(title.platform, title_id, title.steam_appid)

    async def tips_due(self, title_id: str) -> bool:
        title = await self._repo.title_steam(title_id)
        if title is None:
            return False
        if title.steam_appid is None:
            return title.appid_due
        return title.tips_checked_at is None

    async def _fill_tips(self, platform: str, title_id: str, appid: int) -> bool:
        api_key = await self._steam_auth.get_key() if self._steam_auth else None
        if not api_key:
            return True
        catalog = await self._repo.title_achievement_names(platform, title_id)
        if not catalog:
            # Nothing to match the guides against yet; the catalog refresh
            # comes, and the next call finds it.
            return True
        # Which lines of a guide are an achievement's tip is for the model to say;
        # without its key there is nothing to do and nothing is stamped as read.
        if not (self._anthropic_auth and await self._anthropic_auth.get_key()):
            return True
        tips: dict[str, tuple[str, str]] = {}
        asked_in_vain = False

        async def take(guide: Guide) -> bool:
            """A guide (most popular first) that fills at least half of the game's
            achievements is a good one: it is taken, and that is all, the others are
            not even read. Until one does, what each gives is kept, the first
            guide's account of an achievement standing."""
            nonlocal asked_in_vain
            pointed = await self._pointed_at(platform, title_id, guide, catalog)
            if pointed is None:
                asked_in_vain = True
                return False
            if len(pointed) * 2 >= len(catalog):
                tips.clear()
                tips.update({i: (text, guide.file_id) for i, text in pointed.items()})
                return True
            for achievement_id, text in pointed.items():
                tips.setdefault(achievement_id, (text, guide.file_id))
            return False

        found = await guides_of(appid, api_key, take)
        # A model that could not be asked leaves the game to be read again.
        complete = found.complete and not asked_in_vain
        await self._repo.replace_title_tips(platform, title_id, tips, complete=complete)
        if complete:
            await self._repo.mark_steam_guides_read(appid)
        log.info(
            "steam tips for %s (app %s): %s of %s%s",
            title_id,
            appid,
            len(tips),
            len(catalog),
            "" if complete else ", more to read",
        )
        return complete

    async def _pointed_at(
        self, platform: str, title_id: str, guide: Guide, catalog: list
    ) -> dict[str, str] | None:
        """{achievement id: tip} for what Haiku picked in this guide; empty
        without a key or when the model gave nothing usable. The model is asked
        only when this guide, or what the game's list tells it, is not what it was
        last time: otherwise the stored answer is cut into tips again, so a guide
        that was asked once never costs another call, kept or not."""
        api_key = await self._anthropic_auth.get_key() if self._anthropic_auth else None
        if not api_key:
            return {}
        fingerprint = _fingerprint(guide, catalog)
        before = await self._repo.guide_read(title_id, guide.file_id)
        if before is not None and before[0] == fingerprint:
            return _tips_of(guide, before[1])
        numbers = {
            normalize(name): number
            for number, row in enumerate(catalog, start=1)
            for name in (row.name_en, row.name_ru)
            if name
        }
        marks = {
            i: numbers[normalize(line)]
            for i, line in enumerate(guide.lines)
            if normalize(line) in numbers
        }
        sections = await locate_sections(
            api_key, guide.lines, [_asked_about(row) for row in catalog], marks
        )
        if sections is None:
            return None
        answer = {catalog[index].achievement_id: ranges for index, ranges in sections.items()}
        await self._repo.save_guide_read(title_id, guide.file_id, fingerprint, answer)
        return _tips_of(guide, answer)

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
                    kind=p.kind,
                    image_url=p.image,
                )
                for p in patches
            ],
        )


def _asked_about(row) -> tuple[str, str]:
    """An achievement as the model is shown it: one name, one description."""
    return (row.name_en or row.name_ru or "", row.description_en or row.description_ru or "")


def _tips_of(guide: Guide, answer: dict[str, list[tuple[int, int]]]) -> dict[str, str]:
    found: dict[str, str] = {}
    for achievement_id, ranges in answer.items():
        text = tip_from_lines(guide, ranges)
        if text:
            found[achievement_id] = text
    return found


def _fingerprint(guide: Guide, catalog: list) -> str:
    """Exactly what a question to the model depends on: the guide's lines, and each
    achievement as the prompt shows it plus both names (the name marks use them).
    A translation filled in later, which the prompt does not show, changes nothing."""
    digest = hashlib.sha256()
    for line in guide.lines:
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    for row in catalog:
        parts = (row.achievement_id, row.name_en, row.name_ru, *_asked_about(row))
        digest.update("\x1f".join(str(part or "") for part in parts).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()
