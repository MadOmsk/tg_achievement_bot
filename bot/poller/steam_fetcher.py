"""Fetching Steam achievements and backfill (SPEC 9, M-Steam-2c/2d) — the
Steam counterpart of poller/fetcher.py. Smaller than the Xbox version: no
`ensure_title_name` equivalent (Steam's own presence already carries the
game's display name, `gameextrainfo` — SPEC 9, M-Steam-2c), and no title-
history refresh (no Steam analogue exists yet, scoped out of 2c on
purpose).

The API key is read lazily from SteamAuth on each call rather than held as
a constructor copy (#17) — so an admin's set/change/clear in the panel
takes effect without a restart.
"""

from __future__ import annotations

import asyncio
import logging

from bot.constants import Platform
from bot.db.repo import AchievementRow, Repo
from bot.i18n import gettext
from bot.poller.publisher import Publisher
from bot.services.rows import to_achievement_row
from bot.services.steam.achievements import fetch_unlocked
from bot.services.steam.auth import SteamAuth, SteamNotConfiguredError
from bot.services.steam.client import (
    OwnedGame,
    SteamApiError,
    SteamGameDetailsPrivateError,
    get_owned_games,
    get_presence_batch,
    rate_limit_usage,
)
from bot.services.translate.auth import AnthropicAuth

log = logging.getLogger(__name__)

_ = lambda key, **kwargs: gettext("steamfetcher", key, **kwargs)  # noqa: E731

# A backfill's per-game concurrency — Xbox never needed this second level
# (one call covers its whole library), Steam genuinely does since
# fetch_unlocked() is one call per game (SPEC 9, M-Steam-2d). Module
# constant, not a Settings field: internal tuning, not something the admin
# would ever need to reach for.
GAME_BACKFILL_CONCURRENCY = 5


class SteamFetcher:
    def __init__(
        self,
        repo: Repo,
        steam_auth: SteamAuth,
        publisher: Publisher,
        concurrency: int = 2,
        *,
        anthropic_auth: AnthropicAuth,
    ) -> None:
        self._repo = repo
        self._steam_auth = steam_auth
        self._publisher = publisher
        self._anthropic_auth = anthropic_auth
        self._backfill_slots = asyncio.Semaphore(concurrency)  # people backfilling at once
        self._game_slots = asyncio.Semaphore(GAME_BACKFILL_CONCURRENCY)  # games within one

    def api_usage(self) -> list[tuple[int, int, float]]:
        """(used, limit, window_seconds) — the admin panel's Steam line,
        alongside Fetcher's own Xbox one (SPEC 6.4)."""
        return rate_limit_usage()

    async def poll_title(
        self,
        tg_id: int,
        steam_id: str,
        persona_name: str,
        appid: str,
        game_name: str | None,
    ) -> int:
        """Fetch one game's achievements, keep the new ones, publish them."""
        api_key = await self._steam_auth.require_key()
        parsed = await fetch_unlocked(self._repo, self._anthropic_auth, api_key, steam_id, appid)
        rows = [to_achievement_row(item) for item in parsed]
        new_rows = await self._repo.insert_new_achievements_steam(
            tg_id, steam_id, rows, is_backfill=False
        )
        await self._repo.mark_steam_achievements_polled(steam_id)
        if not new_rows:
            return 0

        log.info("tg_id=%s unlocked %s new steam achievements in %s", tg_id, len(new_rows), appid)
        await self._publisher.publish(tg_id, steam_id, persona_name, new_rows, game_name)
        return len(new_rows)

    async def refresh_user(self, tg_id: int, steam_id: str, persona_name: str) -> str:
        """An out-of-turn look at one person, for the admin card (SPEC 6.4)
        — Steam's counterpart of Fetcher.refresh_user() (2026-09-05
        follow-up: the admin panel never had a Steam equivalent at all)."""
        try:
            api_key = await self._steam_auth.require_key()
        except SteamNotConfiguredError:
            return _("steamfetcher-not-configured")
        # Re-check achievement visibility as part of the resync (#5, user
        # request: "ресинк перепроверяет же статус доступности ачивок?") —
        # it did not, before this. A cheap probe, discarding the games list:
        # backfill() is the one that actually re-stores anything.
        try:
            await get_owned_games(api_key, steam_id)
        except SteamGameDetailsPrivateError:
            await self._repo.set_achievements_visible(tg_id, Platform.STEAM, False)
        except SteamApiError:
            pass  # transient failure — don't overwrite the last known-good status on a blip
        else:
            await self._repo.set_achievements_visible(tg_id, Platform.STEAM, True)

        try:
            snapshots = await get_presence_batch(api_key, [steam_id])
        except SteamApiError as exc:
            return _("steamfetcher-refresh-failed", error=exc)
        snapshot = snapshots.get(steam_id)
        if snapshot is None:
            return _("steamfetcher-no-profile")

        await self._repo.save_steam_presence_state(
            steam_id, snapshot.persona_state, snapshot.gameid, snapshot.game_name, changed=False
        )
        published = 0
        if snapshot.persona_state != 0 and snapshot.gameid is not None:
            published = await self.poll_title(
                tg_id,
                steam_id,
                snapshot.persona_name or persona_name,
                snapshot.gameid,
                snapshot.game_name,
            )

        where = snapshot.game_name or snapshot.gameid or _("steamfetcher-no-game")
        state = (
            _("steamfetcher-online", where=where)
            if snapshot.persona_state != 0
            else _("steamfetcher-offline")
        )
        return _("steamfetcher-refreshed", state=state, published=published)

    async def backfill(self, tg_id: int, steam_id: str) -> int:
        """Mark everything already unlocked as seen, publishing nothing —
        same principle as Xbox's backfill (SPEC 5.6), just spread over one
        request per played game instead of one call for the whole library
        (SPEC 9, M-Steam-2d: no Steam equivalent of Xbox's contract 2)."""
        api_key = await self._steam_auth.require_key()
        async with self._backfill_slots:
            try:
                games = await get_owned_games(api_key, steam_id)
            except SteamGameDetailsPrivateError:
                # "My Profile" passed connect_steam's own is_public check,
                # but the separate "Game details" toggle is still private —
                # #39 already surfaces this to the person via
                # _backfill_and_notify's own catch; recorded here too (#5)
                # so /panel's login row reflects the same finding instead of
                # only ever logging it. Re-raised unchanged — #39's message
                # still needs to see this exact exception.
                await self._repo.set_achievements_visible(tg_id, Platform.STEAM, False)
                raise
            await self._repo.set_achievements_visible(tg_id, Platform.STEAM, True)
            rows: list[AchievementRow] = []

            async def one(game: OwnedGame) -> None:
                async with self._game_slots:
                    try:
                        parsed = await fetch_unlocked(
                            self._repo, self._anthropic_auth, api_key, steam_id, game.appid
                        )
                    except SteamApiError as exc:
                        log.info("steam backfill of appid=%s skipped: %s", game.appid, exc)
                        return
                    rows.extend(to_achievement_row(item) for item in parsed)

            await asyncio.gather(*(one(game) for game in games))
            await self._repo.insert_new_achievements_steam(tg_id, steam_id, rows, is_backfill=True)
            log.info("steam backfill for tg_id=%s stored %s achievements", tg_id, len(rows))
            return len(rows)
