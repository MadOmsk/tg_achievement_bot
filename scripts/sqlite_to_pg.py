"""A server's SQLite files carried into PostgreSQL, once, at the switch (#234).

    python -X utf8 -m scripts.sqlite_to_pg bring-up --db COPY.db [--games COPY.games.db] --out DIR
    python -X utf8 -m scripts.sqlite_to_pg preflight --db COPY.db [--games COPY.games.db] --dsn DSN
    python -X utf8 -m scripts.sqlite_to_pg import --db COPY.db --schema prod --dsn DSN [--dry-run]
    python -X utf8 -m scripts.sqlite_to_pg verify --db COPY.db --schema prod --dsn DSN

`DATABASE_URL` stands in for `--dsn`, which keeps a password off the command
line. The source is opened read-only: a server's database, and its catalog from
the file `app_settings.games_db_path` names (`--games` when the copy lives
elsewhere), or from the same file when it names none, as on the dev server.

- **Preflight** always runs before an import: what PostgreSQL would refuse, or
  what would be lost. A real problem stops the import unless `--accept-problems`
  says what to do about each (see `ACCEPTED`), and `verify` then needs the flag
  too, to compare against the data as repaired. The dates' three forms are only
  counted: date columns are text and stay as they are.
- **Import** fills one server's schema and `games` in one transaction: an
  empty schema or nothing. The schemas are made from `bot/db/pg/*.sql` when they
  have no tables; a schema with rows in any table is refused. Foreign keys are
  checked before the commit.
- **`games` already filled** is the second server on the shared catalog (#229).
  The same file: skipped. A file with nothing the catalog lacks: skipped, said
  so. Otherwise it is refused with the counts, or with `--merge-catalog` what
  only this server knew is added by the rules `games_db.py join` had: rows of
  `MERGED` tables where there is none, a kept stand-in with what points at it for
  a list no version stands for, unlinked and then linked into a game. Everything
  else (games, labels, series) gives way to the catalog already there.
- **Catalog ids the server's own tables hold** (`favorite_games.game_id`,
  `pass_items.game_id`) are mapped through the games' versions whenever the
  catalog is not the same file: its ids are not the source's. A favorite of a
  game the catalog does not have is dropped, a prize's link cleared (its title
  stays): an id that names another game would be worse.
- **`app_settings.games_db_path` is not carried**: it names a file only SQLite
  could attach, and nothing on PostgreSQL reads it.

Nothing here prints a value of a row: counts, table and column names, numeric
keys at most. PostgreSQL's own messages quote rows, so only the code and the
names in its diagnostics are shown.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import struct
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

from bot.db.repo._games_db import CATALOG_TABLES, GAMES, GAMES_DB_KEY

_DB_DIR = Path(__file__).resolve().parent.parent / "bot" / "db"
APP_SQL = _DB_DIR / "pg" / "app.sql"
GAMES_SQL = _DB_DIR / "pg" / "games.sql"
PG_MIGRATIONS = _DB_DIR / "pg" / "migrations"
SQLITE_MIGRATIONS = _DB_DIR / "migrations"

SERVER = "server"  # the attached server's file, in the source's connection
_PROBE_APP, _PROBE_GAMES = "_transfer_probe_app", "_transfer_probe_games"
_SAFE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")
_IMPORT_LOCK = 234_234
_BATCH = 2000

# What a merging server adds where the catalog has no row: facts about a list
# or a store's answer, the same whoever learned them. Not `fetch_state`: its
# "asked, next due then" would stand for answers that give way to the catalog's,
# which would then not ask again until then.
MERGED = (
    "achievement_list_connectors",
    "title_groups",
    "title_achievements",
    "steam_schema_cache",
    "steam_rarity_cache",
    "steam_apps",
    "title_guide_reads",
    "game_patches",
    "guide_channels",
    "guide_videos",
    "guide_marks",
    "hltb_entries",
    "hltb_platform_times",
    "hltb_platform_groups",
    "hltb_entry_platforms",
    "hltb_review_scores",
    "hltb_related",
    "source_payloads",
)
# An HLTB entry's rows of its own: taken only for an entry the catalog did not
# have, never mixed into one it reads from a newer page.
HLTB_CHILDREN = frozenset(
    {
        "hltb_platform_times",
        "hltb_platform_groups",
        "hltb_entry_platforms",
        "hltb_review_scores",
        "hltb_related",
    }
)
ACCEPTED = {
    "text_in_numeric": "a number written as text is read as the number; other text becomes NULL",
    "real_in_integer": "a fractional value in an integer column becomes NULL",
    "blob_in_numeric": "bytes in a number column become NULL",
    "blob_in_text": "bytes in a text column are read as text, as below",
    "text_in_bytes": "text in a bytes column is kept as its UTF-8 bytes",
    "nul_in_text": "\\0 is taken out of the text",
    "broken_utf8": "undecodable bytes become U+FFFD",
    "orphan": "the row goes (ON DELETE SET NULL: the reference goes), and what hung on it",
    "source_only_table": "the table is left behind",
    "source_only_column": "the column is left behind",
    "catalog_also_in_main": "the rows beside the games file are left behind",
}
# Nothing a flag can answer: there is no value to put there. A migration the
# source never ran may have filled a table (141 made the chats' admins), which
# no schema file brings: the source is brought up first.
UNFIXABLE = frozenset({"null_in_not_null", "required_column_missing", "migrations_missing"})


class TransferError(Exception):
    """A refusal, in words safe to print."""


# ---------------------------------------------------------------- the target


@dataclass
class Column:
    name: str
    kind: str  # int / float / text / bytes
    nullable: bool
    generated: bool
    identity: bool
    has_default: bool


@dataclass
class ForeignKey:
    columns: list[str]
    parent: str
    parent_columns: list[str]
    set_null: bool


@dataclass
class Table:
    schema: str
    name: str
    columns: dict[str, Column] = field(default_factory=dict)
    pk: list[str] = field(default_factory=list)
    fks: list[ForeignKey] = field(default_factory=list)

    @property
    def ident(self) -> sql.Composed:
        return sql.Identifier(self.schema, self.name)


_KINDS = {
    "bigint": "int",
    "integer": "int",
    "smallint": "int",
    "double precision": "float",
    "real": "float",
    "text": "text",
    "bytea": "bytes",
}


def read_plan(pg: psycopg.Connection, schema: str) -> dict[str, Table]:
    """The tables of `schema` as PostgreSQL has them."""
    tables: dict[str, Table] = {}
    rows = pg.execute(
        "SELECT table_name, column_name, data_type, is_nullable, is_generated, is_identity,"
        " column_default FROM information_schema.columns WHERE table_schema = %s"
        " ORDER BY table_name, ordinal_position",
        (schema,),
    ).fetchall()
    for name, column, data_type, nullable, generated, identity, default in rows:
        if data_type not in _KINDS:
            raise TransferError(f"{name}.{column}: a type this tool does not know: {data_type}")
        tables.setdefault(name, Table(schema, name)).columns[column] = Column(
            column,
            _KINDS[data_type],
            nullable == "YES",
            generated == "ALWAYS",
            identity == "YES",
            default is not None or identity == "YES",
        )
    rows = pg.execute(
        """
        SELECT cl.relname::text, c.contype::text, c.confdeltype::text, pf.relname::text,
               (SELECT array_agg(a.attname::text ORDER BY k.ord)
                  FROM unnest(c.conkey) WITH ORDINALITY k(n, ord)
                  JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.n),
               (SELECT array_agg(a.attname::text ORDER BY k.ord)
                  FROM unnest(c.confkey) WITH ORDINALITY k(n, ord)
                  JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.n)
          FROM pg_constraint c
          JOIN pg_class cl ON cl.oid = c.conrelid
          JOIN pg_namespace ns ON ns.oid = cl.relnamespace
          LEFT JOIN pg_class pf ON pf.oid = c.confrelid
         WHERE ns.nspname = %s AND c.contype IN ('p', 'f')
        """,
        (schema,),
    ).fetchall()
    for name, kind, on_delete, parent, columns, parent_columns in rows:
        if kind == "p":
            tables[name].pk = columns
        else:
            tables[name].fks.append(ForeignKey(columns, parent, parent_columns, on_delete == "n"))
    return tables


def _make_schema(pg: psycopg.Connection, schema: str, script: Path, path_tail: str) -> None:
    pg.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
    pg.execute(
        sql.SQL("SET LOCAL search_path TO {}, {}").format(
            sql.Identifier(schema), sql.Identifier(path_tail)
        )
    )
    pg.execute(script.read_text(encoding="utf-8"))  # type: ignore[arg-type]


def _has_tables(pg: psycopg.Connection, schema: str) -> bool:
    row = pg.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = %s LIMIT 1", (schema,)
    ).fetchone()
    return row is not None


def _probe_plan(pg: psycopg.Connection) -> tuple[dict[str, Table], dict[str, Table]]:
    """What the schema files make, read in a transaction that never lands."""
    _make_schema(pg, _PROBE_GAMES, GAMES_SQL, _PROBE_GAMES)
    _make_schema(pg, _PROBE_APP, APP_SQL, _PROBE_GAMES)
    app, catalog = read_plan(pg, _PROBE_APP), read_plan(pg, _PROBE_GAMES)
    pg.rollback()
    return app, catalog


def _filled(pg: psycopg.Connection, plan: dict[str, Table]) -> list[str]:
    return [
        name
        for name, table in sorted(plan.items())
        if pg.execute(sql.SQL("SELECT 1 FROM {} LIMIT 1").format(table.ident)).fetchone()
    ]


def _say_refusal(exc: psycopg.Error, where: str) -> TransferError:
    """PostgreSQL's words quote rows (a key, a whole failing row): only its
    code and the names it gives are safe."""
    diag = exc.diag
    names = ", ".join(
        f"{label} {value}"
        for label, value in (
            ("table", diag.table_name),
            ("column", diag.column_name),
            ("constraint", diag.constraint_name),
        )
        if value
    )
    return TransferError(f"{where}: PostgreSQL refused it: {diag.sqlstate} {names}".rstrip())


# ---------------------------------------------------------------- the source


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class Source:
    """The SQLite side, read-only: a table is found where it lives."""

    def __init__(self, db: Path, games: Path | None = None) -> None:
        if not db.exists():
            raise TransferError(f"{db} not found")
        # The connection's own database is memory, for the temporary tables of
        # `plan_repairs`, which a read-only connection refuses; the files are
        # attached read-only, so nothing here can write them.
        self.conn = sqlite3.connect(":memory:", uri=True)
        self.conn.text_factory = bytes
        self.conn.execute(f"ATTACH DATABASE ? AS {SERVER}", (f"{db.resolve().as_uri()}?mode=ro",))
        self.games_file: Path | None = None
        named = self._named_games_file()
        if games is None and named is not None:
            games = Path(named)
        if games is not None:
            if not games.exists():
                raise TransferError(
                    f"{db.name} keeps its catalog in {games}, not found: --games names the copy"
                )
            self.games_file = games
            self.conn.execute(
                f"ATTACH DATABASE ? AS {GAMES}", (f"{games.resolve().as_uri()}?mode=ro",)
            )
        self.main_tables = self._tables(SERVER)
        self.games_tables = self._tables(GAMES) if self.games_file else set()
        self._columns: dict[str, dict[str, bool]] = {}

    def _named_games_file(self) -> str | None:
        try:
            row = self.conn.execute(
                f"SELECT value FROM {SERVER}.app_settings WHERE key = ?", (GAMES_DB_KEY,)
            ).fetchone()
        except sqlite3.OperationalError:  # no app_settings: a bare file
            return None
        return row[0].decode() if row and row[0] else None

    def _tables(self, schema: str) -> set[str]:
        rows = self.conn.execute(
            f"SELECT name FROM {schema}.sqlite_master WHERE type = 'table'"
            " AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\'"
        ).fetchall()
        return {r[0].decode() for r in rows}

    def where(self, table: str) -> str | None:
        if table in CATALOG_TABLES and table in self.games_tables:
            return GAMES
        return SERVER if table in self.main_tables else None

    def ref(self, table: str) -> str:
        return f"{self.where(table)}.{_q(table)}"

    def columns(self, table: str) -> dict[str, bool]:
        """Its column names, each saying whether it is generated."""
        if table not in self._columns:
            schema = self.where(table)
            if schema is None:
                self._columns[table] = {}
            else:
                rows = self.conn.execute(f"PRAGMA {schema}.table_xinfo({_q(table)})").fetchall()
                self._columns[table] = {r[1].decode(): r[6] in (2, 3) for r in rows if r[6] != 1}
        return self._columns[table]

    def close(self) -> None:
        self.conn.close()


@dataclass
class Repairs:
    """What `--accept-problems` does to rows as they are read."""

    accept: bool = False
    # table -> SQL that says a row goes
    drop: dict[str, str] = field(default_factory=dict)
    # (table, column) -> SQL that says the reference goes
    clear: dict[tuple[str, str], str] = field(default_factory=dict)

    def clear_for(self, table: str) -> set[str]:
        return {column for t, column in self.clear if t == table}


def _int(value: Any, accept: bool) -> int | None:
    if value is None or isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
    elif accept:
        try:
            return int(value.decode("utf-8", "replace").strip())
        except ValueError:
            return None
    if accept:
        return None
    raise ValueError


def _float(value: Any, accept: bool) -> float | None:
    if value is None or isinstance(value, float):
        return value
    if isinstance(value, int):
        return float(value)
    if accept:
        try:
            return float(value.decode("utf-8", "replace").strip())
        except ValueError:
            return None
    raise ValueError


def _text(value: Any, accept: bool) -> str | None:
    if value is None:
        return None
    if not isinstance(value, bytes):
        return str(value)
    if accept:
        return value.decode("utf-8", "replace").replace("\0", "")
    text = value.decode("utf-8")
    if "\0" in text:
        raise ValueError
    return text


def _bytes(value: Any, accept: bool) -> bytes | None:
    if value is None or isinstance(value, bytes):
        return value
    raise ValueError


_CONVERT: dict[str, Callable[[Any, bool], Any]] = {
    "int": _int,
    "float": _float,
    "text": _text,
    "bytes": _bytes,
}


def _is_seq(table: Table, column: str, src: Source) -> bool:
    """The order rows came in, SQLite's rowid (`title_achievements`,
    `edition_items`, `account_links`): the platform's own order of a list."""
    return (
        column == "seq" and table.columns[column].identity and column not in src.columns(table.name)
    )


