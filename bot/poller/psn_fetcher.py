"""Fetching PSN trophies and backfill (SPEC 9, M-PSN-2) — the PSN
counterpart of poller/steam_fetcher.py. No presence poller alongside it,
unlike Xbox/Steam: PSN trophy sync has no signal to key off (M-PSN-2's own
"ключевое отличие" paragraph) — `tick()` just scans every linked account
directly, debounced the same way Xbox/Steam debounce their own achievement
polls (`achievement_poll_interval`, poller/cadence.py), reused rather than
a PSN-specific setting: this is a "don't ask too often" politeness, not a
budget constraint, the same reasoning that already applies on both other
platforms (SPEC 5.2).

The scan/persist itself (and the ordering that makes an interrupted scan
safe) lives in services/psn/achievements.py::sync_account — this module only
decides *who* to scan and *when*, and publishes whatever came back new.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from psnawp_api import PSNAWP

from bot.config import Settings
from bot.constants import Platform
from bot.db.repo import Repo
from bot.i18n import gettext
from bot.poller.cadence import debounce_passed
from bot.poller.publisher import Publisher
from bot.services.psn.achievements import sync_account
from bot.services.psn.auth import STATUS_NOT_CONFIGURED, PsnAuth, PsnNotConfiguredError
from bot.services.psn.client import PsnApiError, account_trophy_level, is_trophy_visible

log = logging.getLogger(__name__)

_ = lambda key, **kwargs: gettext("psnfetcher", key, **kwargs)  # noqa: E731


@dataclass(slots=True)
class PsnBackfillResult:
    """What backfill() did — `stored` for the "read N already-earned
    trophies" notice, `private_title_ids` for the follow-on "and N games
    are private" line (#28)."""

    stored: int = 0
    private_title_ids: list[str] = field(default_factory=list)


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
            if not target.backfill_done:
                # #21: this account's first-ever backfill is still running
                # (or crashed and never finished). Polling it here would
                # race that backfill and publish its whole trophy history as
                # if just earned. A stuck one is recovered via the admin
                # panel's PSN resync, not by this tick.
                continue
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
            outcome = await sync_account(self._repo, client, tg_id, account_id, is_backfill=False)
        except PsnNotConfiguredError:
            return 0  # PSN got unconfigured mid-run — next tick will also skip cleanly
        except PsnApiError as exc:
            log.info("psn poll of account_id=%s skipped: %s", account_id, exc)
            return 0

        if outcome.unmapped_errors:
            log.warning(
                "psn poll of account_id=%s: %s title(s) hit an unmapped error, skipped this pass",
                account_id,
                outcome.unmapped_errors,
            )
        if not outcome.new_rows:
            return 0

        log.info("tg_id=%s unlocked %s new psn trophies", tg_id, len(outcome.new_rows))
        # No game_name here (unlike Xbox/Steam's own poll_title): a single
        # poll can cover several different games at once (M-PSN-2's own
        # multi-achievement paragraph) — format_digest/_group_by_title
        # (services/achievements.py) already handle that by grouping on
        # each row's own title_name, same as a Xbox/Steam catch-up burst.
        await self._publisher.publish(tg_id, account_id, online_id, outcome.new_rows, None)
        # Level only ever changes when a trophy is earned (Follow-up
        # 2026-09-06, /stats' own PSN line) — refreshed here, not on every
        # tick.
        await self._refresh_level(client, tg_id, account_id)
        return len(outcome.new_rows)

    async def backfill(self, tg_id: int, account_id: str) -> PsnBackfillResult:
        """Mark everything already earned as seen, publishing nothing — same
        principle as Xbox/Steam's own backfill (SPEC 5.6, M-Steam-2d).
        Cheaper than Steam's: trophy_titles() without a limit already lists
        every game with progress in one paginated pass, no separate
        "which games has this account played" call needed.

        Flips psn_poll_state.backfill_done on success so tick() may start
        polling this account (#21). If sync_account raises, the flag is left
        off — the account stays out of the regular poller until an admin
        resync re-runs this.
        """
        try:
            client = await self._psn_auth.get_client()
        except PsnNotConfiguredError:
            return PsnBackfillResult()

        # Re-check trophy visibility (#5) — connect_psn already required
        # this to pass once, before linking; re-verifying here (and
        # recording it, not just gating on it) is what makes /panel's login
        # row reflect the *last actual check*, matching Steam's own
        # backfill-time check right above this file's Steam counterpart.
        if not await is_trophy_visible(client, account_id):
            await self._repo.set_achievements_visible(tg_id, Platform.PSN, False)
            log.info("psn backfill for tg_id=%s skipped: trophies not visible", tg_id)
            return PsnBackfillResult()
        await self._repo.set_achievements_visible(tg_id, Platform.PSN, True)

        # No limit (unlike poll_account) — the whole account's history, not
        # just the recent window regular polling uses, or an older game's
        # trophies would never get a seen_achievements/psn_title_progress
        # baseline at all (SPEC 9, M-PSN-2).
        outcome = await sync_account(
            self._repo, client, tg_id, account_id, is_backfill=True, limit=None
        )
        await self._repo.mark_psn_backfill_done(account_id)
        log.info(
            "psn backfill for tg_id=%s stored %s trophies (%s private, %s unmapped error(s))",
            tg_id,
            len(outcome.new_rows),
            len(outcome.private_title_ids),
            outcome.unmapped_errors,
        )
        # So /stats has a real level to show from the moment someone links,
        # not just after their first live trophy (Follow-up 2026-09-06).
        await self._refresh_level(client, tg_id, account_id)
        return PsnBackfillResult(
            stored=len(outcome.new_rows),
            private_title_ids=list(outcome.private_title_ids),
        )

    async def refresh_user(self, tg_id: int, account_id: str, online_id: str) -> str:
        """An out-of-turn look at one PSN account for the admin card (#27) —
        the PSN counterpart of Fetcher/SteamFetcher.refresh_user, which PSN
        never had. Doubles as the recovery path for an account stuck in
        "linked but the first backfill never finished" (#24/#26): if
        backfill_done is still off, wipe any partial progress checkpoints
        and re-run backfill from scratch, instead of the only fix being a
        manual DB script on the server.

        Also re-checks trophy visibility (#5, user request: "ресинк
        перепроверяет же статус доступности ачивок?") — it did not, before
        this, for an account already past its first backfill (the
        `poll_account` branch below never touched the flag `backfill`
        above now sets). A cheap probe here too, same "don't overwrite the
        last known-good status on a transient failure" shape as Steam's own.
        """
        try:
            client = await self._psn_auth.get_client()
        except PsnNotConfiguredError:
            pass
        else:
            try:
                visible = await is_trophy_visible(client, account_id)
            except PsnApiError:
                pass
            else:
                await self._repo.set_achievements_visible(tg_id, Platform.PSN, visible)

        if not await self._repo.psn_backfill_done(account_id):
            await self._repo.clear_psn_title_progress(account_id)
            try:
                result = await self.backfill(tg_id, account_id)
            except Exception:
                log.exception("admin psn resync (backfill) of tg_id=%s failed", tg_id)
                return _("psnfetcher-resync-failed")
            return _("psnfetcher-resynced-backfill", stored=result.stored)

        try:
            published = await self.poll_account(tg_id, account_id, online_id)
        except Exception:
            log.exception("admin psn resync (poll) of tg_id=%s failed", tg_id)
            return _("psnfetcher-resync-failed")
        return _("psnfetcher-resynced-poll", published=published)

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
