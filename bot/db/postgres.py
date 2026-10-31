"""PostgreSQL behind the connection the repo already speaks to (#234).

The repo was written against aiosqlite: `await conn.execute(sql, params)`
returning a cursor to `fetchone()` / `fetchall()`, rows read by name and by
position, `?` and `:name` placeholders. This module gives psycopg 3 that same
face, so moving the database moved the SQL dialect and nothing else:

* `translate` turns `?` into `%s` and `:name` into `%(name)s` — outside string
  literals, quoted names and comments, and leaving PostgreSQL's `::` casts
  alone — and doubles every `%`, a literal's too, which psycopg would
  otherwise read as a placeholder. Done once per distinct statement.
* `Row` is read as `row["column"]` and `row[0]`, iterated as its values, and
  turned into a dict by `dict(row)`, as `aiosqlite.Row` was.
* The connection runs in autocommit: a statement outside a transaction block
  is its own transaction, so a failed one leaves nothing half done behind it
  (SQLite went on after a failed statement; PostgreSQL refuses everything
  until a rollback). Blocks of writes that must land together are
  `Repo.transaction()`'s (`_tx.py`), which opens an explicit transaction.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from functools import lru_cache
from typing import Any

import psycopg
from psycopg import AsyncConnection, AsyncCursor
from psycopg.adapt import Dumper
from psycopg.pq import TransactionStatus

IntegrityError = psycopg.IntegrityError
OperationalError = psycopg.OperationalError
Error = psycopg.Error

#: Told when the server is gone. The process has one connection for its whole
#: life, and pollers log a failure and go on, so without this a restarted
#: PostgreSQL leaves a bot that looks alive and does nothing, which systemd does
#: not restart. The bot's assembly ends the process here; a new one connects.
on_connection_lost: Callable[[Exception], None] | None = None

_TOKEN = re.compile(
    r"""
    (?P<string>'(?:[^']|'')*')          # a string literal
  | (?P<ident>"(?:[^"]|"")*")           # a quoted name
  | (?P<comment>--[^\n]*)               # a line comment
  | (?P<cast>::)                        # a cast, never a named parameter
  | (?P<named>:[A-Za-z_]\w*)            # :name
  | (?P<qmark>\?)                       # ?
  | (?P<percent>%)                      # a literal percent sign
    """,
    re.VERBOSE,
)


@lru_cache(maxsize=4096)
def translate(sql: str) -> str:
    """SQLite's placeholders as psycopg's (see the module's docstring)."""

    def replace(m: re.Match[str]) -> str:
        kind = m.lastgroup
        if kind == "named":
            return f"%({m.group()[1:]})s"
        if kind == "qmark":
            return "%s"
        if kind == "percent":
            return "%%"
        # psycopg reads a % anywhere in the text, inside a literal too.
        return m.group().replace("%", "%%")

    return _TOKEN.sub(replace, sql)


class Row(Sequence[Any]):
    """A row read by column name or by position."""

    __slots__ = ("_index", "_values")

    def __init__(self, values: Sequence[Any], index: dict[str, int]) -> None:
        self._values = tuple(values)
        self._index = index

    def __getitem__(self, key: Any) -> Any:  # type: ignore[override]
        if isinstance(key, str):
            return self._values[self._index[key]]
        return self._values[key]

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._values)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Row):
            return self._values == other._values
        return self._values == other

    def __hash__(self) -> int:
        return hash(self._values)

    def __repr__(self) -> str:
        return f"Row({dict(zip(self._index, self._values, strict=False))!r})"

    def keys(self) -> list[str]:
        return list(self._index)

    def get(self, key: str, default: Any = None) -> Any:
        index = self._index.get(key)
        return default if index is None else self._values[index]


class _Untyped(Dumper):
    """A number sent with no type of its own (oid 0): the server takes the
    type of whatever it meets — a text column, a bigint — as SQLite's loose
    typing did. Strings go so by default; numbers would otherwise arrive as
    int8 / float8 and refuse `text = bigint`."""

    oid = 0

    def dump(self, obj: Any) -> bytes:
        return str(obj).encode()


class _UntypedBool(_Untyped):
    """A bool as SQLite stored it: 1 or 0 (the flags are integer columns)."""

    def dump(self, obj: Any) -> bytes:
        return b"1" if obj else b"0"


class _UntypedDateTime(_Untyped):
    """A datetime as sqlite3's adapter wrote it — ISO text with a space — and
    untyped: the columns are text, and are compared as text."""

    def dump(self, obj: Any) -> bytes:
        return obj.isoformat(" ").encode()


class _UntypedDate(_Untyped):
    def dump(self, obj: Any) -> bytes:
        return obj.isoformat().encode()


def _row_factory(cursor: Any) -> Any:
    description = cursor.description or ()
    # A name given twice reads as its first column, as sqlite3.Row did.
    index: dict[str, int] = {}
    for i, column in enumerate(description):
        index.setdefault(column.name, i)

    def make(values: Sequence[Any]) -> Row:
        return Row(values, index)

    return make