def insert_columns(table: Table, src: Source) -> list[str]:
    """What an import writes: never a generated column; a column the source
    does not have takes its default."""
    theirs = src.columns(table.name)
    return [
        c.name
        for c in table.columns.values()
        if not c.generated and (c.name in theirs or _is_seq(table, c.name, src))
    ]


def compared_columns(table: Table, src: Source) -> list[str]:
    """What `verify` compares: a generated column too, where both engines have
    one — its two definitions must agree."""
    written = set(insert_columns(table, src))
    theirs = src.columns(table.name)
    return [c for c in table.columns if c in written or (c in theirs)]


def read_rows(
    src: Source, table: Table, columns: list[str], repairs: Repairs
) -> Iterator[tuple[Any, ...]]:
    """Rows as PostgreSQL will hold them: each value of its column's kind."""
    if src.where(table.name) is None:
        return
    exprs = []
    for name in columns:
        if _is_seq(table, name, src):
            exprs.append("rowid")
        elif name in repairs.clear_for(table.name):
            exprs.append(
                f"CASE WHEN {repairs.clear[(table.name, name)]} THEN NULL ELSE {_q(name)} END"
            )
        else:
            exprs.append(_q(name))
    query = f"SELECT {', '.join(exprs)} FROM {src.ref(table.name)} AS t"
    conditions = []
    if table.name == "app_settings":
        conditions.append(f"key <> '{GAMES_DB_KEY}'")
    if table.name in repairs.drop:
        conditions.append(f"NOT ({repairs.drop[table.name]})")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    if any(_is_seq(table, c, src) for c in table.columns):
        query += " ORDER BY rowid"
    converts = [_CONVERT[table.columns[c].kind] for c in columns]
    cursor = src.conn.execute(query)
    while batch := cursor.fetchmany(_BATCH):
        for row in batch:
            try:
                yield tuple(
                    convert(value, repairs.accept)
                    for convert, value in zip(converts, row, strict=True)
                )
            except ValueError:
                # The value itself stays out of the message.
                raise TransferError(
                    f"{table.name}: a value does not fit its column: run preflight"
                ) from None


