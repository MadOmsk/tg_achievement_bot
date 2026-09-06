"""Fetching PSN trophies and backfill.

Unlike Xbox and Steam, PSN trophy sync has no reliable presence signal to key off.
The tick scans every linked account directly, debounced with the shared achievement
poll interval.
"""

from __future__ import annotations

import logging

from bot.config import Settings
from bot.db.repo import Repo
from bot.poller.cadence import debounce_passed
from bot.poller.publisher import Publisher
from bot.poller.rows import to_achievement_row
from bot.services.psn.achievements import fetch_unlocked
from bot.services.psn.auth import STATUS_NOT_CONFIGURED, PsnAuth, PsnNotConfiguredError
from bot.services.psn.client import PsnApiError

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
            if not debounce_passed(
                target.last_polled_at, self._settings.achievement_poll_interval
            ):
                continue
            try:
                await self.poll_account(
                    target.tg_id, target.account_id, target.online_id or target.account_id
                )
            except Exception:
                # Isolation per account: poll_account already catches PsnApiError,
                # this is only for a genuine bug.
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
        # A single PSN poll can cover several games. The publisher already groups
        # by each row's own title name, same as an Xbox/Steam catch-up burst.
        await self._publisher.publish(tg_id, account_id, online_id, new_rows, None)
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
        return len(rows)
