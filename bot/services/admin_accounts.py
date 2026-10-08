"""What the super-admin does to one person's game account — refresh it, or
reset it and read its history again — for both panels (the bot's user card
and the Mini App's). One implementation, so "🔄 Обновить" means the same in
both: it used to pull the delta since the newest unlock in the bot only, and
the Mini App's sync looked at the present moment and nothing else.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bot.config import Settings
from bot.constants import Platform, account_platform_of
from bot.db.repo import PlatformLink, Repo
from bot.i18n import translator
from bot.services.naming import link_nickname
from bot.util import parse_iso

if TYPE_CHECKING:
    from bot.poller.fetcher import Fetcher
    from bot.poller.psn_fetcher import PsnFetcher
    from bot.poller.steam_fetcher import SteamFetcher

log = logging.getLogger(__name__)

PLATFORMS = ("xbox", "steam", "psn")


class AdminAccounts:
    def __init__(
        self,
        repo: Repo,
        settings: Settings,
        *,
        xbox: Fetcher | None,
        steam: SteamFetcher | None,
        psn: PsnFetcher | None,
    ) -> None:
        self._repo = repo
        self._settings = settings
        self._fetchers = {"xbox": xbox, "steam": steam, "psn": psn}

    async def link(
        self, platform: str, person: int, account_id: str | None = None
    ) -> PlatformLink | None:
        """The Steam/PSN link a button is about: the one named by `account_id`
        (a PSN account among several, #10), else the person's only one."""
        platform_value = Platform.STEAM if platform == "steam" else Platform.PSN
        if account_id is None:
            return await self._repo.get_platform_link(person, platform_value)
        links = await self._repo.platform_links_for(person, platform_value)
        return next((link for link in links if link.external_id == account_id), None)

    async def target(
        self, platform: str, person: int, *, locale: str, account_id: str | None = None
    ) -> tuple[str, str] | None:
        """(external id, name) of the account, or None when it is not linked
        or this process has no fetcher for its platform."""
        if self._fetchers.get(platform) is None:
            return None
        if platform == "xbox":
            user = await self._repo.get_user(person)
            if user is None or not user.xuid:
                return None
            return user.xuid, user.gamertag or translator("admin", locale)("admin-default-player")
        link = await self.link(platform, person, account_id)
        if link is None:
            return None
        return link.external_id, link_nickname(link)

    async def refresh(
        self, platform: str, person: int, *, locale: str, account_id: str | None = None
    ) -> str | None:
        """ "🔄 Обновить": presence and the game being played right now, then
        everything earned since the newest unlock already stored. The words to
        show, or None when the account is not linked."""
        target = await self.target(platform, person, locale=locale, account_id=account_id)
        if target is None:
            return None
        external_id, name = target
        fetcher = self._fetchers[platform]
        assert fetcher is not None
        summary = await fetcher.refresh_user(person, external_id, name, locale)
        delta = await self._delta(platform, person, external_id, name, locale=locale)
        return f"{summary}\n{delta}" if delta else summary

    async def _delta(
        self, platform: str, person: int, external_id: str, name: str, *, locale: str
    ) -> str:
        """Everything earned since the newest unlock already stored — the "pull
        what is new" half of "🔄 Обновить" (user request, 2026-09-13).

        `refresh_user` on its own is a *right now* look: presence, plus the
        achievements of the game being played at this moment. For somebody who
        is offline that finds nothing at all. PSN needs nothing extra — its own
        `refresh_user` already runs the ordinary trophy scan, a delta by
        construction.

        What it finds is stored in full and *announced* only inside the usual
        catch-up window: a delta reaching back a month is worth storing, never
        worth posting to a chat all at once.
        """
        _ = translator("admin", locale)
        since = await self._repo.account_latest_unlock(account_platform_of(platform), external_id)
        window = self._settings.catchup_publish_window_hours
        xbox = self._fetchers["xbox"]
        steam = self._fetchers["steam"]
        if platform == "xbox" and xbox is not None:
            titles, published = await xbox.catch_up(  # type: ignore[union-attr]
                person,
                external_id,
                name,
                parse_iso(since) if since else None,
                window,
                self._settings.catchup_max_titles,
            )
            return _("admin-sync-delta", titles=titles, published=published)
        if platform == "steam" and steam is not None and since is not None:
            published = await steam.catch_up(person, external_id, name, since, window)  # type: ignore[union-attr]
            return _("admin-sync-delta-steam", published=published)
        return ""

    async def reset(self, platform: str, person: int, account_id: str | None = None) -> bool:
        """ "🗑 Сброс": the account's history wiped and read again. False when
        the account is not linked."""
        fetcher = self._fetchers.get(platform)
        if fetcher is None:
            return False
        if platform == "xbox":
            user = await self._repo.get_user(person)
            if user is None or not user.xuid:
                return False
            await self._repo.reset_xbox_data(person, user.xuid)
            await fetcher.backfill(person, user.xuid)
            return True
        link = await self.link(platform, person, account_id)
        if link is None:
            return False
        if platform == "steam":
            # The account's own id, not the person's: since #52 the history
            # belongs to the account.
            await self._repo.reset_steam_data(link.external_id)
        else:
            await self._repo.reset_psn_data(person, link.external_id)
        await fetcher.backfill(person, link.external_id)
        return True