# ---------------------------------------------------------------- preflight


@dataclass
class Finding:
    kind: str
    table: str
    column: str = ""
    count: int = 1


@dataclass
class Preflight:
    problems: list[Finding] = field(default_factory=list)
    dates: Counter[str] = field(default_factory=Counter)
    schema_notes: list[str] = field(default_factory=list)

    def add(self, kind: str, table: str, column: str = "", count: int = 1) -> None:
        if count:
            self.problems.append(Finding(kind, table, column, count))

    @property
    def unfixable(self) -> list[Finding]:
        return [p for p in self.problems if p.kind in UNFIXABLE]


_DATE_BUCKETS = (
    ("iso_offset (2026-10-31T12:00:00+00:00)", "'????-??-??T*[+-]??:??'"),
    ("iso_z (2026-10-31T12:00:00Z)", "'????-??-??T*Z'"),
    ("iso_bare (2026-10-31T12:00:00)", "'????-??-??T*'"),
    ("sqlite (2026-10-31 12:00:00)", "'????-??-?? *'"),
    ("day (2026-10-31)", "'????-??-??'"),
)


def _is_date_column(column: Column) -> bool:
    return column.kind == "text" and (column.name.endswith("_at") or "date" in column.name)


def _census(src: Source, table: Table, report: Preflight) -> None:
    """Value types, NULLs and date forms, one scan of the table."""
    theirs = src.columns(table.name)
    probes: list[tuple[str, Column | None, str]] = []
    for name, column in table.columns.items():
        if name not in theirs or theirs[name]:
            continue
        q = _q(name)
        if column.kind in ("int", "float"):
            probes.append(("text_in_numeric", column, f"typeof({q}) = 'text'"))
            probes.append(("blob_in_numeric", column, f"typeof({q}) = 'blob'"))
        if column.kind == "int":
            probes.append(
                ("real_in_integer", column, f"typeof({q}) = 'real' AND {q} <> CAST({q} AS INTEGER)")
            )
        if column.kind == "text":
            probes.append(("blob_in_text", column, f"typeof({q}) = 'blob'"))
        if column.kind == "bytes":
            probes.append(("text_in_bytes", column, f"typeof({q}) = 'text'"))
        if not column.nullable:
            probes.append(("null_in_not_null", column, f"{q} IS NULL"))
        if _is_date_column(column):
            cases = " ".join(
                f"WHEN {q} GLOB {pattern} THEN {i}" for i, (_, pattern) in enumerate(_DATE_BUCKETS)
            )
            for i, (label, _) in enumerate(_DATE_BUCKETS):
                probes.append((f"date:{label}", None, f"(CASE {cases} END) = {i}"))
            probes.append(
                (
                    "date:other",
                    None,
                    f"{q} IS NOT NULL AND (CASE {cases} ELSE -1 END) = -1",
                )
            )
    if not probes:
        return
    # SQLite takes at most so many result columns; a chunk is a scan.
    for start in range(0, len(probes), 500):
        chunk = probes[start : start + 500]
        select = ", ".join(f"COALESCE(SUM({expr}), 0)" for _, _, expr in chunk)
        counts = src.conn.execute(f"SELECT {select} FROM {src.ref(table.name)}").fetchone()
        for (kind, column, _), count in zip(chunk, counts, strict=True):
            if kind.startswith("date:"):
                report.dates[kind[5:]] += count
            elif column is not None:
                report.add(kind, table.name, column.name, count)


def _scan_text(src: Source, table: Table, report: Preflight) -> None:
    """Broken UTF-8 and \\0: only reading each value tells."""
    theirs = src.columns(table.name)
    names = [
        c.name
        for c in table.columns.values()
        if c.kind == "text" and c.name in theirs and not theirs[c.name]
    ]
    if not names:
        return
    broken: Counter[str] = Counter()
    nul: Counter[str] = Counter()
    cursor = src.conn.execute(
        f"SELECT {', '.join(_q(n) for n in names)} FROM {src.ref(table.name)}"
    )
    while batch := cursor.fetchmany(_BATCH):
        for row in batch:
            for name, value in zip(names, row, strict=True):
                if not isinstance(value, bytes):
                    continue
                if b"\0" in value:
                    nul[name] += 1
                try:
                    value.decode("utf-8")
                except UnicodeDecodeError:
                    broken[name] += 1
    for name, count in nul.items():
        report.add("nul_in_text", table.name, name, count)
    for name, count in broken.items():
        report.add("broken_utf8", table.name, name, count)


def _fk_condition(fk: ForeignKey, src: Source, alias: str, parent_filter: str = "") -> str:
    """SQL, inside a query on the child as `alias`: the row's reference is set
    and its parent is not there (MATCH SIMPLE: any NULL means no reference)."""
    set_ = " AND ".join(f"{alias}.{_q(c)} IS NOT NULL" for c in fk.columns)
    match = " AND ".join(
        f"p.{_q(pc)} = {alias}.{_q(c)}" for c, pc in zip(fk.columns, fk.parent_columns, strict=True)
    )
    parent = src.ref(fk.parent)
    return f"({set_} AND NOT EXISTS (SELECT 1 FROM {parent} p WHERE {match}{parent_filter}))"


def _usable_fks(table: Table, src: Source) -> Iterable[ForeignKey]:
    if src.where(table.name) is None:
        return
    for fk in table.fks:
        if src.where(fk.parent) is None:
            continue  # the source has no such table at all: reported on its own
        theirs = src.columns(table.name)
        parents = src.columns(fk.parent)
        if all(c in theirs for c in fk.columns) and all(c in parents for c in fk.parent_columns):
            yield fk


