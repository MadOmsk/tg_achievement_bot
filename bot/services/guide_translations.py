"""The Steam guides' tips in the other language (owner, 2026-10-30).

A tip is kept in the language its guide was written in (`replace_title_tips`);
this puts it into the other one, so a Russian reader gets a Russian tip and an
English reader an English one. A game's tips go together, a few per call,
each beside its achievement's name and description, so the terms stay the
same across the game. Translated as soon as a game's tips are worked out
(`SteamExtras` → `later`); `poller/translations.py` works through the tips
kept before. A changed tip loses its translation and gets a new one. No key,
or a failed call: the tip stays in its own language and the game rests an
hour.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from bot.services.translate.client import translate_guides

if TYPE_CHECKING:
    from bot.db.repo import Repo
    from bot.services.translate.auth import AnthropicAuth

log = logging.getLogger(__name__)

RETRY_SECONDS = 3600
# One call: at most this many tips and characters, so its answer fits.
CALL_TIPS = 15
CALL_CHARS = 8000


class GuideTranslator:
    def __init__(self, repo: Repo, anthropic_auth: AnthropicAuth | None) -> None:
        self._repo = repo
        self._auth = anthropic_auth
        self._failed: dict[tuple[str, str], float] = {}
        self._running: set[tuple[str, str]] = set()
        self._tasks: set[asyncio.Task] = set()

    def later(self, platform: str, title_id: str) -> None:
        """Translate the game's tips in the background."""
        if self._auth is None:
            return
        task = asyncio.create_task(self.translate(platform, title_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def translate_some(self, games: int) -> int:
        """The backlog: up to `games` games whose tips are in one language only;
        how many were taken."""
        now = time.monotonic()
        taken = 0
        for key in await self._repo.titles_with_untranslated_guides(games + len(self._failed)):
            if taken >= games:
                break
            if self._failed.get(key, 0) > now:
                continue
            taken += 1
            await self.translate(*key)
        return taken

    async def translate(self, platform: str, title_id: str) -> None:
        key = (platform, title_id)
        if self._auth is None or key in self._running:
            return
        self._running.add(key)
        try:
            api_key = await self._auth.get_key()
            if not api_key:
                return
            tips = await self._repo.untranslated_guides(platform, title_id)
            for lang in ("en", "ru"):
                target = "ru" if lang == "en" else "en"
                rows = [row for row in tips if row[1] == lang]
                for batch in _batches(rows):
                    done = await translate_guides(
                        api_key, [(r[2], r[3], r[4]) for r in batch], target_language=target
                    )
                    if done is None:
                        self._failed[key] = time.monotonic() + RETRY_SECONDS
                        return
                    for row, text in zip(batch, done, strict=True):
                        await self._repo.set_guide_translation(
                            platform, title_id, row[0], of=row[4], lang=target, text=text
                        )
            self._failed.pop(key, None)
        except Exception as exc:  # a translation never fails anything else
            log.warning("tips of %s %s not translated: %r", platform, title_id, exc)
        finally:
            self._running.discard(key)


def _batches(rows: list) -> list[list]:
    batches: list[list] = []
    current: list = []
    size = 0
    for row in rows:
        if current and (len(current) >= CALL_TIPS or size + len(row[4]) > CALL_CHARS):
            batches.append(current)
            current, size = [], 0
        current.append(row)
        size += len(row[4])
    if current:
        batches.append(current)
    return batches
