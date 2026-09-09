"""Logging every group message the bot sends, for the admin panel's
"стереть сообщения бота" (SPEC 6.4) — no official way to list a bot's own
past messages in Telegram, so this log is the only thing there is to
delete from."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aiogram.types import Chat, Message

from bot.db.repo import Repo
from bot.services.message_log import (
    MessageLogMiddleware,
    _preview_of,
    _sent_messages,
    stats_category,
)

CHAT_ID = -100777


def group_message(message_id: int = 1) -> Message:
    return Message(
        message_id=message_id, date=datetime.now(UTC), chat=Chat(id=CHAT_ID, type="supergroup")
    )


def private_message(message_id: int = 1) -> Message:
    return Message(message_id=message_id, date=datetime.now(UTC), chat=Chat(id=42, type="private"))


def text_message(message_id: int, text: str) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=Chat(id=CHAT_ID, type="supergroup"),
        text=text,
    )


def caption_message(message_id: int, caption: str) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=Chat(id=CHAT_ID, type="supergroup"),
        caption=caption,
    )


def test_sent_messages_unwraps_a_single_message() -> None:
    msg = group_message()
    assert _sent_messages(msg) == [msg]


def test_sent_messages_unwraps_a_media_group() -> None:
    msgs = [group_message(1), group_message(2)]
    assert _sent_messages(msgs) == msgs


def test_sent_messages_ignores_non_message_results() -> None:
    assert _sent_messages(True) == []
    assert _sent_messages(None) == []
    assert _sent_messages([]) == []


async def test_middleware_logs_only_group_messages(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Test chat", 1)
    middleware = MessageLogMiddleware(repo)

    async def returns_group(_bot: object, _method: object) -> Message:
        return group_message(5)

    async def returns_private(_bot: object, _method: object) -> Message:
        return private_message(6)

    await middleware(returns_group, object(), object())  # type: ignore[arg-type]
    await middleware(returns_private, object(), object())  # type: ignore[arg-type]

    logged = await repo.bot_messages_since(CHAT_ID, datetime.now(UTC) - timedelta(minutes=1))
    assert logged == [5]


async def test_bot_messages_round_trip_and_forget(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Test chat", 1)
    now = datetime.now(UTC)
    await repo.log_bot_message(CHAT_ID, 1)
    await repo.log_bot_message(CHAT_ID, 2)

    assert sorted(await repo.bot_messages_since(CHAT_ID, now - timedelta(minutes=1))) == [1, 2]
    # A cutoff in the future sees nothing — sanity check the "since" bound works.
    assert await repo.bot_messages_since(CHAT_ID, now + timedelta(minutes=1)) == []

    await repo.forget_bot_messages(CHAT_ID, [1])
    assert await repo.bot_messages_since(CHAT_ID, now - timedelta(minutes=1)) == [2]


async def test_last_bot_message_is_the_highest_message_id(repo: Repo) -> None:
    """For /delete_last (chat.py) — message_id, not sent_at: Telegram hands
    out ids sequentially per chat, and a poll tick can log several messages
    within the same second, where sent_at alone couldn't tell them apart."""
    await repo.upsert_chat(CHAT_ID, "Test chat", 1)
    await repo.log_bot_message(CHAT_ID, 5)
    await repo.log_bot_message(CHAT_ID, 9)
    await repo.log_bot_message(CHAT_ID, 7)

    assert await repo.last_bot_message(CHAT_ID) == 9