def preflight(src: Source, app: dict[str, Table], catalog: dict[str, Table]) -> Preflight:
    report = Preflight()
    known = set(app) | set(catalog)
    for extra in sorted((src.main_tables | src.games_tables) - known):
        schema = GAMES if extra in src.games_tables else SERVER
        count = src.conn.execute(f"SELECT COUNT(*) FROM {schema}.{_q(extra)}").fetchone()[0]
        report.add("source_only_table", extra, count=max(count, 1))
    if src.games_file is not None:
        for table in sorted(src.main_tables & set(catalog)):
            count = src.conn.execute(f"SELECT COUNT(*) FROM {SERVER}.{_q(table)}").fetchone()[0]
            report.add("catalog_also_in_main", table, count=count)
    applied = {
        r[0].decode()
        for r in (
            src.conn.execute(f"SELECT version FROM {SERVER}.schema_migrations").fetchall()
            if "schema_migrations" in src.main_tables
            else []
        )
    }
    missing = {p.stem for p in SQLITE_MIGRATIONS.glob("*.sql")} - applied
    report.add("migrations_missing", "schema_migrations", count=len(missing))

    if set(catalog) != set(CATALOG_TABLES):
        report.schema_notes.append(
            "CATALOG_TABLES and games.sql disagree: "
            + ", ".join(sorted(set(catalog) ^ set(CATALOG_TABLES)))
        )
    for plan in (app, catalog):
        for name, table in sorted(plan.items()):
            theirs = src.columns(name)
            if not theirs:
                report.schema_notes.append(f"{name}: no such table in the source")
                continue
            for column in sorted(set(theirs) - set(table.columns)):
                report.add("source_only_column", name, column)
            for column in table.columns.values():
                if (
                    column.name not in theirs
                    and not column.nullable
                    and not column.has_default
                    and not column.generated
                ):
                    report.add("required_column_missing", name, column.name)
            _census(src, table, report)
            _scan_text(src, table, report)
            for fk in _usable_fks(table, src):
                count = src.conn.execute(
                    f"SELECT COUNT(*) FROM {src.ref(name)} t WHERE {_fk_condition(fk, src, 't')}"
                ).fetchone()[0]
                report.add("orphan", name, ",".join(fk.columns), count)
    return report


def print_preflight(report: Preflight, accept: bool) -> None:
    print("preflight:")
    for note in report.schema_notes:
        print(f"  note: {note}")
    if report.problems:
        for p in report.problems:
            where = f"{p.table}.{p.column}" if p.column else p.table
            print(f"  {p.kind:24} {where:48} {p.count}")
        if accept:
            for kind in sorted({p.kind for p in report.problems} - UNFIXABLE):
                print(f"  accepted {kind}: {ACCEPTED[kind]}")
    else:
        print("  no problems")
    print("  date forms (counted only, kept as they are):")
    for label, count in sorted(report.dates.items()):
        print(f"    {label:44} {count}")


def plan_repairs(
    src: Source, plans: Iterable[dict[str, Table]], report: Preflight, accept: bool
) -> Repairs:
    """Orphans under `--accept-problems`: which rows go, which references are
    cleared, to the point where nothing is left hanging. Worked out in temporary
    tables of the keys that go, since dropping a row may orphan another."""
    repairs = Repairs(accept=accept)
    if not accept or not any(p.kind == "orphan" for p in report.problems):
        return repairs
    tables = {name: table for plan in plans for name, table in plan.items()}
    with_fks = [
        (t, list(_usable_fks(t, src))) for t in tables.values() if src.where(t.name) is not None
    ]

    # Every table anything could go from gets its table of doomed keys. It
    # needs a key to name a row by; every table here has one but the three
    # with no primary key, which nothing refers to.
    def key_of(table: Table) -> list[str]:
        return table.pk or list(src.columns(table.name))

    def doomed(name: str) -> str:
        return f"temp.{_q('gone_' + name)}"

    for table in tables.values():
        if src.where(table.name) is None:
            continue
        key = ", ".join(_q(c) for c in key_of(table))
        src.conn.execute(
            f"CREATE TEMP TABLE {_q('gone_' + table.name)} AS"
            f" SELECT {key} FROM {src.ref(table.name)} WHERE 0"
        )

    def parent_alive(fk: ForeignKey) -> str:
        parent = tables[fk.parent]
        match = " AND ".join(f"d.{_q(c)} IS p.{_q(c)}" for c in key_of(parent))
        return f" AND NOT EXISTS (SELECT 1 FROM {doomed(fk.parent)} d WHERE {match})"

    while True:
        moved = 0
        for table, fks in with_fks:
            for fk in fks:
                if fk.set_null and len(fk.columns) == 1:
                    continue
                key = ", ".join(f"t.{_q(c)}" for c in key_of(table))
                gone_match = " AND ".join(f"d.{_q(c)} IS t.{_q(c)}" for c in key_of(table))
                condition = _fk_condition(fk, src, "t", parent_alive(fk))
                cursor = src.conn.execute(
                    f"INSERT INTO {doomed(table.name)} SELECT {key}"
                    f" FROM {src.ref(table.name)} t WHERE {condition}"
                    f" AND NOT EXISTS (SELECT 1 FROM {doomed(table.name)} d WHERE {gone_match})"
                )
                moved += max(cursor.rowcount, 0)
        if not moved:
            break
    src.conn.commit()

    for table, fks in with_fks:
        count = src.conn.execute(f"SELECT COUNT(*) FROM {doomed(table.name)}").fetchone()[0]
        if count:
            match = " AND ".join(f"d.{_q(c)} IS t.{_q(c)}" for c in key_of(table))
            repairs.drop[table.name] = (
                f"EXISTS (SELECT 1 FROM {doomed(table.name)} d WHERE {match})"
            )
        for fk in fks:
            if fk.set_null and len(fk.columns) == 1:
                repairs.clear[(table.name, fk.columns[0])] = _fk_condition(
                    fk, src, "t", parent_alive(fk)
                )
    return repairs


# ---------------------------------------------------------------- digests


def _cell(value: Any) -> bytes:
    """One value's canonical bytes, the same whichever engine it came from:
    `read_rows` has already given it the kind PostgreSQL holds it as."""
    if value is None:
        return b"\xff"
    if isinstance(value, str):
        data = value.encode("utf-8")
        return b"s" + len(data).to_bytes(8, "big") + data
    if isinstance(value, int):
        return b"i%d;" % value
    if isinstance(value, float):
        return b"f" + struct.pack(">d", value)
    data = bytes(value)
    return b"b" + len(data).to_bytes(8, "big") + data


_MASK = (1 << 128) - 1


def _row_hash(row: tuple[Any, ...]) -> int:
    digest = hashlib.blake2b(digest_size=16)
    for value in row:
        digest.update(_cell(value))
    return int.from_bytes(digest.digest(), "big")


def _digest(rows: Iterable[tuple[Any, ...]]) -> tuple[int, int]:
    """Count and a sum of the rows' hashes: no order to agree on, which the
    two engines would not (their text collations differ), and a changed, lost
    or extra row changes it."""
    count = total = 0
    for row in rows:
        count += 1
        total = (total + _row_hash(row)) & _MASK
    return count, total


def pg_rows(
    pg: psycopg.Connection, table: Table, columns: list[str], where: sql.Composable | None = None
) -> Iterator[tuple[Any, ...]]:
    query = sql.SQL("SELECT {} FROM {}").format(
        sql.SQL(", ").join(map(sql.Identifier, columns)), table.ident
    )
    if where is not None:
        query = sql.SQL("{} WHERE {}").format(query, where)
    with pg.cursor(name=f"read_{table.name}") as cursor:
        cursor.itersize = _BATCH
        cursor.execute(query)
        for row in cursor:
            yield tuple(row)


def _extra_migrations_filter(table: Table) -> sql.Composable | None:
    """PostgreSQL's own migrations, recorded by the import, are not the source's."""
    if table.name != "schema_migrations":
        return None
    return sql.SQL("version <> ALL({})").format(sql.Literal(_pg_migrations()))


def _pg_migrations() -> list[str]:
    return sorted(p.stem for p in PG_MIGRATIONS.glob("*.sql"))


