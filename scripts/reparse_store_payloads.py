"""Re-derive the store side from the answers already kept (#147; owner,
2026-10-12) — **no request to any store**.

Every answer in `source_payloads` is read again through today's parsers and
written as a collection would write it (`StoreCollector.reparse_stored`):
versions on the consoles a product is made for, availability, Xbox add-ons
of their own game only, the Xbox 360 store pages, HLTB entries (a DLC's game
as its parent, an entry's own times) and their links, the answers kept again
without prices. Then every game is rebuilt (`GameLinker.link_all`).

Dry run by default: the work is done on a copy of the database (made with
sqlite's `backup()`, in a temporary folder) and what would change is printed.
`--apply` first copies the database into `backups/`, then does it for real —
with the bot stopped (one process writes the database).

Usage:
    .venv/Scripts/python.exe -X utf8 -m scripts.reparse_store_payloads --db data/games.db
    .venv/Scripts/python.exe -X utf8 -m scripts.reparse_store_payloads --db data/games.db --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from bot.db.repo import Database, Repo
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


def _counts(path: Path) -> dict[str, object]:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        found: dict[str, object] = {}
        for label, query in SUMMARY:
            try:
                found[label] = conn.execute(query).fetchone()[0]
            except sqlite3.Error:
                found[label] = "—"  # a column a migration has not added yet
        return found
    finally:
        conn.close()


def _copy(source: Path, target: Path) -> None:
    """A copy as sqlite makes it (the database runs in WAL mode: never `cp`)."""
    src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


async def _run(path: Path) -> dict[str, int]:
    database = await Database(path).connect()
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
    parser.add_argument("--db", help="database file (default: DB_PATH from the env file)")
    parser.add_argument("--apply", action="store_true", help="write (the bot stopped)")
    args = parser.parse_args()
    if args.db:
        db_path = Path(args.db)
    else:
        from bot.config import get_settings

        db_path = Path(get_settings().db_path)
    before = _counts(db_path)
    if args.apply:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        backups = Path("backups")
        backups.mkdir(exist_ok=True)
        backup = backups / f"{db_path.stem}-pre-reparse-{stamp}.db"
        _copy(db_path, backup)
        print(f"backed up to {backup}")
        done = asyncio.run(_run(db_path))
        after = _counts(db_path)
    else:
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / db_path.name
            _copy(db_path, copy)
            done = asyncio.run(_run(copy))
            after = _counts(copy)
    print("done:", ", ".join(f"{k} {v}" for k, v in done.items()))
    width = max(len(label) for label, _ in SUMMARY)
    for label, _ in SUMMARY:
        mark = "" if before[label] == after[label] else "   ←"
        print(f"{label:<{width}}  {before[label]!s:>8} → {after[label]!s:<8}{mark}")
    if not args.apply:
        print("dry run: nothing written (--apply to write, with the bot stopped)")


if __name__ == "__main__":
    main()
