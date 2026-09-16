"""Profile pictures — each person's Telegram one, and each platform
account's own (2026-09-13 and #55, owner requests: the mini-app shows
people, and a list of names with no faces is not what anyone means by a
profile list).

**Both halves are downloaded, not linked.** Telegram's `file_id` is only
usable together with the bot token, and a platform's URL is a promise
somebody else can break — a face that only exists on their CDN disappears
when they reorganize it. So the bytes land in `data/avatars/` and the row
keeps the path (`services/avatars.py`).

**Why a poller and not the message middleware.** The middleware runs on
every message and refreshes username/first_name/last_name from what the
update already carries, for free. A photo is not in the update: it takes a
`getUserProfilePhotos` of its own, and paying one per message to learn
something that changes a few times a year is the wrong trade. A slow sweep
instead: a few subjects per tick, each looked at once every
`REFRESH_AFTER_DAYS`, oldest check first.

The platform half costs even less: all three platforms hand their picture
over inside a response the bot already makes for something else — Xbox's
profile call (read for gamerscore), Steam's `GetPlayerSummaries`, PSN's
profile behind `get_presence`. What this job adds is the *download*, and
only when the URL or the bytes actually changed.

A subject with no picture we can see — never set one, a privacy setting, a
platform that answered nothing — still gets its `checked_at` stamped, or it
would be asked about again on every tick forever.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from bot.constants import AccountPlatform
from bot.db.repo import Repo
from bot.services import avatars
from bot.services.psn.auth import PsnAuth, PsnNotConfiguredError
from bot.services.psn.client import PsnApiError, profile_avatar_url
from bot.services.steam.auth import SteamAuth
from bot.services.steam.client import SteamApiError
from bot.services.steam.client import avatar_url as steam_avatar_url
from bot.util import utcnow

log = logging.getLogger(__name__)

# A profile photo changes a few times a year at most, so this is about
# noticing eventually, not promptly.
REFRESH_AFTER_DAYS = 7

# One request each; the pace is chosen so a fresh install with a hundred
# people finishes in half an hour without ever being the reason another job
# waits.
USERS_PER_TICK = 5
ACCOUNTS_PER_TICK = 3


class AvatarRefresh:
    def __init__(
        self,
        bot: Bot,
        repo: Repo,
        *,
        steam_auth: SteamAuth | None = None,
        psn_auth: PsnAuth | None = None,
        users_per_tick: int = USERS_PER_TICK,
        accounts_per_tick: int = ACCOUNTS_PER_TICK,
    ) -> None:
        self._bot = bot
        self._repo = repo
        self._steam_auth = steam_auth
        self._psn_auth = psn_auth
        self._users_per_tick = users_per_tick
        self._accounts_per_tick = accounts_per_tick

    async def tick(self) -> None:
        cutoff = (utcnow() - timedelta(days=REFRESH_AFTER_DAYS)).isoformat(timespec="seconds")
        for tg_id in await self._repo.users_needing_avatar(cutoff, self._users_per_tick):
            await self.refresh_now(tg_id)
        for platform, external_id in await self._repo.accounts_needing_avatar(
            cutoff, self._accounts_per_tick
        ):
            await self._refresh_account(platform, external_id)

    async def refresh_now(self, tg_id: int) -> None:
        """One person's Telegram photo, out of turn — for whatever wants a
        face immediately (a fresh registration, the mini-app asking)."""
        try:
            photos = await self._bot.get_user_profile_photos(tg_id, limit=1)
        except TelegramBadRequest:
            # Telegram says there is no such user. Found live (#66): a chat
            # id had ended up in `users`, and since a failure left
            # `photo_checked_at` unstamped, that row stayed permanently
            # first in line — one of the five slots per tick, and a
            # traceback a minute, forever. A "no such user" is an answer,
            # so it is stamped like any other.
            log.info("telegram has no user %s — stamping the check anyway", tg_id)
            await self._repo.set_user_photo(tg_id, None, None)
            return
        except Exception:
            # Anything that might pass later (a network blip, a 429) leaves
            # the check unstamped on purpose: this person is simply first in
            # line again next time. One person must never end a tick — the
            # same rule every other poller here follows.
            log.info("could not read the profile photo of tg_id=%s", tg_id, exc_info=True)
            return

        sizes = photos.photos[0] if photos.photos else []
        # Telegram returns every size of the one photo, smallest first; the
        # last is the largest, which is what a face on a screen of any size
        # should be cropped from rather than upscaled to.
        largest = sizes[-1] if sizes else None
        if largest is None:
            await self._repo.set_user_photo(tg_id, None, None)
            return

        known_unique_id, known_path = await self._repo.user_photo(tg_id)
        if known_unique_id == largest.file_unique_id and known_path:
            # Same photo, already on disk: stamp the check and stop. This is
            # the common case by far, and it costs no download.
            await self._repo.set_user_photo(tg_id, largest.file_id, largest.file_unique_id)
            return

        saved = await self._download_from_telegram(largest.file_id, avatars.telegram_name(tg_id))
        await self._repo.set_user_photo(
            tg_id, largest.file_id, largest.file_unique_id, saved[0] if saved else None
        )

    async def _download_from_telegram(self, file_id: str, name: str) -> tuple[str, str] | None:
        try:
            payload = await self._bot.download(file_id)
        except Exception:
            log.info("could not download the telegram photo %s", name, exc_info=True)
            return None
        data = payload.read() if payload is not None else b""
        return avatars.write(data, name) if data else None

    async def _refresh_account(self, platform: str, external_id: str) -> None:
        """One platform account's own picture. A platform that cannot answer
        right now is stamped anyway and comes back around in a week —
        retrying a dead credential every minute helps nobody."""
        url = await self._account_avatar_url(platform, external_id)
        if url is None:
            await self._repo.set_account_avatar(platform, external_id, None)
            return

        known_url, known_hash = await self._repo.account_avatar(platform, external_id)
        if url == known_url and known_hash:
            await self._repo.set_account_avatar(platform, external_id, url)
            return

        saved = await avatars.download(url, avatars.account_name(platform, external_id))
        await self._repo.set_account_avatar(
            platform, external_id, url, saved[0] if saved else None, saved[1] if saved else None
        )

    async def _account_avatar_url(self, platform: str, external_id: str) -> str | None:
        """Where each platform keeps a face. Xbox is missing on purpose: its
        picture rides in the profile call the *fetcher* already makes with
        that person's own token, and this job has no token of its own — so
        Xbox writes the URL from there (poller/fetcher.py) and this job only
        ever downloads it."""
        try:
            if platform == AccountPlatform.STEAM and self._steam_auth is not None:
                key = await self._steam_auth.get_key()
                return await steam_avatar_url(key, external_id) if key else None
            if platform == AccountPlatform.PSN and self._psn_auth is not None:
                return await profile_avatar_url(await self._psn_auth.get_client(), external_id)
        except (SteamApiError, PsnApiError, PsnNotConfiguredError) as exc:
            log.info("no avatar url for %s %s: %r", platform, external_id, exc)
            return None
        except Exception:
            log.info("unexpected failure reading %s avatar url", platform, exc_info=True)
            return None
        # Xbox, or a platform whose credential is not configured at all: the
        # stored URL (if any) is still worth downloading from.
        known_url, _hash = await self._repo.account_avatar(platform, external_id)
        return known_url