def _difference(
    source_rows: Iterable[tuple[Any, ...]],
    target_rows: Iterable[tuple[Any, ...]],
    table: Table,
    columns: list[str],
) -> str:
    """Which rows and columns differ, in words safe to print."""
    key_at = [columns.index(c) for c in table.pk if c in columns]

    def cells(row: tuple[Any, ...]) -> list[int]:
        return [hash(_cell(v)) for v in row]

    def keyed(rows: Iterable[tuple[Any, ...]]) -> dict[Any, list[int]]:
        out: dict[Any, list[int]] = {}
        for row in rows:
            key = tuple(row[i] for i in key_at) if key_at else _row_hash(row)
            out[key] = cells(row)
        return out

    ours, theirs = keyed(source_rows), keyed(target_rows)
    differing: Counter[str] = Counter()
    changed = []
    for key in ours.keys() & theirs.keys():
        if ours[key] != theirs[key]:
            changed.append(key)
            for name, a, b in zip(columns, ours[key], theirs[key], strict=True):
                if a != b:
                    differing[name] += 1
    only_source = ours.keys() - theirs.keys()
    only_target = theirs.keys() - ours.keys()
    numeric = [k for k in changed if isinstance(k, tuple) and all(isinstance(v, int) for v in k)]
    parts = [f"only in the source {len(only_source)}", f"only in the target {len(only_target)}"]
    parts.append(f"changed {len(changed)}")
    if differing:
        parts.append("columns " + ", ".join(f"{c} ({n})" for c, n in differing.most_common()))
    if numeric:
        parts.append(f"e.g. keys {sorted(numeric)[:5]}")
    return "; ".join(parts)


def compare_table(
    src: Source,
    pg: psycopg.Connection,
    table: Table,
    repairs: Repairs,
    source_of: Callable[[list[str]], Iterable[tuple[Any, ...]]] | None = None,
    skip: tuple[str, ...] = (),
) -> tuple[int, int, str | None]:
    """(source rows, target rows, what differs or None)."""
    columns = [c for c in compared_columns(table, src) if c not in skip]
    where = _extra_migrations_filter(table)

    def source(cols: list[str]) -> Iterable[tuple[Any, ...]]:
        return source_of(cols) if source_of else read_rows(src, table, cols, repairs)

    ours_count, ours = _digest(source(columns))
    theirs_count, theirs = _digest(pg_rows(pg, table, columns, where))
    if ours_count == theirs_count and ours == theirs:
        return ours_count, theirs_count, None
    detail = _difference(source(columns), pg_rows(pg, table, columns, where), table, columns)
    return ours_count, theirs_count, detail


# ---------------------------------------------------------------- the catalog


@dataclass
class CatalogLack:
    """What the source knows that `games` has not."""

    rows: dict[str, int] = field(default_factory=dict)
    stand_ins: int = 0

    @property
    def nothing(self) -> bool:
        return not self.stand_ins and not any(self.rows.values())


def _target_keys(pg: psycopg.Connection, table: Table) -> set[tuple[Any, ...]]:
    query = sql.SQL("SELECT {} FROM {}").format(
        sql.SQL(", ").join(map(sql.Identifier, table.pk)), table.ident
    )
    return {tuple(r) for r in pg.execute(query).fetchall()}


def _missing_rows(
    src: Source,
    table: Table,
    columns: list[str],
    repairs: Repairs,
    target_keys: set[tuple[Any, ...]],
    shared_hltb: set[int],
) -> Iterator[tuple[Any, ...]]:
    """Rows of a `MERGED` table the catalog has no row for."""
    at = [columns.index(c) for c in table.pk]
    hltb_at = columns.index("hltb_id") if table.name in HLTB_CHILDREN else None
    for row in read_rows(src, table, columns, repairs):
        if tuple(row[i] for i in at) in target_keys:
            continue
        if hltb_at is not None and row[hltb_at] in shared_hltb:
            continue
        yield row


def _shared_hltb(pg: psycopg.Connection) -> set[int]:
    return {r[0] for r in pg.execute(f"SELECT hltb_id FROM {GAMES}.hltb_entries").fetchall()}


def _stand_ins(
    src: Source, catalog: dict[str, Table], pg: psycopg.Connection, repairs: Repairs
) -> Iterator[dict[str, Any]]:
    """This source's versions of lists no version in the catalog stands for."""
    if src.where("versions") is None:
        return
    table = catalog["versions"]
    theirs = {
        tuple(r)
        for r in pg.execute(
            f"SELECT platform, title_id FROM {GAMES}.versions WHERE platform IS NOT NULL"
        ).fetchall()
    }
    columns = insert_columns(table, src)
    for values in read_rows(src, table, columns, repairs):
        row = dict(zip(columns, values, strict=True))
        if row["platform"] is not None and (row["platform"], row["title_id"]) not in theirs:
            yield row


def catalog_lack(
    src: Source, catalog: dict[str, Table], pg: psycopg.Connection, repairs: Repairs
) -> CatalogLack:
    lack = CatalogLack()
    shared_hltb = _shared_hltb(pg)
    for name in MERGED:
        table = catalog[name]
        keys = _target_keys(pg, table)
        columns = [c for c in insert_columns(table, src) if c in table.pk or c == "hltb_id"]
        if src.where(name) is None:
            continue
        lack.rows[name] = sum(
            1 for _ in _missing_rows(src, table, columns, repairs, keys, shared_hltb)
        )
    # A product the catalog holds under another list has nothing more to give.
    products = {
        (r[0], r[1], r[2]): r[3]
        for r in pg.execute(
            f"SELECT store, product_id, console, platform FROM {GAMES}.versions"
        ).fetchall()
    }
    for row in _stand_ins(src, catalog, pg, repairs):
        key = (row["store"], row["product_id"], row["console"])
        if key not in products or products[key] is None:
            lack.stand_ins += 1
    return lack


def catalog_identical(
    src: Source,
    catalog: dict[str, Table],
    pg: psycopg.Connection,
    repairs: Repairs,
) -> bool:
    for table in catalog.values():
        _ours, _theirs, detail = compare_table(src, pg, table, repairs)
        if detail is not None:
            return False
    return True


def merge_catalog(
    src: Source, catalog: dict[str, Table], pg: psycopg.Connection, repairs: Repairs
) -> list[int]:
    """What only this source knew added to `games`; returns the kept
    stand-ins' ids in the catalog, for linking into games after."""
    shared_hltb = _shared_hltb(pg)
    for name in MERGED:
        if src.where(name) is None:
            continue
        table = catalog[name]
        started = time.monotonic()
        # `seq` is the catalog's to give: it goes on after what it has.
        columns = [c for c in insert_columns(table, src) if not _is_seq(table, c, src)]
        keys = _target_keys(pg, table)
        added = copy_rows(
            pg, table, columns, _missing_rows(src, table, columns, repairs, keys, shared_hltb)
        )
        _line(name, added, started, prefix="+")
    return _keep_stand_ins(src, catalog, pg, repairs)


def _keep_stand_ins(
    src: Source, catalog: dict[str, Table], pg: psycopg.Connection, repairs: Repairs
) -> list[int]:
    """Identity columns are the catalog's: a version is found by its product
    or takes a new id; nothing is written with the source's."""
    new_id: dict[int, int] = {}
    table = catalog["versions"]
    for row in _stand_ins(src, catalog, pg, repairs):
        old = row.pop("version_id")
        row.update(game_id=None, of_version_id=None)
        same = pg.execute(
            f"SELECT version_id, platform FROM {GAMES}.versions"
            " WHERE store = %s AND product_id = %s AND console = %s",
            (row["store"], row["product_id"], row["console"]),
        ).fetchone()
        if same is not None:
            # The catalog knows this product, just not as this list's.
            if same[1] is None:
                pg.execute(
                    f"UPDATE {GAMES}.versions SET platform = %s, title_id = %s"
                    " WHERE version_id = %s",
                    (row["platform"], row["title_id"], same[0]),
                )
            new_id[old] = int(same[0])
            continue
        query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING version_id").format(
            table.ident,
            sql.SQL(", ").join(map(sql.Identifier, row)),
            sql.SQL(", ").join(sql.Placeholder() * len(row)),
        )
        made = pg.execute(query, list(row.values())).fetchone()
        new_id[old] = int(made[0])
    for name in ("version_hltb", "dlcs"):
        child = catalog[name]
        if src.where(name) is None:
            continue
        columns = [c for c in insert_columns(child, src) if c != "dlc_id"]
        at = columns.index("version_id")
        query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
            child.ident,
            sql.SQL(", ").join(map(sql.Identifier, columns)),
            sql.SQL(", ").join(sql.Placeholder() * len(columns)),
        )
        for values in read_rows(src, child, columns, repairs):
            if values[at] in new_id:
                moved = list(values)
                moved[at] = new_id[values[at]]
                pg.execute(query, moved)
    return sorted(set(new_id.values()))


