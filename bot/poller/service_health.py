"""Periodic liveness check for the two shared service credentials — Steam's
API key and PSN's NPSSO (SPEC 9, M-PSN-1's "мониторинг живости" paragraph,
applied to Steam too).

Neither belongs to one person the way an Xbox token does: a dead Xbox token
only ever silences the one person who owns it, and reminders.py already
covers that case. A dead shared key silences *everyone* on that platform at
once, with nothing forcing it to surface on its own (no one is trying to
/connect_steam or /connect_psn every day) — hence a proactive tick instead
of waiting for someone's own action to hit it.

PSN's own liveness (and the transition-based notify) lives in
services/psn/auth.py's PsnAuth.check_health — this module just calls it.
Steam's key doesn't have an equivalent stateful auth wrapper (it is a
permanent, .env-configured secret with nothing to rotate), so its check
lives here directly instead.
"""

from __future__ import annotations

import logging

from bot.config import Settings
from bot.db.repo import Repo
from bot.services.notify import AdminNotifier
from bot.services.psn.auth import PsnAuth
from bot.services.steam.client import check_alive as steam_check_alive
from bot.util import utcnow

log = logging.getLogger(__name__)

STEAM_STATUS_KEY = "steam_key_status"
STEAM_CHECKED_AT_KEY = "steam_key_checked_at"

STATUS_ACTIVE = "active"
STATUS_INVALID = "invalid"


class ServiceHealth:
    def __init__(
        self, settings: Settings, repo: Repo, psn_auth: PsnAuth, notifier: AdminNotifier
    ) -> None:
        self._settings = settings
        self._repo = repo
        self._psn_auth = psn_auth
        self._notifier = notifier

    async def tick(self) -> None:
        await self._check_steam()
        await self._psn_auth.check_health()  # notifies via its own on_dead, wired in main.py

    async def _check_steam(self) -> None:
        if self._settings.steam_api_key is None:
            return  # never configured — nothing to watch
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
