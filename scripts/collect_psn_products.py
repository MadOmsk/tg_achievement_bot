"""Read the PlayStation store pages of the add-ons, editions, demos and themes
that the stored concepts name (#147; owner, 2026-10-15), keep each as it came
(`source_payloads`, source `psn_product`) and put them with their versions:
add-ons as DLC, game-category products as editions. One page every two
seconds. The database is copied into `backups/` first.

    .venv/Scripts/python.exe -X utf8 -m scripts.collect_psn_products --scope played
    .venv/Scripts/python.exe -X utf8 -m scripts.collect_psn_products --scope played --limit 10
    .venv/Scripts/python.exe -X utf8 -m scripts.collect_psn_products --scope played --no-fetch
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from bot.db.repo import Database, Repo
from bot.services import psn_products

logging.basicConfig(level="WARNING")


def _backup(db_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    target = Path("backups") / f"{db_path.stem}-pre-psn-products-{stamp}.db"
    source = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    copy = sqlite3.connect(target)
    try:
        source.backup(copy)
    finally:
        copy.close()
        source.close()
    return target


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", default=None)
    parser.add_argument("--scope", choices=["played", "all"], default="played")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-fetch", action="store_true", help="only put kept pages in place")
    args = parser.parse_args()
    if args.db:
        db_path = Path(args.db)
    else:
        from bot.config import get_settings

        db_path = Path(get_settings().db_path)
    origin = "played" if args.scope == "played" else None
    database = await Database(db_path).connect()
    try:
        repo = Repo(database)
        todo = await psn_products.products_of_concepts(repo, origin)
        print(f"{len(todo)} products named by the concepts ({args.scope})")
        if not args.no_fetch:
            print("database copied to", _backup(db_path))
            print("pages:", await psn_products.read_pages(repo, origin, limit=args.limit))
        print("put in place:", await psn_products.put_in_place(repo, origin))
    finally:
        await database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
