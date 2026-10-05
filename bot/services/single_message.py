"""Delete-then-send for message kinds that must never have more than one
live copy per (chat[, subject]) — /panel, /summary, /recent, and a specific
person's /stats card (Follow-up 2026-09-06). An old copy has already
scrolled away and nobody will ever scroll back for it, so replacing it
outright is strictly better than letting a person's own repeated commands
pile up duplicates and spam the chat.

/online and /admin are NOT here — both already (or now) have their own
dedicated one-row-per-scope table because they also auto-refresh in place
on a timer, which this plain dedup helper has no concept of
(poller/online_refresh.py, poller/admin_refresh.py).
"""

from __future__ import annotations

import contextlib
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from bot.db.repo import Repo


async def send_replacing(
    bot: Bot,
    repo: Repo,
    chat_id: int,
    kind: str,
    text: str,
    *,
    subject_id: int = 0,
    reply_markup: InlineKeyboardMarkup | None = None,
    **kwargs: Any,
) -> int:
    """Deletes whatever this (chat, kind, subject) last sent, then sends and
    tracks the new one. The delete is best-effort: an already-gone message
    (age, a manual delete, the chat's bot-message wipe) is exactly as fine
    to fail on as one that was never there — either way there is nothing
    left to clean up before sending the replacement."""
    previous_id = await repo.tracked_message(chat_id, kind, subject_id)
    if previous_id is not None:
        with contextlib.suppress(Exception):
            await bot.delete_message(chat_id, previous_id)
    sent = await bot.send_message(chat_id, text, reply_markup=reply_markup, **kwargs)
    await repo.set_tracked_message(chat_id, kind, subject_id, sent.message_id)
    return sent.message_id
