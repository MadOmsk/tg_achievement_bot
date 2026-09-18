"""Default Mini App chat: subscribed / recently-seen before alphabetical."""

from __future__ import annotations

from bot.db.repo import Repo

TG_ID = 1


async def test_subscribed_chat_sorts_before_seen_only(repo: Repo) -> None:
    # Alphabetical would put "Alpha test" first; subscription must win so the
    # Mini App home does not open on an empty private test chat.
    await repo.ensure_user(TG_ID, "igor")
    await repo.upsert_chat(-1001, "Alpha test", TG_ID)
    await repo.upsert_chat(-1002, "Zulu club", TG_ID)
    await repo.record_chat_seen(-1001, TG_ID)
    await repo.subscribe(-1002, TG_ID)
    await repo.record_chat_seen(-1002, TG_ID)

    chats = await repo.user_chats(TG_ID)

    assert [c.chat_id for c in chats] == [-1002, -1001]
