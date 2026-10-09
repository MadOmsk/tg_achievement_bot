"""Removing the bot's own messages from a chat, for both admin panels (the
bot's chat card and the Mini App's): what each kind of wipe takes, deleting
it in the Bot API's chunks, and "delete the last one". Never used on the
super-admin's own chat — nothing is deleted there.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Any

from bot.db.repo import Repo
from bot.util import utcnow

log = logging.getLogger(__name__)

WIPE_WINDOW_HOURS = 24
# The Bot API's own cap on deleteMessages.
_CHUNK = 100


class Wipe(StrEnum):
    """Each wipe's name is also the Mini App's action."""

    ALL_24H = "wipe_24h"  # everything the bot sent in the last day
    # System messages only — published achievements, stats and summaries stay,
    # so these two are a routine cleanup, not a "just in case" tool.
    SYSTEM_24H = "wipe_system_24h"
    SYSTEM_ALL = "wipe_system_all"


async def messages_to_wipe(repo: Repo, chat_id: int, kind: Wipe) -> list[int]:
    since = utcnow() - timedelta(hours=WIPE_WINDOW_HOURS)
    if kind is Wipe.ALL_24H:
        return await repo.bot_messages_since(chat_id, since)
    if kind is Wipe.SYSTEM_24H:
        return await repo.system_bot_messages_since(chat_id, since)
    return await repo.all_system_bot_messages(chat_id)


async def wipe(bot: Any, repo: Repo, chat_id: int, ids: list[int]) -> bool:
    """Delete what the caller decided on, in chunks, and forget the log rows
    either way (Telegram silently skips ids it can no longer delete — too
    old, already gone — and retrying them later would not help). Whether
    every chunk went through."""
    ok = True
    for start in range(0, len(ids), _CHUNK):
        try:
            await bot.delete_messages(chat_id, ids[start : start + _CHUNK])
        except Exception:
            log.info("bulk delete failed for chat %s, chunk at %s", chat_id, start)
            ok = False
    await repo.forget_bot_messages(chat_id, ids)
    return ok


@dataclass(frozen=True, slots=True)
class LastDeleted:
    deleted: bool
    # The first lines of what went, `bot_messages.preview`; None if unknown.
    preview: str | None


async def delete_last(bot: Any, repo: Repo, chat_id: int) -> LastDeleted | None:
    """/delete_last's target — the bot's latest message that is not an
    achievement post (#101). None when there is nothing to delete; the row is
    forgotten even when Telegram refuses (too old to delete)."""
    target = await repo.last_deletable_bot_message(chat_id)
    if target is None:
        return None
    try:
        await bot.delete_message(chat_id, target.message_id)
    except Exception:
        log.info("admin delete_last failed for chat %s message %s", chat_id, target.message_id)
        await repo.forget_bot_messages(chat_id, [target.message_id])
        return LastDeleted(False, target.preview)
    await repo.forget_bot_messages(chat_id, [target.message_id])
    return LastDeleted(True, target.preview)
