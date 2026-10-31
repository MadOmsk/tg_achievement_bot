"""A game put into Russian whole, one job wherever it comes from.

Its description (a store's own Russian is kept as `native`; with none, the English
a Russian reader is shown is translated and kept beside a hash of that English: a
version's as `llm`, HowLongToBeat's as `summary_ru`; #230), its achievements'
descriptions (`translate/descriptions.py`: a Russian side the catalog already holds
only gets marked, unpaid), its tips and its newest posts.

**One job, three doors** (owner, 2026-10-31): the queue (`poller/translations.py`),
the octopus and store collection (`later`), and a page opened in the Mini App
(`pending`), which shows the text blurred and asks again. The page never waits, and
nothing is translated twice: a game being worked on is not started again. The bot's
own messages have another rule: a post waits for its translation before it goes out.

No key, or a failed call: the English stays, and the game rests an hour.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bot.services.game_page import text_hash, to_translate
from bot.services.translate.client import translate_game_description
from bot.services.translate.descriptions import bilingual_descriptions
from bot.util import looks_russian

if TYPE_CHECKING:
    from bot.db.repo import Repo
    from bot.services.guide_translations import GuideTranslator
    from bot.services.news_translations import NewsTranslator
    from bot.services.translate.auth import AnthropicAuth

log = logging.getLogger(__name__)

# A game the model could not finish rests this long before another try, twice as
# long each time it fails again, up to a day: a text it cannot do is not paid for hourly.
RETRY_SECONDS = 3600
LONGEST_REST_SECONDS = 86400
# Games worked on at once, whoever asked; each sends a few calls at once itself.
GAMES_AT_ONCE = 5
# A game's newest posts go with it: what its page shows.
POSTS_WITH_A_GAME = 5
# A Russian reader's language: the only one anything is translated for here.
READER_LOCALE = "ru"


@dataclass(frozen=True)
class Pending:
    """What a page should show blurred."""

    description: bool = False
    achievements: bool = False


class GameTranslator:
    def __init__(
        self,
        repo: Repo,
        anthropic_auth: AnthropicAuth | None,
        guides: GuideTranslator | None = None,
        news: NewsTranslator | None = None,
    ) -> None:
        self._repo = repo
        self._auth = anthropic_auth
        self._guides = guides
        self._news = news
        # What is being translated now, so two callers pay once.
        self._running: set[int] = set()
        self._failed: dict[int, float] = {}
        self._failures: dict[int, int] = {}
        self._slots = asyncio.Semaphore(GAMES_AT_ONCE)
        self._tasks: set[asyncio.Task] = set()

    def later(self, game_ids: Iterable[int]) -> None:
        """Translate these games in the background."""
        if self._auth is None:
            return
        for game_id in game_ids:
            if game_id in self._running:
                continue
            # Marked here, not in the task: a page asking again a moment later
            # must find it running.
            self._running.add(game_id)
            task = asyncio.create_task(self._run(game_id))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def pending(self, game_id: int, locale: str) -> Pending:
        """What of this game is on its way to a reader of `locale`, starting the
        work when it is not. Nothing when it cannot come: no key, resting."""
        if locale != READER_LOCALE or self._auth is None or not await self._auth.get_key():
            return Pending()
        if time.monotonic() < self._failed.get(game_id, 0):
            return Pending()
        found = await self._missing(game_id)
        if found.description or found.achievements:
            self.later([game_id])
        return found

    async def rows_on_their_way(self, platform: str, title_id: str) -> set[str]:
        """Which of a list's achievements a page shows blurred: those waiting for the
        model. A Russian side already here is only marked, and shows as it is."""
        waiting = await self._repo.catalog_untranslated_descriptions(platform, title_id)
        return {key for key, (russian, _) in waiting.items() if not looks_russian(russian)}

    async def is_due(self, game_id: int) -> bool:
        """Whether the queue has work here: anything missing, and not resting."""
        if game_id in self._running or time.monotonic() < self._failed.get(game_id, 0):
            return False
        found = await self._missing(game_id)
        return found.description or found.achievements

    async def translate(self, game_id: int) -> bool:
        """The game whole, now; True when anything was missing."""
        if self._auth is None or game_id in self._running:
            return False
        self._running.add(game_id)
        return await self._run(game_id)

    async def _run(self, game_id: int) -> bool:
        try:
            async with self._slots:
                if time.monotonic() < self._failed.get(game_id, 0):
                    return False
                if not await self._auth.get_key():
                    return False
                found = await self._missing(game_id)
                lists = await self._repo.game_page_lists(game_id)
                await asyncio.gather(
                    self._description(game_id),
                    *(self._achievements(str(r["platform"]), str(r["title_id"])) for r in lists),
                )
                # What failed stays missing: it rests, or a page would blur it for
                # ever and the queue would pay for it every pass.
                left = await self._missing(game_id)
                if left.description or left.achievements:
                    self._rest(game_id)
                else:
                    self._failed.pop(game_id, None)
                    self._failures.pop(game_id, None)
            # Outside the slot: posts go one at a time, and an opened game's blurred
            # text must not wait behind another game's.
            await asyncio.gather(
                *(self._tips_and_posts(str(r["platform"]), str(r["title_id"])) for r in lists)
            )
            return found.description or found.achievements
        except Exception as exc:  # a translation never fails anything else
            log.warning("game %s not translated: %r", game_id, exc)
            self._rest(game_id)
            return False
        finally:
            self._running.discard(game_id)

    def _rest(self, game_id: int) -> None:
        failures = self._failures.get(game_id, 0)
        self._failures[game_id] = failures + 1
        rest = min(RETRY_SECONDS * 2**failures, LONGEST_REST_SECONDS)
        self._failed[game_id] = time.monotonic() + rest
        log.info("game %s rests %s s before its translation is tried again", game_id, rest)

    async def _missing(self, game_id: int) -> Pending:
        versions = await self._repo.game_page_versions(game_id)
        found = await self._repo.game_hltb(game_id)
        description = to_translate(versions, found["entry"] if found else None) is not None
        achievements = False
        for row in await self._repo.game_page_lists(game_id):
            if await self._repo.catalog_untranslated_descriptions(
                str(row["platform"]), str(row["title_id"])
            ):
                achievements = True
                break
        return Pending(description, achievements)

    async def _description(self, game_id: int) -> None:
        versions = await self._repo.game_page_versions(game_id)
        found = await self._repo.game_hltb(game_id)
        target = to_translate(versions, found["entry"] if found else None)
        if target is None:
            return
        kind, key, english = target
        api_key = await self._auth.get_key()
        translated = await translate_game_description(api_key, english, target_language="ru")
        if not translated:
            return
        if kind == "version":
            await self._repo.set_version_description_ru(key, translated, text_hash(english))
        else:
            await self._repo.set_hltb_summary_ru(key, translated, text_hash(english))

    async def _achievements(self, platform: str, title_id: str) -> None:
        pending = await self._repo.catalog_untranslated_descriptions(platform, title_id)
        if pending:
            await bilingual_descriptions(self._repo, self._auth, platform, title_id, pending)

    async def _tips_and_posts(self, platform: str, title_id: str) -> None:
        if self._guides is not None:
            await self._guides.translate(platform, title_id)
        if self._news is not None:
            steam = await self._repo.title_steam(platform, title_id)
            if steam is not None and steam.steam_appid:
                await self._news.translate(appid=int(steam.steam_appid), limit=POSTS_WITH_A_GAME)
