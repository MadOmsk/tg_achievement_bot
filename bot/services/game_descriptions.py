"""A game's description in Russian, translated once (owner, 2026-10-28; #230).

The achievements' rule (`translate/descriptions.py`) for a game's story: a
store's own Russian is kept as `native`; with none, the English a Russian
reader is shown is translated by Haiku the first time the game's page is
opened in Russian, and kept beside a hash of that English — a version's as
`llm` (`versions.description_ru_of`), HowLongToBeat's as `summary_ru`
(`summary_ru_of`). An unchanged text is never paid for twice; a changed one
is translated again. No key, or a failed call: the English stays, and the
next visit tries again. In the background, so the page never waits.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from bot.services.game_page import text_hash, to_translate
from bot.services.translate.auth import AnthropicNotConfiguredError
from bot.services.translate.client import translate_game_description

if TYPE_CHECKING:
    from bot.db.repo import Repo
    from bot.services.translate.auth import AnthropicAuth

log = logging.getLogger(__name__)

# What is being translated now, so a crowd opening one game pays once.
_RUNNING: set[tuple[str, int]] = set()
_TASKS: set[asyncio.Task] = set()


def translate_later(
    repo: Repo,
    anthropic_auth: AnthropicAuth | None,
    versions: list[dict[str, Any]],
    hltb: dict[str, Any] | None,
) -> None:
    """Start translating the game's description when it has no Russian one."""
    target = to_translate(versions, hltb)
    if target is None or anthropic_auth is None:
        return
    kind, key, english = target
    if (kind, key) in _RUNNING:
        return
    _RUNNING.add((kind, key))
    task = asyncio.create_task(_translate(repo, anthropic_auth, kind, key, english))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


async def _translate(
    repo: Repo, anthropic_auth: AnthropicAuth, kind: str, key: int, english: str
) -> None:
    try:
        try:
            api_key = await anthropic_auth.require_key()
        except AnthropicNotConfiguredError:
            return
        translated = await translate_game_description(api_key, english, target_language="ru")
        if not translated:
            return
        if kind == "version":
            await repo.set_version_description_ru(key, translated, text_hash(english))
        else:
            await repo.set_hltb_summary_ru(key, translated, text_hash(english))
    except Exception as exc:  # a translation never fails anything else
        log.warning("game description %s %s not translated: %r", kind, key, exc)
    finally:
        _RUNNING.discard((kind, key))
