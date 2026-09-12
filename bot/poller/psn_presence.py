"""PSN presence polling — issue #1's "/online" piece.

Deliberately its own tiny poller, unrelated to poller/psn_fetcher.py's
trophy-scan cadence (psn_poll_state/psn_pollable_users): trophy sync has
never been driven by presence on PSN (CLAUDE.md's PSN section explains
why — trophies may only sync to Sony's servers when a player opens trophy
data on the console, not at the moment of unlock), and adding presence
tracking doesn't change that design. This poller only ever writes to
psn_presence_state and touches last_online — it never triggers a trophy
poll.

PSN has no Steam-style batch presence endpoint (SPEC 9, M-PSN-1 checklist
item 4's own open question) — one `get_presence()` request per account,
same one-account-per-request shape as Xbox's own presence.py, not Steam's
batched steam_presence.py.

Every target is handled in isolation — one private profile or one
unexpected error must never stop the tick for everyone else, the same
discipline presence.py/steam_presence.py already follow.
"""

from __future__ import annotations

import logging

from bot.config import Settings
from bot.constants import Platform
from bot.db.repo import PsnPresenceTarget, Repo
from bot.poller.cadence import is_due, presence_interval
from bot.services.psn.auth import PsnAuth, PsnNotConfiguredError
from bot.services.psn.client import PsnApiError, PsnPresenceSnapshot, get_presence

log = logging.getLogger(__name__)


class PsnPresencePoller:
    def __init__(self, settings: Settings, repo: Repo, psn_auth: PsnAuth) -> None:
        self._settings = settings
        self._repo = repo
        self._psn_auth = psn_auth

    async def tick(self) -> None:
        try:
            client = await self._psn_auth.get_client()
        except PsnNotConfiguredError:
            return  # PSN not configured on this instance — same silent skip PsnFetcher gets
        except PsnApiError:
            return  # dead token etc. — reminded about elsewhere (service_health), not here

        due = [t for t in await self._repo.psn_presence_pollable_accounts() if self._is_due(t)]
        for target in due:
            try:
                snapshot = await get_presence(client, target.account_id)
            except PsnApiError as exc:
                log.info("psn presence skipped for account_id=%s: %s", target.account_id, exc)
                continue  # private profile, not-found, dead token — expected, isolate and move on
            except Exception:
                log.exception(
                    "unexpected failure polling psn presence account_id=%s", target.account_id
                )
                continue
            try:
                await self._handle(target, snapshot)
            except Exception:
                log.exception(
                    "unexpected failure saving psn presence account_id=%s", target.account_id
                )

    async def _handle(self, target: PsnPresenceTarget, snapshot: PsnPresenceSnapshot) -> None:
        changed = snapshot.state != target.state or snapshot.title_id != target.title_id
        await self._repo.save_psn_presence_state(
            target.account_id,
            snapshot.state,
            snapshot.title_id,
            snapshot.title_name,
            changed=changed,
        )
        if snapshot.state == "Online":
            await self._repo.touch_last_online(target.tg_id)
        await self._refresh_nickname(target, snapshot.online_id)

    async def _refresh_nickname(self, target: PsnPresenceTarget, online_id: str | None) -> None:
        """The current online ID came along with the presence request (#51),
        so keeping it fresh costs nothing. A change here is also the only
        signal Sony gives us that an account was renamed — the endpoint that
        reports a previous online ID is addressed by nickname, and by the
        time we would ask, we would already be asking with the new one. So
        the value being replaced *is* the previous id, kept as this
        platform's own second naming step.
        """
        if not online_id or online_id == target.online_id:
            return
        previous = target.online_id
        await self._repo.update_platform_names(target.tg_id, Platform.PSN, online_id)
        if previous:
            await self._repo.set_platform_secondary_name(target.tg_id, Platform.PSN, previous)
            log.info("psn account %s renamed: %s -> %s", target.account_id, previous, online_id)

    def _is_due(self, target: PsnPresenceTarget) -> bool:
        return is_due(target.updated_at, self._interval(target))

    def _interval(self, target: PsnPresenceTarget) -> int:
        # Same politeness-driven cadence Xbox/Steam presence already use
        # (poller/cadence.py) — PSN's own rate limit is undocumented but
        # nowhere near a constraint either (services/psn/client.py's
        # RATE_WINDOWS is a runaway-bug guard, not a real budget).
        return presence_interval(
            online=target.state == "Online",
            in_game=bool(target.title_id),
            changed_at=target.changed_at,
            interval_in_game=self._settings.presence_interval_in_game,
            interval_online=self._settings.presence_interval_online,
            interval_offline=self._settings.presence_interval_offline,
            interval_idle=self._settings.presence_interval_idle,
        )
