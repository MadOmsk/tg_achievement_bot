"""A database opened outside the bot: the scripts and the operator's tools (#234).

`open_database` gives the repo on the schema as it stands, with no bring-up: a
script never migrates a running bot's database. `connect` gives the plain
synchronous connection the tools write their own SQL on, with the bot's
placeholders, rows and loose typing (`bot.db.postgres`). `backup` is `pg_dump`
of the server's schema and the catalog, the copy a script takes before it
writes.

The database and the schema come from the settings unless a caller names them;
a script takes `--schema` with `add_arguments`.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import os
import selectors
import subprocess
import sys
from collections.abc import Coroutine, Iterable
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.pq import TransactionStatus

from bot.config import get_settings
from bot.db.postgres import (
    Connection as AsyncConnection,
)
from bot.db.postgres import (
    _params,
    _row_factory,
    _Untyped,
    _UntypedBool,
    _UntypedDate,
    _UntypedDateTime,
    translate,
)
from bot.db.repo._games_db import GAMES


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """`--schema`, the one choice a script gives: whose database to open."""
    parser.add_argument(
        "--schema", default=None, help="the server's schema (default: DATABASE_SCHEMA)"
    )


def _target(dsn: str | None, schema: str | None) -> tuple[str, str]:
    if dsn is not None and schema is not None:
        return dsn, schema
    settings = get_settings()
    return dsn or settings.database_url, schema or settings.database_schema


def event_loop() -> asyncio.AbstractEventLoop:
    """The loop psycopg's async connection can run on: Windows' default one
    (the proactor) refuses it."""
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()


def run(main: Coroutine[Any, Any, Any]) -> Any:
    """`asyncio.run` for a script that opens the database."""
    return asyncio.run(main, loop_factory=event_loop)


async def open_database(dsn: str | None = None, *, schema: str | None = None) -> Any:
    """A `Repo` on the schema as it is: no bring-up, no migration."""
    from bot.db.repo import Database

    dsn, schema = _target(dsn, schema)
    database = Database(dsn, schema=schema)
    database._conn = await AsyncConnection.connect(dsn, search_path=f"{schema},{GAMES}")
    return database


class Cursor:
    """What a statement left, read at once, as `bot.db.postgres.Cursor`."""

    def __init__(self, rows: list[Any], rowcount: int, description: Any) -> None:
        self._rows = rows
        self._next = 0
        self.rowcount = rowcount
        self.description = description

    def fetchone(self) -> Any:
        if self._next >= len(self._rows):
            return None
        row = self._rows[self._next]
        self._next += 1
        return row

    def fetchall(self) -> list[Any]:
        rows = self._rows[self._next :]
        self._next = len(self._rows)
        return rows

    def __iter__(self) -> Cursor:
        return self

    def __next__(self) -> Any:
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row


class Connection:
    """psycopg's synchronous connection with the bot's face. Autocommit like
    the bot's: a statement is its own transaction, `begin()` opens a block."""

    def __init__(self, raw: psycopg.Connection[Any]) -> None:
        self.raw = raw

    def execute(self, sql: str, parameters: Any = None) -> Cursor:
        with self.raw.cursor() as cursor:
            cursor.execute(translate(sql), _params(parameters))
            rows = cursor.fetchall() if cursor.description is not None else []
            return Cursor(rows, cursor.rowcount, cursor.description)

    def executemany(self, sql: str, parameters: Iterable[Any]) -> None:
        rows = [_params(p) for p in parameters]
        if rows:
            with self.raw.cursor() as cursor:
                cursor.executemany(translate(sql), rows)

    @property
    def in_transaction(self) -> bool:
        return self.raw.info.transaction_status != TransactionStatus.IDLE

    def begin(self) -> None:
        self.raw.execute("BEGIN")

    def commit(self) -> None:
        status = self.raw.info.transaction_status
        if status == TransactionStatus.INERROR:
            self.raw.execute("ROLLBACK")
            raise psycopg.errors.InFailedSqlTransaction(
                "a statement failed inside this block: everything in it was rolled back"
            )
        if status == TransactionStatus.INTRANS:
            self.raw.execute("COMMIT")

    def rollback(self) -> None:
        if self.in_transaction:
            self.raw.execute("ROLLBACK")

    def close(self) -> None:
        self.raw.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def connect(
    dsn: str | None = None, *, schema: str | None = None, readonly: bool = False
) -> Connection:
    """A synchronous connection, the search path as the bot's; a read-only one
    is refused every write by the server itself."""
    dsn, schema = _target(dsn, schema)
    options = f"-c search_path={schema},{GAMES}"
    if readonly:
        options += " -c default_transaction_read_only=on"
    raw = psycopg.connect(dsn, autocommit=True, row_factory=_row_factory, options=options)
    raw.adapters.register_dumper(int, _Untyped)
    raw.adapters.register_dumper(float, _Untyped)
    raw.adapters.register_dumper(bool, _UntypedBool)
    raw.adapters.register_dumper(datetime.datetime, _UntypedDateTime)
    raw.adapters.register_dumper(datetime.date, _UntypedDate)
    return Connection(raw)


def tool_target(dsn: str) -> tuple[str, dict[str, str]]:
    """What to hand `pg_dump` or `pg_restore`: the address with no password, and
    an environment carrying it. A command line is seen by every local user, and
    is printed whole when the command fails."""
    parts = conninfo_to_dict(dsn)
    password = parts.pop("password", None)
    env = dict(os.environ)
    if password is not None:
        env["PGPASSWORD"] = str(password)
    return make_conninfo(**parts), env


def backup(
    target: Path | str,
    *,
    dsn: str | None = None,
    schema: str | None = None,
    pg_dump: str = "pg_dump",
) -> Path:
    """`pg_dump` of the server's schema and the catalog, custom format."""
    dsn, schema = _target(dsn, schema)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    address, env = tool_target(dsn)
    subprocess.run(
        [
            pg_dump,
            "--format=custom",
            f"--schema={schema}",
            f"--schema={GAMES}",
            f"--file={target}",
            f"--dbname={address}",
        ],
        check=True,
        env=env,
    )
    return target
