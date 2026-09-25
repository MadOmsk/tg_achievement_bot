"""Whether a failed send means the chat is gone for good (#116).

Telegram says so two ways: 403 when the bot was removed from a chat that
still exists, and 400 "chat not found" when the chat itself does not exist
any more — deleted, or never reachable by this bot. Only the first used to
deactivate a chat; the second left it active, so every summary, publication
and release announcement kept failing into it with a traceback.
"""

from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError


def chat_is_gone(exc: BaseException) -> bool:
    if isinstance(exc, TelegramForbiddenError):
        return True
    return isinstance(exc, TelegramBadRequest) and "chat not found" in exc.message.lower()
