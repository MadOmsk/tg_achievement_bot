"""Fetching achievements, deduplication and backfill (SPEC 5.3, 5.4, 5.6)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from bot.constants import Platform, PresenceState
from bot.db.repo import AchievementRow, Repo, TitleHistoryRow
from bot.i18n import translator
from bot.poller.publisher import Publisher
from bot.services.rows import to_achievement_row
from bot.services.translate.auth import AnthropicAuth
from bot.services.translate.descriptions import bilingual_descriptions
from bot.services.xbox.client import TitleHistoryEntry, XboxApiError, XboxClient
from bot.services.xbox.models import ParsedAchievement
from bot.util import parse_iso, utcnow

log = logging.getLogger(__name__)


class Fetcher:
    def __init__(
        self,
        repo: Repo,
        client: XboxClient,
        publisher: Publisher,
        concurrency: int = 2,
        *,
        anthropic_auth: AnthropicAuth,
    ) -> None:
        self._repo = repo
        self._client = client
        self._publisher = publisher
        self._anthropic_auth = anthropic_auth
        self._backfill_slots = asyncio.Semaphore(concurrency)

    def api_usage(self) -> list[tuple[int, int, float]]:
        """(used, limit, window_seconds) — surfaced in the admin panel
        (SPEC 6.4) so "are we anywhere near a limit" has an actual answer."""
        return self._client.rate_limit_usage()

    async def poll_title(
        self,
        tg_id: int,
        xuid: str,
        gamertag: str,
        title_id: str,
        platform: Platform,
        title_name: str | None,
    ) -> int:
        """Fetch one game's achievements, keep the new ones, publish them."""
        parsed = await self._client.title_achievements(tg_id, title_id, platform)
        await self._fill_x360_icon(tg_id, title_id, platform, parsed)
        await self._bilingual_descriptions(tg_id, title_id, platform, parsed)
        rows = [to_achievement_row(item) for item in parsed]
        new_rows = await self._repo.insert_new_achievements(xuid, rows, is_backfill=False)
        await self._repo.mark_achievements_polled(xuid)
        if not new_rows:
            return 0

        log.info("tg_id=%s unlocked %s new achievements in %s", tg_id, len(new_rows), title_id)
        resolved = await self.ensure_title_name(tg_id, title_id, title_name)
        await self._publisher.publish(tg_id, xuid, gamertag, new_rows, resolved)
        return len(new_rows)

    async def ensure_title_name(
        self, tg_id: int, title_id: str, from_presence: str | None
    ) -> str | None:
        """Presence leaves the name empty for PC titles, so ask titlehub once.

        "неизвестная игра" in a published message is worse than one extra
        request per game we have never seen.
        """
        if from_presence:
            return from_presence
        cached = await self._repo.title_name(title_id)
        if cached:
            return cached
        try:
            entry = await self._client.resolve_title(tg_id, title_id)
        except XboxApiError as exc:
            log.info("could not resolve title %s: %s", title_id, exc)
            return None
        if entry is None or not entry.name:
            return None
        await self._repo.upsert_title(entry.title_id, entry.name, entry.platform)
        return entry.name

    async def ensure_title_icon(self, tg_id: int, title_id: str) -> str | None:
        """Box art as a stand-in for an Xbox 360 achievement icon (SPEC 7.1)
        — contract 1's achievement payload only ever carries a bare imageId
        int, no documented way to turn it into a URL at all (verified live
        against the real API: the raw response has nothing image-shaped
        besides that number). No `from_presence` shortcut like
        ensure_title_name has — presence never carries box art either way.
        """
        cached = await self._repo.title_icon_url(title_id)
        if cached:
            return cached
        try:
            entry = await self._client.resolve_title(tg_id, title_id)
        except XboxApiError as exc:
            log.info("could not resolve icon for title %s: %s", title_id, exc)
            return None
        if entry is None or not entry.icon_url:
            return None
        await self._repo.upsert_title(entry.title_id, entry.name, entry.platform, entry.icon_url)
        return entry.icon_url

    async def _fill_x360_icon(
        self, tg_id: int, title_id: str, platform: Platform, parsed: list[ParsedAchievement]
    ) -> None:
        """Shared by poll_title() and catch_up() — both publish live x360
        unlocks and must agree on the icon, not just the one that happens
        to run more often."""
        if platform != Platform.XBOX_360:
            return
        icon_url = await self.ensure_title_icon(tg_id, title_id)
        if icon_url:
            for item in parsed:
                item.icon_url = icon_url

    async def _bilingual_descriptions(
        self, tg_id: int, title_id: str, platform: Platform, parsed: list[ParsedAchievement]
    ) -> None:
        """Mutates each item's `.description` in place — same shape
        `_fill_x360_icon` above already uses. Only called from poll_title/
        catch_up (2026-09-09): both are the only two paths that actually
        publish what they fetch here — backfill's own x360 pass (below)
        deliberately skips this, translating history nobody will ever see
        would just be wasted API/LLM cost for nothing.

        A second `ru-RU` request, only for achievements not already in
        achievement_description_cache — once every achievement in a game
        has been seen once, from any account, this never runs again for
        it. Xbox's own English text is left as `.description` for anything
        the bilingual lookup couldn't resolve (no cache hit and the second
        request came back empty/failed) — same "degrade to the language
        already fetched" shape services/steam/achievements.py's own
        version of this uses.
        """
        candidates = {item.achievement_id: item.description for item in parsed if item.description}
        if not candidates:
            return

        result: dict[str, tuple[str | None, str | None]] = {}
        uncached: dict[str, str] = {}
        for achievement_id, english_text in candidates.items():
            cached = await self._repo.get_cached_description(platform, title_id, achievement_id)
            if cached is not None:
                result[achievement_id] = (cached.description_ru, cached.description_en)
            else:
                uncached[achievement_id] = english_text

        if uncached:
            try:
                russian_parsed = await self._client.title_achievements(
                    tg_id, title_id, platform, language="ru-RU"
                )
            except XboxApiError as exc:
                log.info("bilingual fetch for title %s skipped: %s", title_id, exc)
                russian_parsed = []
            russian_by_id = {item.achievement_id: item.description for item in russian_parsed}
            native = {
                achievement_id: (russian_text, english_text)
                for achievement_id, english_text in uncached.items()
                if (russian_text := russian_by_id.get(achievement_id)) is not None
            }
            if native:
                resolved = await bilingual_descriptions(
                    self._repo, self._anthropic_auth, platform, title_id, native
                )
                result.update(resolved)

        for item in parsed:
            resolved_pair = result.get(item.achievement_id)
            if resolved_pair is not None and resolved_pair[0] is not None:
                item.description = resolved_pair[0]

    async def backfill(self, tg_id: int, xuid: str) -> int:
        """Mark everything already unlocked as seen, publishing nothing.

        Without this the first poll after connecting would dump thousands of
        old achievements into the chat.
        """
        async with self._backfill_slots:
            rows = [to_achievement_row(item) for item in await self._client.all_achievements(tg_id)]

            # Contract 2 covers modern titles only — verified against a live
            # account, where an Xbox 360 game with 33 unlocked achievements was
            # absent from the full list. Without this second pass the first
            # session in such a game would look like 33 fresh unlocks.
            history = await self._client.title_history(tg_id)
            for entry in history:
                if entry.platform != Platform.XBOX_360:
                    continue
                try:
                    parsed = await self._client.title_achievements(
                        tg_id, entry.title_id, Platform.XBOX_360
                    )
                except XboxApiError as exc:
                    log.info("x360 backfill of %s skipped: %s", entry.title_id, exc)
                    continue
                rows.extend(to_achievement_row(item) for item in parsed)

            await self._repo.insert_new_achievements(xuid, rows, is_backfill=True)
            await self._save_history(tg_id, xuid, history)
            log.info("backfill for tg_id=%s stored %s achievements", tg_id, len(rows))
            return len(rows)

    async def catch_up(
        self,
        tg_id: int,
        xuid: str,
        gamertag: str,
        since: datetime | None,
        window_hours: int,
        max_titles: int,
    ) -> tuple[int, int]:
        """Pick up what was unlocked while the bot was down (SPEC 5.8).

        Only achievements newer than the window reach the chat. Older ones are
        still recorded, just not announced: after a fortnight of downtime a
        chat does not want the archive, and after a one-minute restart nothing
        should be lost.
        """
        async with self._backfill_slots:
            history = await self._client.title_history(tg_id)
            await self._save_history(tg_id, xuid, history)

            candidates = _played_since(history, since)[:max_titles]
            if not candidates:
                return 0, 0

            publish_after = utcnow() - timedelta(hours=window_hours)
            published = 0
            for entry in candidates:
                try:
                    parsed = await self._client.title_achievements(
                        tg_id, entry.title_id, entry.platform
                    )
                except XboxApiError as exc:
                    log.info("catch-up skipped title %s: %s", entry.title_id, exc)
                    continue
                await self._fill_x360_icon(tg_id, entry.title_id, entry.platform, parsed)
                await self._bilingual_descriptions(tg_id, entry.title_id, entry.platform, parsed)

                new_rows = await self._repo.insert_new_achievements(
                    xuid, [to_achievement_row(item) for item in parsed], is_backfill=False
                )
                fresh = [row for row in new_rows if _unlocked_after(row, publish_after)]
                if fresh:
                    await self._publisher.publish(tg_id, xuid, gamertag, fresh, entry.name)
                    published += len(fresh)

            log.info(
                "catch-up for tg_id=%s: %s titles, %s published",
                tg_id,
                len(candidates),
                published,
            )
            return len(candidates), published

    async def refresh_user(self, tg_id: int, xuid: str, gamertag: str, locale: str) -> str:
        """An out-of-turn look at one person, for the admin card (SPEC 6.4).

        The only on-demand API call in the interface, so it does the whole
        round: presence, the current game's achievements, title history.
        """
        _ = translator("fetcher", locale)
        snapshot = await self._client.presence(tg_id)
        await self._repo.save_presence_state(
            xuid, snapshot.state, snapshot.title_id, snapshot.title_name, changed=False
        )

        published = 0
        if snapshot.in_game and snapshot.title_id:
            published = await self.poll_title(
                tg_id, xuid, gamertag, snapshot.title_id, snapshot.platform, snapshot.title_name
            )
        await self.refresh_title_history(tg_id, xuid)

        where = snapshot.title_name or snapshot.title_id or _("fetcher-no-game")
        state = (
            _("fetcher-online", where=where)
            if snapshot.state == PresenceState.ONLINE
            else _("fetcher-offline")
        )
        return _("fetcher-refreshed", state=state, published=published)

    async def refresh_title_history(self, tg_id: int, xuid: str) -> None:
        """Source of /stats, /top and of the gamerscore in the panel (SPEC 5.4)."""
        await self._save_history(tg_id, xuid, await self._client.title_history(tg_id))

    async def _save_history(self, tg_id: int, xuid: str, history: list) -> None:
        rows = [
            TitleHistoryRow(
                title_id=entry.title_id,
                name=entry.name,
                platform=entry.platform,
                current_gamerscore=entry.current_gamerscore,
                max_gamerscore=entry.max_gamerscore,
                achievements_unlocked=entry.achievements_unlocked,
                achievements_total=entry.achievements_total,
                last_played_at=entry.last_played_at,
            )
            for entry in history
        ]
        if not rows:
            return
        await self._repo.save_title_history(xuid, rows)

        # From the profile, not from the sum above: the title history request is
        # capped, so an account with more games than the cap would show too low
        # a score.
        try:
            snapshot = await self._client.profile(tg_id)
        except XboxApiError as exc:
            log.info("profile for tg_id=%s not refreshed: %s", tg_id, exc)
            return
        if snapshot.gamerscore is not None:
            await self._repo.update_gamerscore(tg_id, snapshot.gamerscore)
        # The gamertags came in the same response (#51). Xbox used to store
        # them once at connect and never again, so a rename left the bot
        # calling someone by an old name and pointing at a dead profile
        # link — both Xbox links are built from the nickname, not the XUID.
        if snapshot.gamertag or snapshot.gamertag_modern:
            await self._repo.update_xbox_names(
                tg_id, gamertag=snapshot.gamertag, gamertag_modern=snapshot.gamertag_modern
            )


def _played_since(
    history: list[TitleHistoryEntry], since: datetime | None
) -> list[TitleHistoryEntry]:
    """Games touched after our last look, most recent first."""
    entries = [(parse_iso(entry.last_played_at), entry) for entry in history]
    fresh = [
        (played, entry)
        for played, entry in entries
        if played is not None and (since is None or played > since)
    ]
    fresh.sort(key=lambda pair: pair[0], reverse=True)
    return [entry for _, entry in fresh]


def _unlocked_after(row: AchievementRow, moment: datetime) -> bool:
    unlocked = parse_iso(row.unlocked_at)
    # An unknown date is not proof of freshness — those stay unpublished.
    return unlocked is not None and unlocked >= moment
