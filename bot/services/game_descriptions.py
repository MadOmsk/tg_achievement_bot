"""A game's description in Russian, translated once (owner, 2026-10-28; #230).

The achievements' rule (`translate/descriptions.py`) for a game's story: a
store's own Russian is kept as `native`; with none, the English a Russian
reader is shown is translated by Haiku and kept beside a hash of that
English — a version's as `llm` (`versions.description_ru_of`),
HowLongToBeat's as `summary_ru` (`summary_ru_of`). An unchanged text is never
paid for twice; a changed one is translated again. No key, or a failed call:
the English stays, and it is tried again later.

**Never when a page is opened** (owner, 2026-10-30): the page must not wait
for it. A game is translated right after it is collected — by the store
collection or the octopus (`later`) — and `poller/translations.py` walks
every game for whatever that missed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from typing import TYPE_CHECKING

from bot.services.game_page import text_hash, to_translate
from bot.services.translate.client import translate_game_description

if TYPE_CHECKING:
    from bot.db.repo import Repo
    from bot.services.translate.auth import AnthropicAuth

log = logging.getLogger(__name__)

# A text the model could not translate rests this long before another try.
RETRY_SECONDS = 3600


class GameTranslator:
    def __init__(self, repo: Repo, anthropic_auth: AnthropicAuth | None) -> None:
        self._repo = repo
        self._auth = anthropic_auth
        # What is being translated now, so two callers pay once.
        self._running: set[int] = set()
        self._failed: dict[tuple[str, int], float] = {}
        self._tasks: set[asyncio.Task] = set()

    def later(self, game_ids: Iterable[int]) -> None:
        """Translate these games' descriptions in the background."""
        if self._auth is None:
            return
        for game_id in game_ids:
            if game_id in self._running:
                continue
            task = asyncio.create_task(self.translate(game_id))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def translate(self, game_id: int) -> bool:
        """Translate the game's description when it has no Russian one; True
        when the model was asked."""
        if self._auth is None or game_id in self._running:
            return False
        self._running.add(game_id)
        try:
            versions = await self._repo.game_page_versions(game_id)
            found = await self._repo.game_hltb(game_id)
            target = to_translate(versions, found["entry"] if found else None)
            if target is None:
                return False
            kind, key, english = target
            if time.monotonic() < self._failed.get((kind, key), 0):
                return False
            api_key = await self._auth.get_key()
            if not api_key:
                return False
            translated = await translate_game_description(api_key, english, target_language="ru")
            if not translated:
                self._failed[(kind, key)] = time.monotonic() + RETRY_SECONDS
                return True
            if kind == "version":
                await self._repo.set_version_description_ru(key, translated, text_hash(english))
            else:
                await self._repo.set_hltb_summary_ru(key, translated, text_hash(english))
            return True
        except Exception as exc:  # a translation never fails anything else
            log.warning("game %s description not translated: %r", game_id, exc)
            return False
        finally:
            self._running.discard(game_id)