# ---------------------------------------------------------------- catalog ids


@dataclass
class GameMap:
    """A source's game id as the catalog's, through the versions they share."""

    by_id: dict[int, int] = field(default_factory=dict)
    by_key: dict[str, int] = field(default_factory=dict)
    dropped_favorites: int = 0
    cleared_prizes: int = 0
    # What no game holds yet: a kept stand-in is placed by the linker, after the
    # commit, and these follow it then.
    waiting_favorites: list[dict[str, Any]] = field(default_factory=list)
    waiting_prizes: list[tuple[int, int]] = field(default_factory=list)


def game_map(src: Source, pg: psycopg.Connection) -> GameMap:
    out = GameMap()
    for store, product, console, game in pg.execute(
        f"SELECT store, product_id, console, game_id FROM {GAMES}.versions"
        " WHERE game_id IS NOT NULL"
    ).fetchall():
        out.by_key[f"{store}:{product}:{console}"] = game
    if src.where("games") is None or src.where("versions") is None:
        return out
    merged = dict(
        src.conn.execute(
            f"SELECT game_id, merged_into FROM {src.ref('games')} WHERE merged_into IS NOT NULL"
        ).fetchall()
    )
    # Any version they share, the anchor first: the catalog may know a game's
    # stand-in anchor as a store product by now, under another key.
    versions = src.conn.execute(
        f"SELECT v.game_id, v.store, v.product_id, v.console FROM {src.ref('versions')} v"
        f" JOIN {src.ref('games')} g ON g.game_id = v.game_id"
        " ORDER BY v.version_id = g.anchor_version_id DESC, v.version_id"
    ).fetchall()
    at_anchor: dict[int, int] = {}
    for game, store, product, console in versions:
        key = f"{store.decode()}:{product.decode()}:{console.decode()}"
        if key in out.by_key:
            at_anchor.setdefault(game, out.by_key[key])
    # An old id leads on to the game it was merged into.
    ids = {r[0] for r in src.conn.execute(f"SELECT game_id FROM {src.ref('games')}").fetchall()}
    for game in ids:
        at = game
        for _ in range(32):
            if at not in merged:
                break
            at = merged[at]
        if at in at_anchor:
            out.by_id[game] = at_anchor[at]
    return out


def _mapped_pending(pending: Any, mapping: GameMap) -> Any:
    """A waiting change names a game by the source's id too; one with no game here
    loses that change rather than name another game."""
    if not pending:
        return pending
    text = pending.decode() if isinstance(pending, bytes) else str(pending)
    try:
        change = json.loads(text)
    except ValueError:
        return pending
    if not isinstance(change, dict) or not change.get("game_id"):
        return pending
    new = mapping.by_id.get(int(change["game_id"]))
    if new is None:
        mapping.cleared_prizes += 1
        del change["game_id"]
    else:
        change["game_id"] = new
    return json.dumps(change, ensure_ascii=False)


def _mapped(
    table: Table, columns: list[str], rows: Iterable[tuple[Any, ...]], mapping: GameMap
) -> Iterator[tuple[Any, ...]]:
    at = columns.index("game_id") if "game_id" in columns else None
    if at is None:
        yield from rows
        return
    if table.name == "pass_items":
        pending_at = columns.index("pending") if "pending" in columns else None
        item_at = columns.index("item_id")
        for row in rows:
            if pending_at is not None:
                row = (
                    *row[:pending_at],
                    _mapped_pending(row[pending_at], mapping),
                    *row[pending_at + 1 :],
                )
            if row[at] is None:
                yield row
                continue
            new = mapping.by_id.get(row[at])
            if new is None:
                mapping.waiting_prizes.append((row[item_at], row[at]))
            yield (*row[:at], new, *row[at + 1 :])
        return
    anchor_at = columns.index("anchor_key")
    person_at = columns.index("person_id")
    seen: set[tuple[int, int]] = set()
    for row in rows:
        new = mapping.by_key.get(row[anchor_at]) or mapping.by_id.get(row[at])
        if new is None:
            mapping.waiting_favorites.append(dict(zip(columns, row, strict=True)))
            continue
        if (row[person_at], new) in seen:
            mapping.dropped_favorites += 1
            continue
        seen.add((row[person_at], new))
        yield (*row[:at], new, *row[at + 1 :])


MAPPED_TABLES = frozenset({"favorite_games", "pass_items"})


# ---------------------------------------------------------------- import


def copy_rows(
    pg: psycopg.Connection, table: Table, columns: list[str], rows: Iterable[tuple[Any, ...]]
) -> int:
    count = 0
    statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
        table.ident, sql.SQL(", ").join(map(sql.Identifier, columns))
    )
    with pg.cursor() as cursor, cursor.copy(statement) as copy:
        for row in rows:
            copy.write_row(row)
            count += 1
    return count


def _line(name: str, rows: int, started: float, prefix: str = "") -> None:
    print(f"  {name:32} {prefix}{rows:>10} rows {time.monotonic() - started:8.1f} s", flush=True)


def _source_counters(src: Source) -> dict[str, int]:
    """How far each AUTOINCREMENT table has counted: past its highest row when
    that row was deleted, and an id must not name somebody else later (an old
    button says `p<id>`)."""
    counters: dict[str, int] = {}
    for owner in (SERVER, GAMES) if src.games_file else (SERVER,):
        try:
            rows = src.conn.execute(f"SELECT name, seq FROM {owner}.sqlite_sequence").fetchall()
        except sqlite3.OperationalError:  # no AUTOINCREMENT table in this file
            continue
        for name, seq in rows:
            counters[name.decode()] = int(seq)
    return counters


def _set_sequences(
    pg: psycopg.Connection, schema: str, counted: dict[str, int] | None = None
) -> None:
    """Every identity column's counter past what was written with its value.
    setval does not roll back: this is the last thing before the commit."""
    rows = pg.execute(
        "SELECT table_name, column_name FROM information_schema.columns"
        " WHERE table_schema = %s AND is_identity = 'YES'",
        (schema,),
    ).fetchall()
    for table, column in rows:
        qualified = sql.Identifier(schema, table)
        highest = pg.execute(
            sql.SQL("SELECT MAX({}) FROM {}").format(sql.Identifier(column), qualified)
        ).fetchone()[0]
        if counted and table in counted and (highest is None or counted[table] > highest):
            highest = counted[table]
        sequence = pg.execute(
            "SELECT pg_get_serial_sequence(%s, %s)",
            (qualified.as_string(pg), column),
        ).fetchone()[0]
        # A Telegram group's chat_id is negative, and no counter goes below 1.
        # Never back: in the shared catalog the other bot has counted further,
        # and an id it used and deleted must not come round again.
        last, called = pg.execute(
            sql.SQL("SELECT last_value, is_called FROM {}").format(sql.SQL(sequence))
        ).fetchone()
        if called and (highest is None or highest <= last):
            continue
        if highest is None or highest < 1:
            pg.execute("SELECT setval(%s, 1, false)", (sequence,))
        else:
            pg.execute("SELECT setval(%s, %s, true)", (sequence, highest))


