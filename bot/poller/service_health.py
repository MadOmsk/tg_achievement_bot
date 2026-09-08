"""Periodic liveness check for the two shared service credentials — Steam's
API key and PSN's NPSSO (SPEC 9, M-PSN-1's "мониторинг живости" paragraph,
applied to Steam too).

Neither belongs to one person the way an Xbox token does: a dead Xbox token
only ever silences the one person who owns it, and reminders.py already
covers that case. A dead shared key silences *everyone* on that platform at
once, with nothing forcing it to surface on its own (no one is trying to
/connect_steam or /connect_psn every day) — hence a proactive tick instead
of waiting for someone's own action to hit it.

Scheduled on the same 60s tick as everything else in scheduler.py, not a
dedicated fixed-interval trigger (Follow-up 2026-09-06) — the actual check
only fires every `KEY_CHECK_INTERVAL_KEY` minutes (admin-configurable, same
knob poller/admin_refresh.py reads for the /admin screen's own cadence),
same "cheap to poll every tick, gate the real work" shape as
poller/online_refresh.py.

Each credential's own liveness (and the transition-based admin notify) lives
in its auth wrapper — PsnAuth.check_health / SteamAuth.check_health (#17
gave Steam the same stateful wrapper PSN already had). This module only
decides *when* to call them and gates on `_due`; the wrappers fire their
own `on_dead` callbacks, wired in main.py.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from bot.constants import TokenStatus
from bot.db.repo import Repo
from bot.services.psn.auth import PsnAuth
from bot.services.steam.auth import CHECKED_AT_KEY as STEAM_CHECKED_AT_KEY
from bot.services.steam.auth import STATUS_KEY as STEAM_STATUS_KEY
from bot.services.steam.auth import SteamAuth
from bot.util import parse_iso, utcnow

log = logging.getLogger(__name__)

# Re-exported from services/steam/auth.py (their owner as of #17) — kept
# here too so existing importers (services/admin_view.py, tests) don't move.
__all__ = ["STEAM_CHECKED_AT_KEY", "STEAM_STATUS_KEY"]

# Shared with the /admin panel's own auto-refresh cadence (handlers/admin.py's
# NUMERIC_SETTINGS, poller/admin_refresh.py) — deliberately one knob, not two
# coincidentally-equal settings (see admin.py's own comment on the entry).
KEY_CHECK_INTERVAL_KEY = "service_health_interval_min"
DEFAULT_KEY_CHECK_INTERVAL_MIN = 30

# Compatibility exports for tests and older callers.
STATUS_ACTIVE = TokenStatus.ACTIVE
STATUS_INVALID = TokenStatus.INVALID


class ServiceHealth:
    """Decides *when* to run the two shared-credential liveness checks; the
    checks themselves (and the once-per-transition admin notify) live in
    PsnAuth.check_health / SteamAuth.check_health, wired to their `on_dead`
    callbacks in main.py."""

    def __init__(self, repo: Repo, psn_auth: PsnAuth, steam_auth: SteamAuth) -> None:
        self._repo = repo
        self._psn_auth = psn_auth
        self._steam_auth = steam_auth

    async def tick(self) -> None:
        interval = await self._repo.get_int_setting(
            KEY_CHECK_INTERVAL_KEY, DEFAULT_KEY_CHECK_INTERVAL_MIN
        )
        await self._check_steam(interval)
        await self._check_psn(interval)

    async def _due(self, checked_at: str | None, interval: int) -> bool:
        if checked_at is None or interval <= 0:
            return True  # never checked yet, or a hand-edited 0 — don't get stuck
        return utcnow() - parse_iso(checked_at) >= timedelta(minutes=interval)

    async def _check_steam(self, interval: int) -> None:
        checked_at = await self._steam_auth.checked_at()
        if not await self._due(checked_at, interval):
            return
        await self._steam_auth.check_health()  # notifies via its own on_dead, wired in main.py

    async def _check_psn(self, interval: int) -> None:
        checked_at = await self._psn_auth.checked_at()
        if not await self._due(checked_at, interval):
            return
        await self._psn_auth.check_health()  # notifies via its own on_dead, wired in main.py
