"""Which failed sends mean the chat is gone for good (#116)."""

from unittest.mock import MagicMock

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from bot.services.chat_gone import chat_is_gone


def test_a_kick_and_a_missing_chat_are_gone_anything_else_is_not() -> None:
    method = MagicMock()
    assert chat_is_gone(TelegramForbiddenError(method=method, message="Forbidden: bot was kicked"))
    assert chat_is_gone(TelegramBadRequest(method=method, message="Bad Request: chat not found"))
    assert not chat_is_gone(
        TelegramBadRequest(method=method, message="Bad Request: can't parse entities")
    )
    assert not chat_is_gone(TelegramRetryAfter(method=method, message="Too Many", retry_after=3))
    assert not chat_is_gone(RuntimeError("chat not found"))