def _connect(dsn: str) -> psycopg.Connection:
    pg = psycopg.connect(dsn, autocommit=False, client_encoding="UTF8")
    encoding = pg.execute("SHOW server_encoding").fetchone()[0]
    if encoding != "UTF8":
        pg.close()
        raise TransferError(f"the database's encoding is {encoding}, not UTF8")
    pg.rollback()
    return pg


def _check_name(schema: str) -> str:
    if not _SAFE_NAME.match(schema) or schema == GAMES:
        raise TransferError("the server's schema must be a plain name other than games")
    return schema


def run_bring_up(db: Path, games: Path | None, out: Path) -> tuple[Path, Path | None]:
    """Copies of a source, brought up to the SQLite migrations this code ships.

    A migration may fill a table no schema file brings (141, the chats' admins), so
    the import refuses a source behind them, and this branch has no SQLite bot left
    to run them. The source stays as it is: it is what a rollback goes back to.
    """
    out.mkdir(parents=True, exist_ok=True)

    def copy_of(path: Path) -> Path:
        target = out / path.name
        if target.exists():
            raise TransferError(f"{target} is there already")
        source = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        kept = sqlite3.connect(target)
        source.backup(kept)
        kept.close()
        source.close()
        return target

    if not db.exists():
        raise TransferError(f"{db} not found")
    db_copy = copy_of(db)
    games_copy = copy_of(games) if games is not None else None
    conn = sqlite3.connect(db_copy)
    try:
        # A migration names a table wherever it lives (144 is the catalog's).
        if games_copy is not None:
            conn.execute(f"ATTACH DATABASE ? AS {GAMES}", (str(games_copy),))
        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        for path in sorted(SQLITE_MIGRATIONS.glob("*.sql")):
            if path.stem in applied:
                continue
            conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (path.stem, datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")),
            )
            conn.commit()
            print(f"  applied {path.stem}")
    finally:
        conn.close()
    print(f"brought up: {db_copy}" + (f", {games_copy}" if games_copy else ""))
    return db_copy, games_copy


def run_preflight(args: argparse.Namespace) -> int:
    src = Source(args.db, args.games)
    pg = _connect(args.dsn)
    try:
        app, catalog = _probe_plan(pg)
        report = preflight(src, app, catalog)
        print_preflight(report, args.accept_problems)
        return 1 if report.problems else 0
    finally:
        pg.close()
        src.close()


@dataclass
class ImportResult:
    kept: list[int] = field(default_factory=list)
    catalog: str = "imported"  # imported / identical / nothing_lacking / merged
    tables: dict[str, int] = field(default_factory=dict)


def run_import(
    db: Path,
    games: Path | None,
    dsn: str,
    schema: str,
    *,
    merge: bool = False,
    accept: bool = False,
    dry_run: bool = False,
) -> ImportResult:
    _check_name(schema)
    began = time.monotonic()
    src = Source(db, games)
    pg = _connect(dsn)
    result = ImportResult()
    where = "the import"
    try:
        probe_app, probe_catalog = _probe_plan(pg)
        report = preflight(src, probe_app, probe_catalog)
        print_preflight(report, accept)
        if report.unfixable:
            raise TransferError("refused: the preflight found what no flag can answer")
        if report.problems and not accept:
            raise TransferError("refused: real problems above; --accept-problems says what it does")
        repairs = plan_repairs(src, (probe_app, probe_catalog), report, accept)

        pg.execute("SELECT pg_advisory_xact_lock(%s)", (_IMPORT_LOCK,))
        if not _has_tables(pg, GAMES):
            _make_schema(pg, GAMES, GAMES_SQL, GAMES)
        if not _has_tables(pg, schema):
            _make_schema(pg, schema, APP_SQL, GAMES)
        app = read_plan(pg, schema)
        catalog = read_plan(pg, GAMES)
        full = _filled(pg, app)
        if full:
            raise TransferError(f"refused: schema {schema} has rows in: {', '.join(full)}")
        pg.execute("SET CONSTRAINTS ALL DEFERRED")

        mapping: GameMap | None = None
        if _filled(pg, catalog):
            if catalog_identical(src, catalog, pg, repairs):
                print("catalog: the same as games, skipped")
                result.catalog = "identical"
            else:
                lack = catalog_lack(src, catalog, pg, repairs)
                if lack.nothing:
                    print("catalog: differs, but has nothing games lacks: skipped")
                    print("  (verify this server with --merge-catalog)")
                    result.catalog = "nothing_lacking"
                elif not merge:
                    for name, count in lack.rows.items():
                        if count:
                            print(f"  only this server's: {name:32} {count}")
                    print(f"  only this server's: stand-ins for lists {lack.stand_ins}")
                    raise TransferError("refused: games is filled and differs: --merge-catalog")
                else:
                    print("catalog: merging what only this server knew")
                    where = "merging the catalog"
                    result.kept = merge_catalog(src, catalog, pg, repairs)
                    result.catalog = "merged"
                    print(f"  kept stand-ins of lists new to the catalog: {len(result.kept)}")
                mapping = game_map(src, pg)
        else:
            print("catalog:")
            for name, table in sorted(catalog.items()):
                started = time.monotonic()
                where = f"table {name}"
                if not src.columns(name):
                    result.tables[name] = 0
                    continue
                columns = insert_columns(table, src)
                result.tables[name] = copy_rows(
                    pg, table, columns, read_rows(src, table, columns, repairs)
                )
                _line(name, result.tables[name], started)

        print(f"schema {schema}:")
        for name, table in sorted(app.items()):
            started = time.monotonic()
            where = f"table {name}"
            if not src.columns(name):
                # New since the source's code: nothing to bring.
                result.tables[name] = 0
                _line(name, 0, started)
                continue
            columns = insert_columns(table, src)
            rows: Iterable[tuple[Any, ...]] = read_rows(src, table, columns, repairs)
            if mapping is not None and name in MAPPED_TABLES:
                rows = _mapped(table, columns, rows, mapping)
            result.tables[name] = copy_rows(pg, table, columns, rows)
            _line(name, result.tables[name], started)
        # A schema made from its file already holds PostgreSQL's own migrations.
        for stem in _pg_migrations():
            pg.execute(
                sql.SQL(
                    "INSERT INTO {} (version, applied_at) VALUES (%s, now()::text)"
                    " ON CONFLICT DO NOTHING"
                ).format(sql.Identifier(schema, "schema_migrations")),
                (stem,),
            )

        where = "the foreign keys' check"
        pg.execute("SET CONSTRAINTS ALL IMMEDIATE")
        if dry_run:
            pg.rollback()
            print("dry run: everything fitted, nothing written")
        else:
            where = "setting the counters"
            counted = _source_counters(src)
            _set_sequences(pg, schema, counted)
            if result.catalog in ("imported", "merged"):
                _set_sequences(pg, GAMES, counted)
            where = "the commit"
            pg.commit()
    except psycopg.Error as exc:
        pg.rollback()
        raise _say_refusal(exc, where) from None
    except BaseException:
        pg.rollback()
        raise
    finally:
        pg.close()
        src.close()
    if result.kept and not dry_run:
        _link_kept(dsn, schema, result.kept)
    if mapping is not None and not dry_run:
        _settle_waiting(db, games, dsn, schema, mapping)
    print(f"total: {time.monotonic() - began:.1f} s")
    return result