async def test_last_bot_message_is_none_for_an_untouched_chat(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Test chat", 1)
    assert await repo.last_bot_message(CHAT_ID) is None


async def test_middleware_marks_system_by_default(repo: Repo) -> None:
    """A call site that forgets to wrap itself in stats_category() fails
    safe (2026-09-05 follow-up): the message just becomes eligible for
    poller/message_cleanup.py's auto-delete, rather than lingering in the
    never-deleted "stats" category forever."""
    await repo.upsert_chat(CHAT_ID, "Test chat", 1)
    middleware = MessageLogMiddleware(repo)

    async def returns_group(_bot: object, _method: object) -> Message:
        return group_message(11)

    await middleware(returns_group, object(), object())  # type: ignore[arg-type]

    assert await repo.all_system_bot_messages(CHAT_ID) == [11]


async def test_stats_category_marks_the_logged_row_as_not_system(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Test chat", 1)
    middleware = MessageLogMiddleware(repo)

    async def returns_group(_bot: object, _method: object) -> Message:
        return group_message(12)

    with stats_category():
        await middleware(returns_group, object(), object())  # type: ignore[arg-type]

    assert await repo.all_system_bot_messages(CHAT_ID) == []
    logged = await repo.bot_messages_since(CHAT_ID, datetime.now(UTC) - timedelta(minutes=1))
    assert 12 in logged


async def test_stats_category_does_not_leak_across_calls(repo: Repo) -> None:
    """The ContextVar resets after the `with` block — a later, unwrapped
    send must not inherit the previous call's "stats" classification."""
    await repo.upsert_chat(CHAT_ID, "Test chat", 1)
    middleware = MessageLogMiddleware(repo)

    async def returns(message_id: int):
        async def _inner(_bot: object, _method: object) -> Message:
            return group_message(message_id)

        return _inner

    with stats_category():
        await middleware(await returns(13), object(), object())  # type: ignore[arg-type]
    await middleware(await returns(14), object(), object())  # type: ignore[arg-type]

    assert await repo.all_system_bot_messages(CHAT_ID) == [14]


async def test_log_bot_message_upserts_category_and_timestamp(repo: Repo) -> None:
    """An edited message is re-logged under the same id (2026-09-05
    follow-up) — /hltb's own flow edits one message from a system prompt
    into the final "stats" card, and that edit must reclassify the row,
    not leave it stuck as whatever it was first logged as."""
    await repo.upsert_chat(CHAT_ID, "Test chat", 1)
    await repo.log_bot_message(CHAT_ID, 1, is_system=True)
    assert await repo.all_system_bot_messages(CHAT_ID) == [1]

    await repo.log_bot_message(CHAT_ID, 1, is_system=False)
    assert await repo.all_system_bot_messages(CHAT_ID) == []


async def test_system_message_queries_filter_correctly(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Test chat", 1)
    await repo.log_bot_message(CHAT_ID, 1, is_system=True)
    await repo.log_bot_message(CHAT_ID, 2, is_system=False)

    now = datetime.now(UTC)
    assert await repo.system_bot_messages_since(CHAT_ID, now - timedelta(minutes=1)) == [1]
    assert await repo.all_system_bot_messages(CHAT_ID) == [1]
    result = await repo.last_non_system_bot_message(CHAT_ID)
    assert result is not None
    assert result.message_id == 2

    due = await repo.due_system_messages(now + timedelta(minutes=1))
    assert (CHAT_ID, 1) in due
    assert (CHAT_ID, 2) not in due


# _preview_of — first couple of non-blank lines, for /delete_last's own
# confirmation (2026-09-09 user request).


def test_preview_of_takes_the_first_two_non_blank_lines() -> None:
    msg = text_message(1, "Первая строка\n\nВторая строка\nТретья строка")
    assert _preview_of(msg) == "Первая строка\nВторая строка"


def test_preview_of_falls_back_to_caption() -> None:
    msg = caption_message(1, "Подпись к фото")
    assert _preview_of(msg) == "Подпись к фото"


def test_preview_of_is_none_for_an_empty_message() -> None:
    msg = group_message(1)
    assert _preview_of(msg) is None


def test_preview_of_truncates_long_lines() -> None:
    msg = text_message(1, "x" * 300)
    preview = _preview_of(msg)
    assert preview is not None
    assert len(preview) == 200


async def test_middleware_logs_the_preview(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Test chat", 1)
    middleware = MessageLogMiddleware(repo)

    async def returns_group(_bot: object, _method: object) -> Message:
        return text_message(20, "Тестовое сообщение")

    with stats_category():
        await middleware(returns_group, object(), object())  # type: ignore[arg-type]

    result = await repo.last_non_system_bot_message(CHAT_ID)
    assert result is not None
    assert result.message_id == 20
    assert result.preview == "Тестовое сообщение"


async def test_last_non_system_bot_message_preview_round_trips(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Test chat", 1)
    await repo.log_bot_message(CHAT_ID, 1, is_system=False, preview="строка один")

    result = await repo.last_non_system_bot_message(CHAT_ID)
    assert result is not None
    assert result.message_id == 1
    assert result.preview == "строка один"


async def test_last_non_system_bot_message_preview_defaults_to_none(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Test chat", 1)
    await repo.log_bot_message(CHAT_ID, 1, is_system=False)

    result = await repo.last_non_system_bot_message(CHAT_ID)
    assert result is not None
    assert result.preview is None


async def test_last_non_system_bot_message_is_none_for_an_untouched_chat(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Test chat", 1)
    assert await repo.last_non_system_bot_message(CHAT_ID) is None
