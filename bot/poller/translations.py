"""The translators' queue (owner, 2026-10-31): Russian for whatever nobody has
opened yet, in batches, at one pace.

**Off until a super-admin switches it on** (`translation_queue`, /admin →
Таймеры): it spends money with nobody asking. On, every
`translation_interval_minutes` it takes `translation_batch_games` games, those
played here first, each whole
(`GameTranslator`), and as many of the Steam posts and guides kept before. A game
opened in the Mini App or just collected does not wait for it. A pass that found
nothing rests an hour. No Anthropic key: nothing happens.
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

QUEUE_KEY = "translation_queue"
BATCH_KEY = "translation_batch_games"
DEFAULT_BATCH = 20
INTERVAL_KEY = "translation_interval_minutes"
DEFAULT_INTERVAL = 5
# A whole pass over the games that found nothing rests this long.
IDLE_PASS_REST_SECONDS = 3600


class Translations:
    def __init__(
        self, repo: Repo, news: NewsTranslator, guides: GuideTranslator, games: GameTranslator
    ) -> None:
        self._repo = repo
        self._news = news
        self._guides = guides
        self._games = games
        self._queue: list[int] = []
        self._in_a_pass = False
        self._pass_found = False
        self._next_batch = 0.0
        self._rest_until = 0.0

    async def tick(self) -> None:
        if not await self._repo.get_int_setting(QUEUE_KEY, 0):
            return
        now = time.monotonic()
        if now < self._next_batch:
            return
        batch = await self._repo.get_int_setting(BATCH_KEY, DEFAULT_BATCH)
        interval = await self._repo.get_int_setting(INTERVAL_KEY, DEFAULT_INTERVAL)
        self._next_batch = now + interval * 60
        await self.batch(batch, batch)

    async def batch(self, games: int, posts: int) -> dict[str, int]:
        """One batch; how much of each it took."""
        taken, guides, news = await asyncio.gather(
            self._game_batch(games),
            self._guides.translate_some(posts),
            self._news.translate(limit=posts),
        )
        return {"games": taken, "guides": guides, "posts": news}

    async def _game_batch(self, games: int) -> int:
        if time.monotonic() < self._rest_until:
            return 0
        chosen: list[int] = []
        while len(chosen) < games:
            if not self._queue:
                if self._in_a_pass and not self._pass_found:
                    self._in_a_pass = False
                    self._rest_until = time.monotonic() + IDLE_PASS_REST_SECONDS
                    break
                self._queue = await self._repo.games_to_translate_first()
                self._in_a_pass = True
                self._pass_found = False
                if not self._queue:
                    break
            game_id = self._queue.pop(0)
            if await self._games.is_due(game_id):
                chosen.append(game_id)
                self._pass_found = True
        await asyncio.gather(*(self._games.translate(game_id) for game_id in chosen))
        return len(chosen)