def _settle_waiting(db: Path, games: Path | None, dsn: str, schema: str, mapping: GameMap) -> None:
    """Favorites and prizes of games only the linker could place: given their game
    now, or counted as lost, out loud."""
    if mapping.waiting_favorites or mapping.waiting_prizes:
        src = Source(db, games)
        pg = _connect(dsn)
        try:
            now = game_map(src, pg)
            for row in mapping.waiting_favorites:
                new = now.by_key.get(row["anchor_key"]) or now.by_id.get(row["game_id"])
                if new is None:
                    mapping.dropped_favorites += 1
                    continue
                values = {**row, "game_id": new}
                pg.execute(
                    sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
                        sql.Identifier(schema, "favorite_games"),
                        sql.SQL(", ").join(map(sql.Identifier, values)),
                        sql.SQL(", ").join(sql.Placeholder() * len(values)),
                    ),
                    list(values.values()),
                )
            for item, game in mapping.waiting_prizes:
                new = now.by_id.get(game)
                if new is None:
                    mapping.cleared_prizes += 1
                    continue
                pg.execute(
                    sql.SQL("UPDATE {} SET game_id = %s WHERE item_id = %s").format(
                        sql.Identifier(schema, "pass_items")
                    ),
                    (new, item),
                )
            pg.commit()
        finally:
            pg.close()
            src.close()
    if mapping.dropped_favorites or mapping.cleared_prizes:
        print(
            f"LOST: favorites dropped {mapping.dropped_favorites},"
            f" prizes' game cleared {mapping.cleared_prizes}"
        )


def _link_kept(dsn: str, schema: str, version_ids: list[int]) -> None:
    """The kept stand-ins put into games, with the weights now active."""
    from bot.db import tools
    from bot.db.repo import Repo
    from bot.services.game_link import GameLinker

    async def link() -> None:
        database = await tools.open_database(dsn, schema=schema)
        try:
            report = await GameLinker(Repo(database)).link_versions(version_ids)
            print(f"linked {len(version_ids)} kept versions: {len(report.games)} games touched")
        finally:
            await database.close()

    tools.run(link())


# ---------------------------------------------------------------- verify


def _sequence_behind(pg: psycopg.Connection, schema: str, table: str, column: str) -> bool:
    qualified = sql.Identifier(schema, table)
    highest = pg.execute(
        sql.SQL("SELECT MAX({}) FROM {}").format(sql.Identifier(column), qualified)
    ).fetchone()[0]
    if highest is None:
        return False
    sequence = pg.execute(
        "SELECT pg_get_serial_sequence(%s, %s)", (qualified.as_string(pg), column)
    ).fetchone()[0]
    last, called = pg.execute(
        sql.SQL("SELECT last_value, is_called FROM {}").format(sql.SQL(sequence))
    ).fetchone()
    return (last if called else last - 1) < highest


def run_verify(
    db: Path,
    games: Path | None,
    dsn: str,
    schema: str,
    *,
    merge: bool = False,
    accept: bool = False,
) -> list[str]:
    """What differs, by table; empty when all agrees."""
    _check_name(schema)
    began = time.monotonic()
    src = Source(db, games)
    pg = _connect(dsn)
    wrong: list[str] = []

    def report(name: str, ours: int, theirs: int, detail: str | None, started: float) -> None:
        state = "ok" if detail is None else "DIFFERS"
        took = time.monotonic() - started
        print(f"  {name:32} {ours:>10} {theirs:>10} {state:8} {took:6.1f} s", flush=True)
        if detail is not None:
            print(f"    {detail}")
            wrong.append(f"{name}: {detail}")

    try:
        pg.execute("SELECT pg_advisory_xact_lock_shared(%s)", (_IMPORT_LOCK,))
        app, catalog = read_plan(pg, schema), read_plan(pg, GAMES)
        if not app or not catalog:
            raise TransferError(f"schema {schema} or {GAMES} has no tables")
        probe_report = Preflight()
        if accept:
            probe_report = preflight(src, app, catalog)
        repairs = plan_repairs(src, (app, catalog), probe_report, accept)

        print(f"{'':2}{'table':32} {'source':>10} {'target':>10}")
        if merge:
            lack = catalog_lack(src, catalog, pg, repairs)
            print("catalog: nothing of the source's may be missing")
            for name, count in lack.rows.items():
                if count:
                    wrong.append(f"{name}: {count} rows of the source's are not in games")
                    print(f"  {name:32} missing {count}")
            if lack.stand_ins:
                wrong.append(f"versions: {lack.stand_ins} lists have no version in games")
                print(f"  versions: lists with no version {lack.stand_ins}")
        else:
            print("catalog:")
            for name, table in sorted(catalog.items()):
                started = time.monotonic()
                ours, theirs, detail = compare_table(src, pg, table, repairs)
                report(name, ours, theirs, detail, started)
        print(f"schema {schema}:")
        for name, table in sorted(app.items()):
            started = time.monotonic()
            if not src.columns(name):
                continue
            if merge and name == "favorite_games":
                # Mapped, some dropped; a kept stand-in's game came only after.
                ours = sum(1 for _ in read_rows(src, table, ["person_id"], repairs))
                theirs = sum(1 for _ in pg_rows(pg, table, ["person_id"]))
                print(f"  {name:32} {ours:>10} {theirs:>10} mapped")
                continue
            skip = ("game_id",) if merge and name == "pass_items" else ()
            ours, theirs, detail = compare_table(src, pg, table, repairs, skip=skip)
            report(name, ours, theirs, detail, started)
        for owner, plan in ((schema, app), (GAMES, catalog)):
            for table in plan.values():
                for column in table.columns.values():
                    if column.identity and _sequence_behind(pg, owner, table.name, column.name):
                        wrong.append(f"{table.name}.{column.name}: its counter is behind its rows")
                        print(f"  {table.name}.{column.name}: its counter is behind its rows")
    except psycopg.Error as exc:
        raise _say_refusal(exc, "the verify") from None
    finally:
        pg.rollback()
        pg.close()
        src.close()
    print(f"total: {time.monotonic() - began:.1f} s")
    return wrong


# ---------------------------------------------------------------- the command


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("mode", choices=("bring-up", "preflight", "import", "verify"))
    parser.add_argument("--out", type=Path, help="bring-up: the folder for the copies")
    parser.add_argument("--db", type=Path, required=True, help="the server's SQLite copy")
    parser.add_argument("--games", type=Path, help="its catalog, if not the file it names")
    parser.add_argument(
        "--dsn", default=os.environ.get("DATABASE_URL"), help="default: DATABASE_URL"
    )
    parser.add_argument("--schema", choices=("prod", "test", "dev"), help="the target schema")
    parser.add_argument(
        "--merge-catalog",
        action="store_true",
        help="add what only this server knew to a filled games (verify: hold it to that)",
    )
    parser.add_argument(
        "--accept-problems", action="store_true", help="import through what the preflight found"
    )
    parser.add_argument("--dry-run", action="store_true", help="import, then roll it all back")
    args = parser.parse_args()
    if args.mode == "bring-up":
        if not args.out:
            parser.error("bring-up needs --out")
        try:
            run_bring_up(args.db, args.games, args.out)
        except (TransferError, sqlite3.Error) as exc:
            print(exc, file=sys.stderr)
            return 2
        return 0
    if not args.dsn:
        parser.error("--dsn or DATABASE_URL names the database")
    if args.mode != "preflight" and not args.schema:
        parser.error(f"{args.mode} needs --schema")
    try:
        if args.mode == "preflight":
            return run_preflight(args)
        if args.mode == "import":
            run_import(
                args.db,
                args.games,
                args.dsn,
                args.schema,
                merge=args.merge_catalog,
                accept=args.accept_problems,
                dry_run=args.dry_run,
            )
            return 0
        wrong = run_verify(
            args.db,
            args.games,
            args.dsn,
            args.schema,
            merge=args.merge_catalog,
            accept=args.accept_problems,
        )
        if wrong:
            print(f"verify: {len(wrong)} differences")
            return 1
        print("verify: everything agrees")
        return 0
    except TransferError as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
