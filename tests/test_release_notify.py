from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup

from bot.db.repo import Repo
from bot.services.release_notify import (
    CHANGELOG_BASE_URL,
    announce_release_if_needed,
    base_version,
    load_release_summary,
)


class FakeBot:
    def __init__(self, fail_for: set[int] | None = None, missing: set[int] | None = None) -> None:
        self.sent: list[dict[str, Any]] = []
        self.fail_for = fail_for or set()
        self.missing = missing or set()

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
        **kwargs: Any,
    ) -> None:
        if chat_id in self.fail_for:
            # Match TelegramForbiddenError's signature
            raise TelegramForbiddenError(method=MagicMock(), message="Forbidden: bot was kicked")
        if chat_id in self.missing:
            raise TelegramBadRequest(method=MagicMock(), message="Bad Request: chat not found")
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})


def test_base_version_extraction() -> None:
    assert base_version("1.3.0.050") == "1.3.0"
    assert base_version("1.2.4.050") == "1.2.4"
    assert base_version("1.3") == "1.3"


@pytest.mark.asyncio
async def test_production_announces_with_localized_button(repo: Repo) -> None:
    # Set up two active group chats (chat_id < 0) with ru and en locales
    chat_ru = -1001001
    chat_en = -1001002
    await repo.upsert_chat(chat_ru, "RU Chat", None)
    await repo.upsert_chat(chat_en, "EN Chat", None)
    await repo.update_chat_settings(chat_ru, locale="ru")
    await repo.update_chat_settings(chat_en, locale="en")

    bot = FakeBot()
    delivered = await announce_release_if_needed(
        bot, repo, "1.3.0.050", is_test=False, sleep_delay=0
    )

    assert delivered == 2
    assert len(bot.sent) == 2

    sent_ru = next(m for m in bot.sent if m["chat_id"] == chat_ru)
    assert "Бот обновлён до версии 1.3.0.050!" in sent_ru["text"]
    markup_ru = sent_ru["reply_markup"]
    assert isinstance(markup_ru, InlineKeyboardMarkup)
    btn_ru = markup_ru.inline_keyboard[0][0]
    assert btn_ru.text == "📖 Патчноутс"
    assert btn_ru.url == f"{CHANGELOG_BASE_URL}/1.3.0.ru.md"

    sent_en = next(m for m in bot.sent if m["chat_id"] == chat_en)
    assert "Bot has been updated to version 1.3.0.050!" in sent_en["text"]
    markup_en = sent_en["reply_markup"]
    assert isinstance(markup_en, InlineKeyboardMarkup)
    btn_en = markup_en.inline_keyboard[0][0]
    assert btn_en.text == "📖 Release Notes"
    assert btn_en.url == f"{CHANGELOG_BASE_URL}/1.3.0.en.md"

    # Verify last_announced_version is stored
    assert await repo.get_app_setting("last_announced_version") == "1.3.0.050"


@pytest.mark.asyncio
async def test_test_bot_announces_without_button(repo: Repo) -> None:
    chat_ru = -1002001
    await repo.upsert_chat(chat_ru, "RU Chat", None)
    await repo.update_chat_settings(chat_ru, locale="ru")

    bot = FakeBot()
    delivered = await announce_release_if_needed(
        bot, repo, "1.3.7.050", is_test=True, sleep_delay=0
    )

    assert delivered == 1
    sent = bot.sent[0]
    assert "Тестовый бот обновлён до версии 1.3.7.050!" in sent["text"]
    assert sent["reply_markup"] is None
    assert await repo.get_app_setting("last_announced_version") == "1.3.7.050"


@pytest.mark.asyncio
async def test_duplicate_run_does_not_announce_again(repo: Repo) -> None:
    chat_ru = -1003001
    await repo.upsert_chat(chat_ru, "RU Chat", None)

    bot = FakeBot()
    await announce_release_if_needed(bot, repo, "1.3.0.050", is_test=False, sleep_delay=0)
    assert len(bot.sent) == 1

    # Second call with the same version
    bot.sent.clear()
    delivered = await announce_release_if_needed(
        bot, repo, "1.3.0.050", is_test=False, sleep_delay=0
    )
    assert delivered == 0
    assert len(bot.sent) == 0


