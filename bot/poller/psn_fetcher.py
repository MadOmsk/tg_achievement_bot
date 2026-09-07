"""Fetching PSN trophies and backfill (SPEC 9, M-PSN-2) — the PSN
counterpart of poller/steam_fetcher.py. No presence poller alongside it,
unlike Xbox/Steam: PSN trophy sync has no signal to key off (M-PSN-2's own
"ключевое отличие" paragraph) — `tick()` just scans every linked account
directly, debounced the same way Xbox/Steam debounce their own achievement
polls (`achievement_poll_interval`, poller/cadence.py), reused rather than
a PSN-specific setting: this is a "don't ask too often" politeness, not a
budget constraint, the same reasoning that already applies on both other
platforms (SPEC 5.2).
"""

from __future__ import annotations

import logging

from psnawp_api import PSNAWP

from bot.config import Settings
from bot.db.repo import Repo
from bot.poller.cadence import debounce_passed
from bot.poller.publisher import Publisher
from bot.poller.rows import to_achievement_row
from bot.services.psn.achievements import fetch_unlocked
from bot.services.psn.auth import STATUS_NOT_CONFIGURED, PsnAuth, PsnNotConfiguredError
from bot.services.psn.client import PsnApiError, account_trophy_level

log = logging.getLogger(__name__)


class PsnFetcher:
    def __init__(
        self, settings: Settings, repo: Repo, psn_auth: PsnAuth, publisher: Publisher
    ) -> None:
        self._settings = settings
        self._repo = repo
        self._psn_auth = psn_auth
        self._publisher = publisher

    async def tick(self) -> None:
        if await self._psn_auth.status() == STATUS_NOT_CONFIGURED:
            return  # PSN not set up on this instance — same early-out as service_health
        for target in await self._repo.psn_pollable_users():
            if not debounce_passed(target.last_polled_at, self._settings.achievement_poll_interval):
                continue
            try:
                await self.poll_account(
                    target.tg_id, target.account_id, target.online_id or target.account_id
                )
            except Exception:
                # Isolation per account (CLAUDE.md's per-account failure rule) —
                # poll_account already
                # catches PsnApiError itself, this is only for a genuine bug.
                log.exception("unexpected failure polling psn account_id=%s", target.account_id)
            await self._repo.touch_psn_poll_state(target.account_id)

    async def poll_account(self, tg_id: int, account_id: str, online_id: str) -> int:
        """One account's worth of newly-earned trophies, published if any."""
        try:
            client = await self._psn_auth.get_client()
            parsed = await fetch_unlocked(self._repo, client, account_id)
        except PsnNotConfiguredError:
            return 0  # PSN got unconfigured mid-run — next tick will also skip cleanly
        except PsnApiError as exc:
            log.info("psn poll of account_id=%s skipped: %s", account_id, exc)
            return 0

        rows = [to_achievement_row(item) for item in parsed]
        new_rows = await self._repo.insert_new_achievements_psn(
            tg_id, account_id, rows, is_backfill=False
        )
        if not new_rows:
            return 0

        log.info("tg_id=%s unlocked %s new psn trophies", tg_id, len(new_rows))
        # No game_name here (unlike Xbox/Steam's own poll_title): a single
        # poll can cover several different games at once (M-PSN-2's own
        # multi-achievement paragraph) — format_digest/_group_by_title
        # (services/achievements.py) already handle that by grouping on
        # each row's own title_name, same as a Xbox/Steam catch-up burst.
        await self._publisher.publish(tg_id, account_id, online_id, new_rows, None)
        # Level only ever changes when a trophy is earned (Follow-up
        # 2026-09-06, /stats' own PSN line) — refreshed here, not on every
        # tick.
        await self._refresh_level(client, tg_id, account_id)
        return len(new_rows)

    async def backfill(self, tg_id: int, account_id: str) -> int:
        """Mark everything already earned as seen, publishing nothing — same
        principle as Xbox/Steam's own backfill (SPEC 5.6, M-Steam-2d).
        Cheaper than Steam's: trophy_titles() without a limit already lists
        every game with progress in one paginated pass, no separate
        "which games has this account played" call needed."""
        try:
            client = await self._psn_auth.get_client()
        except PsnNotConfiguredError:
            return 0
        # No limit (unlike poll_account) — the whole account's history, not
        # just the recent window regular polling uses, or an older game's
        # trophies would never get a seen_achievements/psn_title_progress
        # baseline at all (SPEC 9, M-PSN-2).
        parsed = await fetch_unlocked(self._repo, client, account_id, limit=None)
        rows = [to_achievement_row(item) for item in parsed]
        await self._repo.insert_new_achievements_psn(tg_id, account_id, rows, is_backfill=True)
        log.info("psn backfill for tg_id=%s stored %s trophies", tg_id, len(rows))
        # So /stats has a real level to show from the moment someone links,
        # not just after their first live trophy (Follow-up 2026-09-06).
        await self._refresh_level(client, tg_id, account_id)
        return len(rows)

    async def _refresh_level(self, client: PSNAWP, tg_id: int, account_id: str) -> None:
        """Never blocks its caller on failure — a stale cached level is a
        much smaller problem than losing an achievement, or a whole tick,
        over this one extra call (Follow-up 2026-09-06). Catches broadly,
        not just PsnApiError: found live this same session that trusting a
        third-party library's own type promises is exactly how a real
        trophy silently stopped publishing (trophy_earn_rate, client.py's
        _as_float) — this is deliberately the more paranoid default."""
        try:
            level = await account_trophy_level(client, account_id)
            await self._repo.set_psn_trophy_level(tg_id, level)
        except Exception:
            log.warning("could not refresh psn trophy level for tg_id=%s", tg_id, exc_info=True)