class Cursor:
    """What a statement left: its rows (already fetched) and its count.

    The rows are read when the statement runs, so nothing is left open on the
    one connection between a caller's `execute` and its `fetchall`."""

    def __init__(self, rows: list[Row], rowcount: int, description: Any) -> None:
        self._rows = rows
        self._next = 0
        self.rowcount = rowcount
        self.description = description
        # SQLite's rowid of the last insert has no PostgreSQL twin: an insert
        # that needs its new id says RETURNING and reads it as a row.
        self.lastrowid = None

    async def fetchone(self) -> Row | None:
        if self._next >= len(self._rows):
            return None
        row = self._rows[self._next]
        self._next += 1
        return row

    async def fetchall(self) -> list[Row]:
        rows = self._rows[self._next :]
        self._next = len(self._rows)
        return rows

    async def fetchmany(self, size: int) -> list[Row]:
        rows = self._rows[self._next : self._next + size]
        self._next += len(rows)
        return rows

    def __aiter__(self) -> Cursor:
        return self

    async def __anext__(self) -> Row:
        row = await self.fetchone()
        if row is None:
            raise StopAsyncIteration
        return row

    async def close(self) -> None:
        return None


async def _finish(cursor: AsyncCursor[Any]) -> Cursor:
    rows = await cursor.fetchall() if cursor.description is not None else []
    return Cursor(rows, cursor.rowcount, cursor.description)


class Connection:
    """psycopg's async connection with aiosqlite's face (see the module)."""

    def __init__(self, raw: AsyncConnection[Any]) -> None:
        self._raw = raw
        self._closing = False

    @classmethod
    async def connect(cls, dsn: str, *, search_path: str | None = None) -> Connection:
        options = f"-c search_path={search_path}" if search_path else ""
        raw = await AsyncConnection.connect(
            dsn, autocommit=True, row_factory=_row_factory, options=options
        )
        raw.adapters.register_dumper(int, _Untyped)
        raw.adapters.register_dumper(float, _Untyped)
        raw.adapters.register_dumper(bool, _UntypedBool)
        raw.adapters.register_dumper(datetime.datetime, _UntypedDateTime)
        raw.adapters.register_dumper(datetime.date, _UntypedDate)
        return cls(raw)

    @property
    def raw(self) -> AsyncConnection[Any]:
        return self._raw

    @property
    def in_transaction(self) -> bool:
        return self._raw.info.transaction_status != TransactionStatus.IDLE

    async def execute(self, sql: str, parameters: Any = None) -> Cursor:
        async with self._raw.cursor() as cursor:
            try:
                await cursor.execute(translate(sql), _params(parameters))
            except psycopg.OperationalError as exc:
                self._maybe_lost(exc)
                raise
            return await _finish(cursor)

    async def executemany(self, sql: str, parameters: Iterable[Any]) -> Cursor:
        rows = [_params(p) for p in parameters]
        async with self._raw.cursor() as cursor:
            if rows:
                try:
                    await cursor.executemany(translate(sql), rows)
                except psycopg.OperationalError as exc:
                    self._maybe_lost(exc)
                    raise
            return Cursor([], cursor.rowcount if rows else 0, None)

    async def executescript(self, script: str) -> None:
        """A script of several statements, none with parameters."""
        async with self._raw.cursor() as cursor:
            await cursor.execute(script)

    def _maybe_lost(self, exc: Exception) -> None:
        if self._raw.closed and not self._closing and on_connection_lost is not None:
            on_connection_lost(exc)

    async def begin(self) -> None:
        try:
            await self._raw.execute("BEGIN")
        except psycopg.OperationalError as exc:
            self._maybe_lost(exc)
            raise

    async def commit(self) -> None:
        status = self._raw.info.transaction_status
        if status == TransactionStatus.INERROR:
            # PostgreSQL answers COMMIT here with a rollback and no error, so a
            # failure somebody caught inside the block would lose it silently.
            await self._raw.execute("ROLLBACK")
            raise psycopg.errors.InFailedSqlTransaction(
                "a statement failed inside this block: everything in it was rolled back"
            )
        if status == TransactionStatus.INTRANS:
            try:
                await self._raw.execute("COMMIT")
            except psycopg.OperationalError as exc:
                self._maybe_lost(exc)
                raise

    async def rollback(self) -> None:
        if self._raw.info.transaction_status in (
            TransactionStatus.INTRANS,
            TransactionStatus.INERROR,
        ):
            await self._raw.execute("ROLLBACK")

    async def close(self) -> None:
        self._closing = True
        await self._raw.close()


def _params(parameters: Any) -> Any:
    # Never None: psycopg reads `%%` back as `%` only when it has parameters,
    # and `translate` has doubled every one.
    if parameters is None:
        return ()
    if isinstance(parameters, dict):
        return parameters
    return tuple(parameters)
