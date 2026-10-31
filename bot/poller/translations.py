"""Russian for the games database the moment something was missed (owner,
2026-10-30): the developers' Steam posts, the guides' tips and the games'
descriptions.

All are translated as they come — a post when the bot reads it
(`NewsTranslator`, from `SteamExtras.refresh_patches`), a game's tips when
they are worked out (`GuideTranslator`), a game's description when the store
collection or the octopus collects it (`GameTranslator`). This walker is for
the rest, as fast as the model answers, for up to `TICK_SECONDS` a tick, the
three side by side: the posts kept before, the newest first; the games'
tips; and the games by id, round and round, translating those whose
description has no Russian — one missed, or whose English changed, is found
on the next pass, and a pass that found nothing rests an hour. Once the
backlog is done a tick finds nothing and asks nobody. Nothing is translated
when a page is opened, so no page waits for it. No Anthropic key: nothing
happens.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.db.repo import Repo
    from bot.services.game_descriptions import GameTranslator
    from bot.services.guide_translations import GuideTranslator
    from bot.services.news_translations import NewsTranslator

# A tick works through the backlog for this long, then leaves the rest to the
# next: the model, not our database, is what takes the time.
TICK_SECONDS = 50
NEWS_PER_STEP = 2
GUIDE_GAMES_PER_STEP = 1
GAMES_READ_PER_STEP = 40
# A whole pass over the games that asked the model nothing rests this long.
IDLE_PASS_REST_SECONDS = 3600
CURSOR_KEY = "game_translation_cursor"


class Translations:
    def __init__(
        self, repo: Repo, news: NewsTranslator, guides: GuideTranslator, games: GameTranslator
    ) -> None:
        self._repo = repo
        self._news = news
        self._guides = guides
        self._games = games
        self._pass_calls = 0
        self._rest_until = 0.0

    async def tick(self) -> None:
        # The three backlogs side by side, each until it is empty or time is up.
        deadline = time.monotonic() + TICK_SECONDS
        await asyncio.gather(
            self._news_backlog(deadline),
            self._guides_backlog(deadline),
            self._descriptions(deadline),
        )

    async def _news_backlog(self, deadline: float) -> None:
        while time.monotonic() < deadline:
            if not await self._news.translate(limit=NEWS_PER_STEP):
                return

    async def _guides_backlog(self, deadline: float) -> None:
        while time.monotonic() < deadline:
            if not await self._guides.translate_some(GUIDE_GAMES_PER_STEP):
                return

    async def _descriptions(self, deadline: float) -> None:
        if time.monotonic() < self._rest_until:
            return
        cursor = await self._repo.get_int_setting(CURSOR_KEY, 0)
        while time.monotonic() < deadline:
            game_ids = await self._repo.game_ids_after(cursor, GAMES_READ_PER_STEP)
            if not game_ids:
                # A pass done: the next starts over, after a rest when this
                # one found nothing to translate.
                cursor = 0
                if self._pass_calls == 0:
                    self._rest_until = time.monotonic() + IDLE_PASS_REST_SECONDS
                self._pass_calls = 0
                break
            for game_id in game_ids:
                if time.monotonic() >= deadline:
                    break
                if await self._games.translate(game_id):
                    self._pass_calls += 1
                cursor = game_id
        await self._repo.set_app_setting(CURSOR_KEY, str(cursor))
