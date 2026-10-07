"""Transactions on the one shared connection (#167, `bot/db/repo/_tx.py`)."""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

from bot.db.repo import Repo


async def _count(repo: Repo, table: str = "chats") -> int:
    cursor = await repo._conn.execute(f"SELECT COUNT(*) FROM {table}")
    return (await cursor.fetchone())[0]


async def test_a_failed_block_leaves_nothing_and_its_inner_commits_wait(repo: Repo) -> None:
    with pytest.raises(RuntimeError):
        async with repo.transaction():
            await repo.upsert_chat(-1, "One", 1)  # commits inside: deferred
            await repo.upsert_chat(-2, "Two", 1)
            raise RuntimeError("boom")
    assert await _count(repo) == 0


async def test_nobody_else_lands_inside_a_block(repo: Repo) -> None:
    """Another coroutine's write waits for the block; the block failing does
    not take it along, and it is not committed half-way through the block."""
    entered = asyncio.Event()
    release = asyncio.Event()

    async def block() -> None:
        async with repo.transaction():
            await repo.upsert_chat(-1, "Block", 1)
            entered.set()
            await release.wait()
            raise RuntimeError("block fails")

    async def other() -> None:
        await entered.wait()
        await repo.upsert_chat(-2, "Other", 1)

    task = asyncio.create_task(block())
    writer = asyncio.create_task(other())
    await entered.wait()
    await asyncio.sleep(0.05)
    assert not writer.done()  # waiting for the block
    release.set()
    with pytest.raises(RuntimeError):
        await task
    await writer
    cursor = await repo._conn.execute("SELECT chat_id FROM chats")
    assert [row[0] for row in await cursor.fetchall()] == [-2]


async def test_an_inner_block_is_a_savepoint(repo: Repo) -> None:
    async with repo.transaction():
        await repo.upsert_chat(-1, "Kept", 1)
        with pytest.raises(sqlite3.IntegrityError):
            async with repo.transaction():
                await repo.upsert_chat(-2, "Dropped", 1)
                raise sqlite3.IntegrityError("clash")
    cursor = await repo._conn.execute("SELECT chat_id FROM chats")
    assert [row[0] for row in await cursor.fetchall()] == [-1]


async def test_a_child_task_inside_a_block_is_inside_it(repo: Repo) -> None:
    async with repo.transaction():
        await asyncio.wait_for(repo.upsert_chat(-1, "Child", 1), timeout=2)
    assert await _count(repo) == 1


async def test_a_cancelled_block_rolls_back_and_frees_the_connection(repo: Repo) -> None:
    started = asyncio.Event()

    async def block() -> None:
        async with repo.transaction():
            await repo.upsert_chat(-1, "Cancelled", 1)
            started.set()
            await asyncio.sleep(10)

    task = asyncio.create_task(block())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(repo.upsert_chat(-2, "After", 1), timeout=2)
    cursor = await repo._conn.execute("SELECT chat_id FROM chats")
    assert [row[0] for row in await cursor.fetchall()] == [-2]


async def test_a_taken_nickname_no_longer_throws_away_other_writes(repo: Repo) -> None:
    """The review's case: `_store_handle` called `rollback()` on a clash, which
    discarded whatever another coroutine had written and not yet committed."""
    await repo.ensure_user(1, "alice")
    await repo.ensure_user(2, "bobby")
    other = await repo.person_id(2)
    # Somebody's write, run but not yet committed.
    await repo._conn.execute(
        "INSERT INTO chats (chat_id, title, created_at, is_active) "
        "VALUES (-5, 'pending', '2026-10-06', 1)"
    )
    stored = await repo._store_handle(other, "alice", 0, confirmed=True, changed=True)
    assert stored is False
    assert await _count(repo) == 1
