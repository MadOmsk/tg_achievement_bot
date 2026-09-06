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

PSN's own liveness (and the transition-based notify) lives in
services/psn/auth.py's PsnAuth.check_health — this module only decides
*when* to call it. Steam's key doesn't have an equivalent stateful auth
wrapper (it is a permanent, .env-configured secret with nothing to rotate),
so its check lives here directly instead.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from bot.config import Settings
from bot.db.repo import Repo
from bot.services.notify import AdminNotifier
from bot.services.psn.auth import PsnAuth
from bot.services.steam.client import check_alive as steam_check_alive
from bot.util import parse_iso, utcnow

log = logging.getLogger(__name__)

STEAM_STATUS_KEY = "steam_key_status"
STEAM_CHECKED_AT_KEY = "steam_key_checked_at"

STATUS_ACTIVE = "active"
STATUS_INVALID = "invalid"

# Shared with the /admin panel's own auto-refresh cadence (handlers/admin.py's
# NUMERIC_SETTINGS, poller/admin_refresh.py) — deliberately one knob, not two
# coincidentally-equal settings (see admin.py's own comment on the entry).
KEY_CHECK_INTERVAL_KEY = "service_health_interval_min"
DEFAULT_KEY_CHECK_INTERVAL_MIN = 30


class ServiceHealth:
    def __init__(
        self, settings: Settings, repo: Repo, psn_auth: PsnAuth, notifier: AdminNotifier
    ) -> None:
        self._settings = settings
        self._repo = repo
        self._psn_auth = psn_auth
        self._notifier = notifier

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
        if self._settings.steam_api_key is None:
            return  # never configured — nothing to watch
        checked_at = await self._repo.get_app_setting(STEAM_CHECKED_AT_KEY)
        if not await self._due(checked_at, interval):
            return
        previous = await self._repo.get_app_setting(STEAM_STATUS_KEY, STATUS_ACTIVE)
        alive = await steam_check_alive(self._settings.steam_api_key.get_secret_value())
        await self._repo.set_app_setting(
            STEAM_STATUS_KEY, STATUS_ACTIVE if alive else STATUS_INVALID
        )
        await self._repo.set_app_setting(
            STEAM_CHECKED_AT_KEY, utcnow().isoformat(timespec="seconds")
        )
        if previous == STATUS_ACTIVE and not alive:
            await self._notifier.service_key_dead("steam")

    async def _check_psn(self, interval: int) -> None:
        checked_at = await self._psn_auth.checked_at()
        if not await self._due(checked_at, interval):
            return
        await self._psn_auth.check_health()  # notifies via its own on_dead, wired in main.py
