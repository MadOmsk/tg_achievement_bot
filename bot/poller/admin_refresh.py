"""Keeps /admin's home screen fresh on its own, same idea as
poller/online_refresh.py for /online (Follow-up 2026-09-06).

A bare /admin used to be a one-off snapshot — this tick re-renders it and
edits the same message in place every `KEY_CHECK_INTERVAL_KEY` minutes
(services/service_health.py's own setting, deliberately shared rather than
a second knob: the panel's numbers are only ever as fresh as the last key
check anyway). One row per admin (db/repo.py's admin_panel_refresh, PRIMARY
KEY admin_id) — a fresh /admin (handlers/admin.py's _replace_admin_home)
deletes the old message outright rather than leaving it to go stale, unlike
/online's version: an admin only ever needs the one live copy open.

Runs every tick (60s, same as everything else in scheduler.py) rather than
on its own dedicated trigger — same reasoning as online_refresh.py's own
docstring: checking this often costs nothing and needs no separate sweep.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from aiogram import Bot

from bot.db.repo import AdminPanelRefreshRow, Repo
from bot.poller.fetcher import Fetcher
from bot.poller.service_health import DEFAULT_KEY_CHECK_INTERVAL_MIN, KEY_CHECK_INTERVAL_KEY
from bot.poller.steam_fetcher import SteamFetcher
from bot.services.admin_view import render_admin_home
from bot.services.psn.auth import PsnAuth
from bot.util import parse_iso, utcnow

log = logging.getLogger(__name__)


class AdminPanelRefresh:
    def __init__(
        self,
        bot: Bot,
        repo: Repo,
        fetcher: Fetcher,
        steam_fetcher: SteamFetcher,
        psn_auth: PsnAuth,
    ) -> None:
        self._bot = bot
        self._repo = repo
        self._fetcher = fetcher
        self._steam_fetcher = steam_fetcher
        self._psn_auth = psn_auth

    async def tick(self) -> None:
        interval = await self._repo.get_int_setting(
            KEY_CHECK_INTERVAL_KEY, DEFAULT_KEY_CHECK_INTERVAL_MIN
        )
        if interval <= 0:
            return
        now = utcnow()
        for row in await self._repo.all_admin_panel_refreshes():
            last_updated_at = parse_iso(row.last_updated_at)
            if now - last_updated_at < timedelta(minutes=interval):
                continue
            await self._refresh_one(row)

    async def _refresh_one(self, row: AdminPanelRefreshRow) -> None:
        text, markup = await render_admin_home(
            self._repo, self._fetcher, self._steam_fetcher, self._psn_auth
        )
        try:
            await self._bot.edit_message_text(
                chat_id=row.admin_id,
                message_id=row.message_id,
                text=text,
                reply_markup=markup,
            )
        except Exception:
            # Expected, not exceptional: the admin deleted it by hand, or it
            # aged out of Telegram's own edit window — nothing left worth
            # retrying, same "forget it either way" reasoning as
            # online_refresh.py. The timestamp in the header changes every
            # refresh, so a genuine no-op edit basically never happens.
            log.info("admin panel auto-refresh: edit failed for admin %s, stopping", row.admin_id)
            await self._repo.delete_admin_panel_refresh(row.admin_id)
            return
        await self._repo.touch_admin_panel_refresh(row.admin_id)
