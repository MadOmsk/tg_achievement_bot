"""Re-derive the store side from the answers already kept (#147; owner,
2026-10-12) — **no request to any store**.

Every answer in `source_payloads` is read again through today's parsers and
written as a collection would write it (`StoreCollector.reparse_stored`):
versions on the consoles a product is made for, availability, Xbox add-ons
of their own game only, the Xbox 360 store pages, HLTB entries (a DLC's game
as its parent, an entry's own times) and their links, the answers kept again
without prices. Then every game is rebuilt (`GameLinker.link_all`).

Dry run by default: the work is done on a copy of the schema and the catalog
(`pg_dump` restored into a temporary database, so the role must be allowed to
create one) and what would change is printed. `--apply` first copies them into
`backups/`, then does it for real — with the bot stopped (one process writes
the database).

Usage:
    .venv/Scripts/python.exe -X utf8 -m scripts.reparse_store_payloads --schema dev
    .venv/Scripts/python.exe -X utf8 -m scripts.reparse_store_payloads --schema dev --apply
"""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from bot.config import get_settings
from bot.db import tools
from bot.db.repo import Repo
from bot.services.game_link import GameLinker
from bot.services.store_collect import StoreCollector

# What is counted before and after, to say what changed: (label, query).
SUMMARY = (
    ("versions", "SELECT COUNT(*) FROM versions"),
    ("versions on series", "SELECT COUNT(*) FROM versions WHERE console = 'series'"),
    (
        "versions with a cross-gen set",
        "SELECT COUNT(*) FROM versions WHERE cross_gen_set IS NOT NULL",
    ),
    ("versions on sale", "SELECT COUNT(*) FROM versions WHERE on_sale = 1"),
    ("versions off sale", "SELECT COUNT(*) FROM versions WHERE on_sale = 0"),
    ("versions, sale unknown", "SELECT COUNT(*) FROM versions WHERE on_sale IS NULL"),
    ("stand-ins", "SELECT COUNT(*) FROM versions WHERE stand_in = 1"),
    (
        "360 versions with a store page",
        "SELECT COUNT(*) FROM versions WHERE console = '360' AND stand_in = 0",
    ),
    ("dlc", "SELECT COUNT(*) FROM dlcs"),
    (
        "dlc linked to HLTB",
        "SELECT COUNT(DISTINCT dlc_id) FROM dlc_hltb WHERE source <> 'rejected'",
    ),
    ("version ↔ HLTB links", "SELECT COUNT(*) FROM version_hltb"),
    (
        "HLTB games filed under a child",
        "SELECT COUNT(*) FROM hltb_entries c JOIN hltb_entries p ON p.hltb_id = c.parent_hltb_id"
        " WHERE c.game_type = 'game' AND p.game_type = 'dlc'",
    ),
    ("games", "SELECT COUNT(*) FROM games WHERE merged_into IS NULL"),
    ("review pairs", "SELECT COUNT(*) FROM match_pairs"),
)


def _counts(dsn: str, schema: str) -> dict[str, object]:
    conn = tools.connect(dsn, schema=schema, readonly=True)
    try:
        found: dict[str, object] = {}
        for label, query in SUMMARY:
            try:
                found[label] = conn.execute(query).fetchone()[0]
            except psycopg.Error:
                found[label] = "—"  # a column a migration has not added yet
        return found
    finally:
        conn.close()


@contextmanager
def _copy(dsn: str, schema: str) -> Iterator[str]:
    """The schema and the catalog in a temporary database of their own: a dry
    run beside a running bot takes no lock on the rows it works on."""
    name = f"reparse_dry_run_{os.getpid()}"
    database = sql.Identifier(name)
    with tempfile.TemporaryDirectory() as folder:
        dump = tools.backup(Path(folder) / "copy.dump", dsn=dsn, schema=schema)
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(database))
            try:
                copy = make_conninfo(dsn, dbname=name)
                address, env = tools.tool_target(copy)
                subprocess.run(
                    ["pg_restore", "--no-owner", f"--dbname={address}", str(dump)],
                    check=True,
                    env=env,
                )
                yield copy
            finally:
                admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(database))


async def _run(dsn: str, schema: str) -> dict[str, int]:
    database = await tools.open_database(dsn, schema=schema)
    try:
        repo = Repo(database)
        done = await StoreCollector(repo).reparse_stored()
        linked = await GameLinker(repo).link_all()
        done["games rebuilt"] = len(linked.games)
        return done
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    tools.add_arguments(parser)
    parser.add_argument("--apply", action="store_true", help="write (the bot stopped)")
    args = parser.parse_args()
    settings = get_settings()
    dsn, schema = settings.database_url, args.schema or settings.database_schema
    before = _counts(dsn, schema)
    if args.apply:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        backup = tools.backup(
            Path("backups") / f"{schema}-pre-reparse-{stamp}.dump", dsn=dsn, schema=schema
        )
        print(f"backed up to {backup}")
        done = tools.run(_run(dsn, schema))
        after = _counts(dsn, schema)
    else:
        with _copy(dsn, schema) as copy:
            done = tools.run(_run(copy, schema))
            after = _counts(copy, schema)
    print("done:", ", ".join(f"{k} {v}" for k, v in done.items()))
    width = max(len(label) for label, _ in SUMMARY)
    for label, _ in SUMMARY:
        mark = "" if before[label] == after[label] else "   ←"
        print(f"{label:<{width}}  {before[label]!s:>8} → {after[label]!s:<8}{mark}")
    if not args.apply:
        print("dry run: nothing written (--apply to write, with the bot stopped)")


if __name__ == "__main__":
    main()
