"""Periodic background catch-up for Steam (#89).

Mirrors Xbox's `poller/catch_up.py` (#82):
The presence poller only ever asks about the game somebody is in *right now*,
plus one look when leaving it (with a 3-minute grace queue). Achievements
earned while offline, in "Invisible" mode, or during Steam Cloud / network
sync delays might never be seen by the presence poller.

One account per tick, not all of them: `get_recently_played_games` is
lightweight (only games played in the last 2 weeks, usually 1-5 games),
and spread across the hour there is no burst at all.

For each account, we check recently played games. For any game with
`last_played > since`, we call `steam_fetcher.poll_title`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta

from bot.config import Settings
from bot.constants import AccountPlatform
from bot.db.repo import Repo, SteamPollTarget
from bot.poller.cadence import is_dormant
from bot.poller.steam_fetcher import SteamFetcher
from bot.services.steam import client as steam_client
from bot.services.steam.auth import SteamAuth
from bot.services.steam.client import SteamApiError
from bot.util import parse_iso, utcnow

log = logging.getLogger(__name__)

DEADLINE_SECONDS = 120.0


async def steam_catch_up_since(repo: Repo, steam_id: str, window_hours: int) -> datetime:
    """Where this Steam account's catch-up window starts (#89).

    Same principle as Xbox's `catch_up_since` (#82): the newest unlock already
    stored for this account, floored at `window_hours` in the past.
    """
    floor = utcnow() - timedelta(hours=window_hours)
    stored = parse_iso(await repo.account_latest_unlock(AccountPlatform.STEAM, steam_id))
    return max(stored, floor) if stored is not None else floor


async def catch_up_steam_account(
    settings: Settings,
    repo: Repo,
    fetcher: SteamFetcher,
    steam_auth: SteamAuth,
    tg_id: int,
    steam_id: str,
    persona_name: str,
    *,
    api_key: str | None = None,
) -> tuple[int, int]:
    """Check recently played games for one Steam account and poll titles played since baseline.

    Returns (titles_checked, published_count).
    """
    if api_key is None:
        api_key = await steam_auth.get_key()
        if api_key is None:
            return (0, 0)

    since = await steam_catch_up_since(repo, steam_id, settings.catchup_publish_window_hours)
    cutoff = since.timestamp()

    try:
        games = await steam_client.get_recently_played_games(api_key, steam_id)
    except SteamApiError as exc:
        log.info("recently played games for tg_id=%s skipped: %s", tg_id, exc)
        return (0, 0)

    candidates = [g for g in games if g.last_played > cutoff]
    if not candidates:
        return (0, 0)

    published = 0
    for game in candidates:
        try:
            published += await fetcher.poll_title(
                tg_id,
                steam_id,
                persona_name,
                game.appid,
                game.name,
                window_hours=settings.catchup_publish_window_hours,
            )
        except SteamApiError as exc:
            log.info("steam catch-up of appid=%s skipped: %s", game.appid, exc)

    return (len(candidates), published)


class SteamCatchUpPoller:
    def __init__(
        self,
        settings: Settings,
        repo: Repo,
        fetcher: SteamFetcher,
        steam_auth: SteamAuth,
    ) -> None:
        self._settings = settings
        self._repo = repo
        self._fetcher = fetcher
        self._steam_auth = steam_auth
        self._started = time.monotonic()
        self._last: dict[str, float] = {}

    async def tick(self) -> None:
        api_key = await self._steam_auth.get_key()
        if api_key is None:
            return

        target = await self._next_due()
        if target is None:
            return

        self._last[target.steam_id] = time.monotonic()
        try:
            titles, published = await asyncio.wait_for(
                self.catch_up_target(target, api_key=api_key),
                timeout=DEADLINE_SECONDS,
            )
        except TimeoutError:
            log.error(
                "hourly steam catch-up for tg_id=%s exceeded %.0fs",
                target.tg_id,
                DEADLINE_SECONDS,
            )
            return
        except Exception:
            log.exception("hourly steam catch-up for tg_id=%s failed", target.tg_id)
            return

        if titles or published:
            log.info(
                "hourly steam catch-up for tg_id=%s: %s titles, %s published",
                target.tg_id,
                titles,
                published,
            )

    async def catch_up_target(
        self, target: SteamPollTarget, *, api_key: str | None = None
    ) -> tuple[int, int]:
        """Check recently played games for one account and poll titles played since baseline.

        Returns (titles_checked, published_count).
        """
        return await catch_up_steam_account(
            self._settings,
            self._repo,
            self._fetcher,
            self._steam_auth,
            target.tg_id,
            target.steam_id,
            target.persona_name or target.steam_id,
            api_key=api_key,
        )

    def _target_interval(self, target: SteamPollTarget) -> int:
        if self._settings.catchup_interval_minutes == 0:
            return 0
        if is_dormant(
            target.last_online_at, target.linked_at, self._settings.catchup_idle_threshold_days
        ):
            return self._settings.catchup_idle_interval_minutes * 60
        return self._settings.catchup_interval_minutes * 60

    async def _next_due(self) -> SteamPollTarget | None:
        """The account that has waited longest past its interval."""
        now = time.monotonic()
        overdue = [
            target
            for target in await self._repo.steam_pollable_users()
            if now - self._last.get(target.steam_id, self._started) >= self._target_interval(target)
        ]
        if not overdue:
            return None
        return min(overdue, key=self._waiting_since)

    def _waiting_since(self, target: SteamPollTarget) -> tuple[float, bool]:
        seen = self._last.get(target.steam_id)
        return (seen if seen is not None else self._started, seen is not None)
