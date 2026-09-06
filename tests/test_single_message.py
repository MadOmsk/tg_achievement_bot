"""services/single_message.py — delete-then-send for self-deduplicating
message kinds (Follow-up 2026-09-06): /panel, /summary, /recent, a specific
person's /stats card."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.services.single_message import send_replacing

CHAT_ID = -100777


class FakeBot:
    def __init__(self, *, fail_delete: bool = False) -> None:
        self.sent: list[tuple[int, str]] = []
        self.deleted: list[tuple[int, int]] = []
        self._fail_delete = fail_delete

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> _FakeMessage:
        message_id = len(self.sent) + 1
        self.sent.append((chat_id, text))
        return _FakeMessage(message_id)

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        if self._fail_delete:
            raise RuntimeError("message not found")
        self.deleted.append((chat_id, message_id))


class _FakeMessage:
    def __init__(self, message_id: int) -> None:
        self.message_id = message_id


async def test_first_send_has_nothing_to_delete(repo: Repo) -> None:
    bot = FakeBot()

    message_id = await send_replacing(bot, repo, CHAT_ID, "recent", "hello")

    assert bot.deleted == []
    assert bot.sent == [(CHAT_ID, "hello")]
    assert await repo.tracked_message(CHAT_ID, "recent") == message_id


async def test_second_send_deletes_the_first_and_tracks_the_new_one(repo: Repo) -> None:
    bot = FakeBot()

    first_id = await send_replacing(bot, repo, CHAT_ID, "recent", "first")
    second_id = await send_replacing(bot, repo, CHAT_ID, "recent", "second")

    assert bot.deleted == [(CHAT_ID, first_id)]
    assert await repo.tracked_message(CHAT_ID, "recent") == second_id


async def test_a_failed_delete_does_not_block_the_new_send(repo: Repo) -> None:
    """The old message is already gone (age, a manual delete, a chat-wide
    wipe) — exactly as fine to fail on as one that was never there."""
    bot = FakeBot(fail_delete=True)
    await send_replacing(bot, repo, CHAT_ID, "recent", "first")

    second_id = await send_replacing(bot, repo, CHAT_ID, "recent", "second")

    assert bot.sent[-1] == (CHAT_ID, "second")
    assert await repo.tracked_message(CHAT_ID, "recent") == second_id


async def test_different_kinds_never_collide(repo: Repo) -> None:
    bot = FakeBot()
    await send_replacing(bot, repo, CHAT_ID, "recent", "recent text")
    await send_replacing(bot, repo, CHAT_ID, "summary", "summary text")

    assert bot.deleted == []  # different kind, nothing to replace
    assert await repo.tracked_message(CHAT_ID, "recent") is not None
    assert await repo.tracked_message(CHAT_ID, "summary") is not None


async def test_different_subjects_of_the_same_kind_never_collide(repo: Repo) -> None:
    """/stats' own scope — a card about person A must not replace one about
    person B in the same chat (SPEC 9's "по 1 шт на юзера")."""
    bot = FakeBot()
    await send_replacing(bot, repo, CHAT_ID, "stats", "Igor's card", subject_id=1)
    await send_replacing(bot, repo, CHAT_ID, "stats", "Anna's card", subject_id=2)

    assert bot.deleted == []
    assert await repo.tracked_message(CHAT_ID, "stats", 1) is not None
    assert await repo.tracked_message(CHAT_ID, "stats", 2) is not None


async def test_same_subject_replaces_its_own_previous_card(repo: Repo) -> None:
    bot = FakeBot()
    first_id = await send_replacing(bot, repo, CHAT_ID, "stats", "old", subject_id=1)
    second_id = await send_replacing(bot, repo, CHAT_ID, "stats", "new", subject_id=1)

    assert bot.deleted == [(CHAT_ID, first_id)]
    assert await repo.tracked_message(CHAT_ID, "stats", 1) == second_id
