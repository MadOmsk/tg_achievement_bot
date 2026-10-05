"""What one failed liveness check is allowed to mean (#62).

The three admin-managed shared credentials — the PSN NPSSO, the Steam key,
the Anthropic key — each have an auth wrapper of the same shape (#17), and
each used to turn a single failed `check_alive` straight into
`status = invalid` plus an admin notification. That is wrong twice over.

**A failed check is not news.** These services fail one request at a time
for their own reasons: Sony answered a 401 on a routine check at 02:42 on
2026-09-15 (and psnawp then fell over parsing the error body), and the
minute after that everything was fine — but the admin had already been told
the token was dead. Production saw `Expired token` twice and a 503 in the
same two days, unnoticed only because the 30-minute check never landed on
them. So a failure now has to be *confirmed*: `FAILURES_BEFORE_DEAD`
consecutive ones, re-checked on the very next scheduler tick rather than
after another full interval (that is what leaving `checked_at` alone does —
`poller/service_health.py` gates on it). A genuinely dead credential still
surfaces within a few minutes; a hiccup never surfaces at all.

**Recovery is news.** There was an `on_dead` and nothing the other way, so
a false alarm read as permanent: the admin was told the key had died and
had no way to learn it came back except opening /admin. An invalid->active
transition now notifies too.

The counter lives in memory on purpose. It is about one run of bad answers,
and a restart is a fine moment to start counting again — the first check
after one is as good a first opinion as any.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from bot.constants import TokenStatus
from bot.db.repo import Repo
from bot.util import utcnow

log = logging.getLogger(__name__)

# Three strikes at one tick a minute: a dead credential is reported within
# about two minutes, and no single bad answer from a service ever is.
FAILURES_BEFORE_DEAD = 3

Hook = Callable[[], Awaitable[None]] | None


class CredentialHealth:
    """One credential's status bookkeeping, shared by PsnAuth / SteamAuth /
    AnthropicAuth so the rule is written once."""

    def __init__(self, repo: Repo, status_key: str, checked_at_key: str, *, label: str) -> None:
        self._repo = repo
        self._status_key = status_key
        self._checked_at_key = checked_at_key
        self._label = label
        self._failures = 0

    async def record(self, alive: bool, *, on_dead: Hook = None, on_alive: Hook = None) -> bool:
        """Store the outcome of one liveness check and fire the transition
        hooks. Returns what the check said, unchanged — the caller's own
        `check_health` answers "did this credential just work", which is
        true of one good check even while an earlier failure is still
        unconfirmed."""
        if alive:
            self._failures = 0
        else:
            self._failures += 1
            if self._failures < FAILURES_BEFORE_DEAD:
                # Neither the status nor `checked_at` moves: an unconfirmed
                # failure must not show up on the /admin card, and leaving
                # `checked_at` where it was is exactly what makes
                # poller/service_health.py re-check on the next tick instead
                # of waiting out the whole interval again.
                log.info(
                    "%s liveness check failed (%s/%s) — re-checking next tick",
                    self._label,
                    self._failures,
                    FAILURES_BEFORE_DEAD,
                )
                return False
            log.warning("%s liveness check failed %s times in a row", self._label, self._failures)

        was_active = (
            await self._repo.get_app_setting(self._status_key, TokenStatus.ACTIVE)
        ) == TokenStatus.ACTIVE
        await self._repo.set_app_setting(
            self._status_key, TokenStatus.ACTIVE if alive else TokenStatus.INVALID
        )
        await self._repo.set_app_setting(
            self._checked_at_key, utcnow().isoformat(timespec="seconds")
        )
        if was_active and not alive and on_dead is not None:
            await on_dead()
        if not was_active and alive and on_alive is not None:
            await on_alive()
        return alive
