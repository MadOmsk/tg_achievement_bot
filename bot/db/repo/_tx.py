"""Transactions on the one shared connection (#167).

The bot has one database connection, and every coroutine writes through it.
A transaction is the connection's, not a coroutine's: one caller's
`commit()` committed whatever another had half written, and one caller's
`rollback()` threw it away — a backfill's half-written batch, later found
again by a live poll and published as new.

`Repo.transaction()` makes a block of writes one unit: while a block is open,
every other caller waits before its next statement, so nothing of theirs can
land inside it; the block's own `commit()` calls wait for its end; and an
exception (a cancellation included) rolls back exactly the block. A block
inside a block is a savepoint. Who is inside is a context variable rather
than the task, so a child task the block starts — `asyncio.wait_for`,
`gather` — counts as inside instead of waiting for its own parent.

Everything not inside a block is a statement of its own: the connection
runs in autocommit (#234), and a `commit()` outside a block has nothing to do.
"""

from __future__ import annotations

import asyncio
import contextvars
import itertools
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import Any

from bot.db.postgres import Connection, Cursor

# The block this context is inside of, if any.
_current: contextvars.ContextVar[int | None] = contextvars.ContextVar("db_tx", default=None)
_ids = itertools.count(1)


class TransactionGate:
    """Which block, if any, has the connection — one per database."""

    def __init__(self) -> None:
        self.owner: int | None = None
        self.depth = 0
        self._released = asyncio.Event()
        self._released.set()

    def mine(self) -> bool:
        return self.owner is not None and _current.get() == self.owner

    async def wait_turn(self) -> None:
        while self.owner is not None and _current.get() != self.owner:
            await self._released.wait()

    def take(self, block: int) -> None:
        self.owner = block
        self._released.clear()

    def release(self) -> None:
        self.owner = None
        self.depth = 0
        self._released.set()


class GatedConnection:
    """The connection as the repo sees it: each statement waits while somebody
    else's block is open, and a `commit()` inside a block waits for its end."""

    def __init__(self, conn: Connection, gate: TransactionGate) -> None:
        self._raw = conn
        self._gate = gate

    @property
    def in_transaction(self) -> bool:
        return self._raw.in_transaction

    async def execute(self, sql: str, parameters: Any = None) -> Cursor:
        await self._gate.wait_turn()
        if parameters is None:
            return await self._raw.execute(sql)
        return await self._raw.execute(sql, parameters)

    async def executemany(self, sql: str, parameters: Iterable[Any]) -> Cursor:
        await self._gate.wait_turn()
        return await self._raw.executemany(sql, parameters)

    async def commit(self) -> None:
        await self._gate.wait_turn()
        if self._gate.mine():
            return  # the block commits once, at its end
        await self._raw.commit()

    async def rollback(self) -> None:
        if self._gate.mine():
            # Inside a block a rollback would also undo what the block's caller
            # wrote before this; raising lets the block roll back what it owns.
            raise RuntimeError("rollback() inside Repo.transaction(); raise instead")
        await self._gate.wait_turn()
        await self._raw.rollback()

    async def close(self) -> None:
        await self._raw.close()


@asynccontextmanager
async def transaction(conn: GatedConnection) -> AsyncIterator[None]:
    gate = conn._gate
    raw = conn._raw
    if gate.mine():
        gate.depth += 1
        name = f"sp{gate.depth}"
        await raw.execute(f"SAVEPOINT {name}")
        try:
            yield
        except BaseException:
            await raw.execute(f"ROLLBACK TO {name}")
            await raw.execute(f"RELEASE {name}")
            raise
        else:
            await raw.execute(f"RELEASE {name}")
        finally:
            gate.depth -= 1
        return

    await gate.wait_turn()
    block = next(_ids)
    gate.take(block)
    token = _current.set(block)
    try:
        await raw.begin()
        try:
            yield
        except BaseException:
            await raw.rollback()
            raise
        try:
            # Deferred foreign keys are checked here, so the commit itself can
            # refuse.
            await raw.commit()
        except BaseException:
            await raw.rollback()
            raise
    finally:
        _current.reset(token)
        gate.release()
