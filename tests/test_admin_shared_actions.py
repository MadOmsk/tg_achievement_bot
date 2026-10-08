"""The super-admin's actions on an account and on a chat's messages are one
implementation for the bot and the Mini App (`services/admin_accounts.py`,
`services/admin_cleanup.py`)."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.services import admin_cleanup
from bot.services.admin_accounts import AdminAccounts
from bot.services.admin_cleanup import Wipe

XUID = "2533274900000001"
CHAT_ID = -100500


class _FakeXbox:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def refresh_user(self, person, external_id, name, locale) -> str:
        self.calls.append("refresh")
        return "now"

    async def catch_up(self, person, xuid, name, since, window, max_titles):
        self.calls.append("catch_up")
        return 2, 1

    async def backfill(self, person, xuid) -> None:
        self.calls.append("backfill")


class _FakeBot:
    def __init__(self, fail_chunks: int = 0) -> None:
        self.chunks: list[list[int]] = []
        self.deleted: list[int] = []
        self._fail = fail_chunks

    async def delete_messages(self, chat_id, ids) -> None:
        self.chunks.append(list(ids))
        if self._fail:
            self._fail -= 1
            raise RuntimeError("refused")

    async def delete_message(self, chat_id, message_id) -> None:
        self.deleted.append(message_id)


async def test_refresh_pulls_the_delta_too(repo: Repo, settings) -> None:
    """The Mini App's sync used to look at the present moment only; the
    bot's "🔄 Обновить" also catches up since the newest unlock."""
    person = await repo.ensure_user(1, "someone")
    assert person is not None
    await repo.link_xbox_account(person, XUID, "GamerTag", 0)
    xbox = _FakeXbox()
    accounts = AdminAccounts(repo, settings, xbox=xbox, steam=None, psn=None)  # type: ignore[arg-type]

    summary = await accounts.refresh("xbox", person, locale="ru")

    assert xbox.calls == ["refresh", "catch_up"]
    assert summary is not None and summary.startswith("now\n")


async def test_an_account_not_linked_is_neither_refreshed_nor_reset(repo: Repo, settings) -> None:
    person = await repo.ensure_user(1, "someone")
    assert person is not None
    xbox = _FakeXbox()
    accounts = AdminAccounts(repo, settings, xbox=xbox, steam=None, psn=None)  # type: ignore[arg-type]

    assert await accounts.refresh("xbox", person, locale="ru") is None
    assert await accounts.reset("xbox", person) is False
    assert await accounts.reset("steam", person) is False
    assert xbox.calls == []


async def test_reset_wipes_and_reads_the_history_again(repo: Repo, settings) -> None:
    person = await repo.ensure_user(1, "someone")
    assert person is not None
    await repo.link_xbox_account(person, XUID, "GamerTag", 0)
    xbox = _FakeXbox()

    assert await AdminAccounts(repo, settings, xbox=xbox, steam=None, psn=None).reset(  # type: ignore[arg-type]
        "xbox", person
    )
    assert xbox.calls == ["backfill"]


async def test_a_wipe_goes_in_chunks_of_a_hundred_and_forgets_every_row(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Чат", 1)
    for message_id in range(1, 151):
        await repo.log_bot_message(CHAT_ID, message_id, is_system=True)
    bot = _FakeBot(fail_chunks=1)

    ids = await admin_cleanup.messages_to_wipe(repo, CHAT_ID, Wipe.SYSTEM_ALL)
    ok = await admin_cleanup.wipe(bot, repo, CHAT_ID, ids)

    assert [len(chunk) for chunk in bot.chunks] == [100, 50]
    assert ok is False  # one chunk refused
    assert await admin_cleanup.messages_to_wipe(repo, CHAT_ID, Wipe.SYSTEM_ALL) == []


async def test_delete_last_with_nothing_to_delete(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Чат", 1)
    assert await admin_cleanup.delete_last(_FakeBot(), repo, CHAT_ID) is None
