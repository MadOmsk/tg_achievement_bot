"""The developers' Steam posts put into Russian (owner, 2026-10-30).

A post is translated the moment the bot reads it: `SteamExtras.refresh_patches`
hands the app over once its posts are saved, which covers a new post and a
changed one (saving a changed post drops its old Russian) — awaited when a new
post is to be told about (`translate_app`), so its notice carries the Russian
title; in the background otherwise (`later`). The posts
kept before are the backlog `poller/translations.py` works through.
The links, pictures and the game's own names stay as they are; a long post
is translated in parts (`translate.client.NEWS_PART_CHARS`). No key, or a
failed call: the post stays English and rests an hour before another try.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from bot.services.steam_news import TEXT_CHARS
from bot.services.translate.client import translate_news

if TYPE_CHECKING:
    from bot.db.repo import Repo
    from bot.services.translate.auth import AnthropicAuth

log = logging.getLogger(__name__)

# Only a runaway post stays English: as much as a post keeps
# (`steam_news.TEXT_CHARS`), in parts of `NEWS_PART_CHARS`.
MAX_CHARS = TEXT_CHARS
RETRY_SECONDS = 3600
# One app's read brings its last thirty posts at most.
PER_APP = 30


class NewsTranslator:
    def __init__(self, repo: Repo, anthropic_auth: AnthropicAuth | None) -> None:
        self._repo = repo
        self._auth = anthropic_auth
        self._failed: dict[tuple[int, str], float] = {}
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()

    async def translate_app(self, appid: int) -> int:
        """The app's posts with no Russian, now."""
        return await self.translate(appid=appid, limit=PER_APP)

    def later(self, appid: int) -> None:
        """Translate the app's posts that have no Russian, in the background."""
        if self._auth is None:
            return
        task = asyncio.create_task(self.translate(appid=appid, limit=PER_APP))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def translate(self, *, limit: int, appid: int | None = None) -> int:
        """Up to `limit` posts with no Russian, the newest first (of one app,
        or of all); how many the model was asked about."""
        if self._auth is None:
            return 0
        # One at a time: the backlog and a fresh read never ask twice.
        async with self._lock:
            try:
                api_key = await self._auth.get_key()
                if not api_key:
                    return 0
                now = time.monotonic()
                posts = await self._repo.patches_to_translate(
                    max_chars=MAX_CHARS, limit=limit + len(self._failed), appid=appid
                )
                posts = [p for p in posts if self._failed.get((p[0], p[1]), 0) <= now][:limit]
                for post_appid, gid, title, text in posts:
                    done = await translate_news(api_key, title, text)
                    if done is None:
                        self._failed[(post_appid, gid)] = time.monotonic() + RETRY_SECONDS
                        continue
                    self._failed.pop((post_appid, gid), None)
                    await self._repo.set_patch_translation(
                        post_appid, gid, of=(title, text), title_ru=done[0], text_ru=done[1]
                    )
                return len(posts)
            except Exception as exc:  # a translation never fails anything else
                log.warning("news posts not translated: %r", exc)
                return 0