@pytest.mark.asyncio
async def test_forbidden_error_deactivates_chat(repo: Repo) -> None:
    chat_kicked = -1004001
    await repo.upsert_chat(chat_kicked, "Kicked Chat", None)

    bot = FakeBot(fail_for={chat_kicked})
    delivered = await announce_release_if_needed(
        bot, repo, "1.3.0.050", is_test=False, sleep_delay=0
    )
    assert delivered == 0

    # Verify chat was deactivated
    cursor = await repo._conn.execute(
        "SELECT is_active FROM chats WHERE chat_id = ?", (chat_kicked,)
    )
    row = await cursor.fetchone()
    assert row["is_active"] == 0


@pytest.mark.asyncio
async def test_a_chat_that_no_longer_exists_is_deactivated(repo: Repo) -> None:
    """ "chat not found" is a chat that is gone, like a kick (#116)."""
    gone, alive = -1004002, -1004003
    await repo.upsert_chat(gone, "Deleted Chat", None)
    await repo.upsert_chat(alive, "Live Chat", None)

    bot = FakeBot(missing={gone})
    delivered = await announce_release_if_needed(
        bot, repo, "1.3.0.050", is_test=False, sleep_delay=0
    )

    assert delivered == 1
    cursor = await repo._conn.execute("SELECT chat_id, is_active FROM chats ORDER BY chat_id")
    assert {r["chat_id"]: r["is_active"] for r in await cursor.fetchall()} == {gone: 0, alive: 1}


@pytest.mark.asyncio
async def test_the_test_bot_leaves_unreachable_chats_active(repo: Repo) -> None:
    """A test bot on a copy of production's database is not a member of those
    chats; "chat not found" there must not switch them off."""
    unreachable = -1004004
    await repo.upsert_chat(unreachable, "Production Chat", None)

    bot = FakeBot(missing={unreachable})
    delivered = await announce_release_if_needed(
        bot, repo, "1.3.0.050", is_test=True, sleep_delay=0
    )

    assert delivered == 0
    cursor = await repo._conn.execute(
        "SELECT is_active FROM chats WHERE chat_id = ?", (unreachable,)
    )
    assert (await cursor.fetchone())["is_active"] == 1


def test_load_release_summary_from_summary_file() -> None:
    summary_ru = load_release_summary("1.4.0", "ru")
    assert summary_ru is not None
    assert "•" in summary_ru
    assert "Mini App" in summary_ru

    summary_en = load_release_summary("1.4.0", "en")
    assert summary_en is not None
    assert "•" in summary_en
    assert "Mini App" in summary_en


def test_load_release_summary_falls_back_to_markdown() -> None:
    # 1.3.0 has .ru.md but no .summary.ru.txt
    summary = load_release_summary("1.3.0", "ru")
    assert summary is not None
    assert "• Оповещения об обновлениях в чатах" in summary


@pytest.mark.asyncio
async def test_production_announces_with_brief_summary(repo: Repo) -> None:
    chat_ru = -1005001
    await repo.upsert_chat(chat_ru, "RU Summary Chat", None)
    await repo.update_chat_settings(chat_ru, locale="ru")

    bot = FakeBot()
    delivered = await announce_release_if_needed(
        bot, repo, "1.4.0.056", is_test=False, sleep_delay=0
    )
    assert delivered == 1
    sent = bot.sent[0]
    assert "Бот обновлён до версии 1.4.0.056!" in sent["text"]
    assert "Кратко о главных изменениях:" in sent["text"]
    assert "• Полный каталог всех достижений игр" in sent["text"]
    assert "Посмотрите подробный список изменений" in sent["text"]
