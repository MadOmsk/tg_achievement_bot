"""APScheduler wiring: one tick a minute plus two housekeeping jobs.

APScheduler rather than a bare asyncio loop for `coalesce` and `max_instances`:
a tick that overruns must not pile up behind itself.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from bot.db.repo import Repo
from bot.poller.admin_refresh import AdminPanelRefresh
from bot.poller.avatars import AvatarRefresh
from bot.poller.catch_up import CatchUpPoller
from bot.poller.covers import CoverRefresh
from bot.poller.daily import DailySummary
from bot.poller.description_backfill import DescriptionBackfill
from bot.poller.fetcher import Fetcher
from bot.poller.flood_flush import FloodFlush
from bot.poller.message_cleanup import MessageCleanup
from bot.poller.online_refresh import OnlineAutoRefresh
from bot.poller.presence import PresencePoller
from bot.poller.psn_fetcher import PsnFetcher
from bot.poller.psn_presence import PsnPresencePoller
from bot.poller.psn_trophy_groups import PsnTrophyGroups
from bot.poller.rarity_backfill import RarityBackfill
from bot.poller.reminders import ReminderJob
from bot.poller.service_health import ServiceHealth
from bot.poller.steam_catch_up import SteamCatchUpPoller
from bot.poller.steam_localization import SteamLocalization
from bot.poller.steam_presence import SteamPresencePoller
from bot.poller.title_platforms import TitlePlatformsRefresh

log = logging.getLogger(__name__)

TICK_SECONDS = 60


class PollerScheduler:
    def __init__(
        self,
        poller: PresencePoller,
        fetcher: Fetcher,
        reminders: ReminderJob,
        daily: DailySummary,
        repo: Repo,
        steam_poller: SteamPresencePoller,
        message_cleanup: MessageCleanup,
        online_refresh: OnlineAutoRefresh,
        service_health: ServiceHealth,
        admin_refresh: AdminPanelRefresh,
        psn_fetcher: PsnFetcher,
        psn_presence: PsnPresencePoller,
        flood_flush: FloodFlush,
        description_backfill: DescriptionBackfill,
        rarity_backfill: RarityBackfill,
        steam_localization: SteamLocalization,
        avatar_refresh: AvatarRefresh,
        catch_up: CatchUpPoller,
        cover_refresh: CoverRefresh,
        steam_catch_up: SteamCatchUpPoller,
        title_platforms: TitlePlatformsRefresh,
        psn_trophy_groups: PsnTrophyGroups,
    ) -> None:
        self._poller = poller
        self._fetcher = fetcher
        self._reminders = reminders
        self._daily = daily
        self._repo = repo
        self._steam_poller = steam_poller
        self._message_cleanup = message_cleanup
        self._online_refresh = online_refresh
        self._service_health = service_health
        self._admin_refresh = admin_refresh
        self._psn_fetcher = psn_fetcher
        self._psn_presence = psn_presence
        self._flood_flush = flood_flush
        self._description_backfill = description_backfill
        self._rarity_backfill = rarity_backfill
        self._steam_localization = steam_localization
        self._avatar_refresh = avatar_refresh
        self._catch_up = catch_up
        self._cover_refresh = cover_refresh
        self._title_platforms = title_platforms
        self._psn_trophy_groups = psn_trophy_groups
        self._steam_catch_up = steam_catch_up
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    def start(self) -> None:
        self._scheduler.add_job(
            self._poller.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="presence",
            coalesce=True,
            max_instances=1,
        )
        # Registered unconditionally, same as reminders/daily_summary below —
        # the tick itself exits early when Steam isn't configured (SPEC 9,
        # M-Steam-2c), simpler than conditionally building the schedule.
        self._scheduler.add_job(
            self._steam_poller.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="steam_presence",
            coalesce=True,
            max_instances=1,
        )
        # Every minute, but it acts on at most one account and only once
        # that account's own hour is up (#82) — the interval lives in the
        # poller, not in the trigger, so one slow account cannot delay the
        # next one's turn.
        self._scheduler.add_job(
            self._catch_up.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="catch_up",
            coalesce=True,
            max_instances=1,
        )
        # Hourly catch-up for Steam via recently played games (#89).
        self._scheduler.add_job(
            self._steam_catch_up.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="steam_catch_up",
            coalesce=True,
            max_instances=1,
        )
        # A finite backlog nobody is waiting on: a few games a minute until
        # every stored title has its art, then nothing at all (#covers).
        self._scheduler.add_job(
            self._cover_refresh.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="cover_refresh",
            coalesce=True,
            max_instances=1,
        )
        # The same kind of finite backlog: Xbox games whose platforms are
        # unknown, until found or given up on (#114).
        self._scheduler.add_job(
            self._title_platforms.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="title_platforms",
            coalesce=True,
            max_instances=1,
        )
        # PSN trophies stored before #46 without their group (#115).
        self._scheduler.add_job(
            self._psn_trophy_groups.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="psn_trophy_groups",
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.add_job(
            self._daily_history,
            CronTrigger(hour=4, minute=0),
            id="title_history",
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.add_job(
            self._reminders.run,
            IntervalTrigger(hours=6),
            id="reminders",
            coalesce=True,
            max_instances=1,
        )
        # Every minute, because the hour is a runtime setting: a cron trigger
        # would have to be rebuilt whenever the admin changes it (SPEC 5.7).
        self._scheduler.add_job(
            self._daily.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="daily_summary",
            coalesce=True,
            max_instances=1,
        )
        # Same cadence as everything else here — a message due at minute 5
        # sits at most one tick past its TTL, not worth a tighter schedule.
        # A few titles a minute, forever — see the module docstring for why
        # this lives inside the bot process rather than in a cron'd script.
        self._scheduler.add_job(
            self._description_backfill.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="description_backfill",
            coalesce=True,
            max_instances=1,
        )
        # A finite backlog rather than a gap that reopens, so gentler still —
        # see its own module docstring.
        self._scheduler.add_job(
            self._rarity_backfill.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="rarity_backfill",
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.add_job(
            self._message_cleanup.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="message_cleanup",
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.add_job(
            self._online_refresh.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="online_refresh",
            coalesce=True,
            max_instances=1,
        )
        # On the standard 60s tick, not a dedicated 30-minute trigger
        # (Follow-up 2026-09-06) — the real check only fires every
        # KEY_CHECK_INTERVAL_KEY minutes (admin-configurable), gated inside
        # ServiceHealth.tick() itself, same "cheap to poll, gate the real
        # work" shape as online_refresh below.
        self._scheduler.add_job(
            self._service_health.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="service_health",
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.add_job(
            self._admin_refresh.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="admin_refresh",
            coalesce=True,
            max_instances=1,
        )
        # Trophy sync itself still has no presence hook (SPEC 9, M-PSN-2) —
        # this tick scans every linked PSN account directly, debounced
        # internally the same way Xbox/Steam's own achievement polls are.
        # psn_presence below is a separate, unrelated poller (issue #1):
        # presence for /online only, never triggers a trophy poll.
        self._scheduler.add_job(
            self._psn_fetcher.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="psn_fetcher",
            coalesce=True,
            max_instances=1,
        )
        # Two games a minute against a storefront that owes us nothing
        # (poller/steam_localization.py) — the slowest job here, and the only
        # one that reaches a game nobody plays any more.
        self._scheduler.add_job(
            self._steam_localization.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="steam_localization",
            coalesce=True,
            max_instances=1,
        )
        # Profile photos change a few times a year, so this is the slowest
        # job here on purpose (poller/avatars.py): a handful of people per
        # tick, each looked at once a week.
        self._scheduler.add_job(
            self._avatar_refresh.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="avatar_refresh",
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.add_job(
            self._psn_presence.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="psn_presence",
            coalesce=True,
            max_instances=1,
        )
        # Same cadence as the daily summary — "is a window due yet" is a
        # runtime setting too (per-chat flood_window_minutes), same reasoning
        # as daily_summary's own comment above.
        self._scheduler.add_job(
            self._flood_flush.tick,
            IntervalTrigger(seconds=TICK_SECONDS),
            id="flood_flush",
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.start()
        log.info("poller started, tick every %ss", TICK_SECONDS)

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    async def _daily_history(self) -> None:
        """Once a day for everyone, on top of the per-session refresh (SPEC 5.4)."""
        for target in await self._repo.pollable_users():
            try:
                await self._fetcher.refresh_title_history(target.tg_id, target.xuid)
            except Exception:
                log.info("daily title history for tg_id=%s skipped", target.tg_id)
