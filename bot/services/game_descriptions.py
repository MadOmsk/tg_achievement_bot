"""A game's description in Russian, translated once (owner, 2026-10-28; #230).

The achievements' rule (`translate/descriptions.py`) for a game's story: a
store's own Russian is kept as `native`; with none, the English a Russian
reader is shown is translated by Haiku as soon as it is there — when the
game's page is opened in Russian, and right after a background collection
wrote it (`translate_game`, the collector's `on_collected`) — and kept beside
a hash of that English: a version's as `llm` (`versions.description_ru_of`),
HowLongToBeat's as `summary_ru` (`summary_ru_of`). An unchanged text is never
paid for twice; a changed one is translated again. No key, or a failed call:
the English stays, and the next visit tries again. In the background, so the
page never waits: it says the text is on its way (`running`), and the Mini
App asks again a moment later.
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
) -> bool:
    """Start translating the game's description when it has no Russian one;
    whether a translation of it is on its way now."""
    target = to_translate(versions, hltb)
    if target is None or anthropic_auth is None:
        return False
    kind, key, english = target
    if (kind, key) in _RUNNING:
        return True
    _RUNNING.add((kind, key))
    task = asyncio.create_task(_translate(repo, anthropic_auth, kind, key, english))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return True


async def translate_game(
    repo: Repo, anthropic_auth: AnthropicAuth | None, platform: str, title_id: str
) -> None:
    """The description of the game a list is in, translated now if it has
    no Russian one — after a collection wrote its English (#230)."""
    game_id = await repo.game_of_list(platform, title_id)
    if game_id is None:
        return
    found = await repo.game_hltb(game_id)
    translate_later(
        repo,
        anthropic_auth,
        await repo.game_page_versions(game_id),
        found["entry"] if found else None,
    )


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
