"""Keeping each person's Telegram profile photo on file (2026-09-13, owner
request: the mini-app shows people, and a list of names with no faces is not
what anyone means by a profile list).

What gets stored is Telegram's own `file_id`, never an image and never a URL:
a file_id is only usable together with the bot token, so the token stays on
the server and the column is not a secret on its own. Whoever renders a face
calls getFile with it at that moment.

**Why a poller and not the message middleware.** The middleware runs on every
single message and already refreshes username/first_name/last_name from what
the update itself carries — for free, no API call. A photo is not in the
update: it takes a `getUserProfilePhotos` request of its own, and paying one
per message to learn something that changes a few times a year is the wrong
trade. So it is a slow sweep instead: a few people per tick, each looked at
once every `REFRESH_AFTER_DAYS`, oldest check first.

A person with no photo we can see — never set one, or a privacy setting —
still gets `photo_checked_at` stamped, or they would be asked about again on
every tick forever.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from bot.db.repo import Repo
from bot.util import utcnow

log = logging.getLogger(__name__)

# A profile photo changes a few times a year at most, so this is about
# noticing eventually, not promptly.
REFRESH_AFTER_DAYS = 7

# Telegram's own limit is generous and this is one request each; the pace is
# chosen so a fresh install with a hundred people finishes in half an hour
# without ever being the reason another job waits.
USERS_PER_TICK = 5


class AvatarRefresh:
    def __init__(self, bot: Bot, repo: Repo, *, users_per_tick: int = USERS_PER_TICK) -> None:
        self._bot = bot
        self._repo = repo
        self._users_per_tick = users_per_tick

    async def tick(self) -> None:
        cutoff = (utcnow() - timedelta(days=REFRESH_AFTER_DAYS)).isoformat(timespec="seconds")
        for tg_id in await self._repo.users_needing_avatar(cutoff, self._users_per_tick):
            try:
                photos = await self._bot.get_user_profile_photos(tg_id, limit=1)
            except TelegramBadRequest:
                # Telegram says there is no such user. Found live (#66): a
                # chat id had ended up in `users`, and an unstamped failure
                # left that row permanently first in line — one of the five
                # slots every tick, and a traceback a minute, forever. A
                # "no such user" is an answer, so it is recorded like one.
                log.info("telegram has no user %s — stamping the check anyway", tg_id)
                await self._repo.set_user_photo(tg_id, None, None)
                continue
            except Exception:
                # Anything that might pass later leaves the check unstamped
                # on purpose: this person is simply first in line again next
                # time. One person must never end a tick — the same rule
                # every other poller here follows.
                log.info("could not read the profile photo of tg_id=%s", tg_id, exc_info=True)
                continue

            sizes = photos.photos[0] if photos.photos else []
            # Telegram returns every size of the one photo, smallest first;
            # the last is the largest, which is what a face on a screen of any
            # size should be cropped from rather than upscaled to.
            largest = sizes[-1] if sizes else None
            await self._repo.set_user_photo(
                tg_id,
                largest.file_id if largest else None,
                largest.file_unique_id if largest else None,
            )

    async def refresh_now(self, tg_id: int) -> None:
        """One person, out of turn — for whatever eventually wants a face
        immediately (a fresh registration, the mini-app asking). Same body as
        the sweep above, minus the "who is due" question."""
        try:
            photos = await self._bot.get_user_profile_photos(tg_id, limit=1)
        except Exception:
            log.info("could not read the profile photo of tg_id=%s", tg_id, exc_info=True)
            return
        sizes = photos.photos[0] if photos.photos else []
        largest = sizes[-1] if sizes else None
        await self._repo.set_user_photo(
            tg_id,
            largest.file_id if largest else None,
            largest.file_unique_id if largest else None,
        )
