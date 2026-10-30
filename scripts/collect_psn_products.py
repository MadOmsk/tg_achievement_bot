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
import logging
from datetime import UTC, datetime
from pathlib import Path

from bot.config import get_settings
from bot.db import tools
from bot.db.repo import Repo
from bot.services import psn_products

logging.basicConfig(level="WARNING")


def _backup(schema: str | None) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    name = schema or get_settings().database_schema
    return tools.backup(Path("backups") / f"{name}-pre-psn-products-{stamp}.dump", schema=schema)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    tools.add_arguments(parser)
    parser.add_argument("--scope", choices=["played", "all"], default="played")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-fetch", action="store_true", help="only put kept pages in place")
    args = parser.parse_args()
    origin = "played" if args.scope == "played" else None
    database = await tools.open_database(schema=args.schema)
    try:
        repo = Repo(database)
        todo = await psn_products.products_of_concepts(repo, origin)
        print(f"{len(todo)} products named by the concepts ({args.scope})")
        if not args.no_fetch:
            print("database copied to", _backup(args.schema))
            print("pages:", await psn_products.read_pages(repo, origin, limit=args.limit))
        print("put in place:", await psn_products.put_in_place(repo, origin))
    finally:
        await database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(tools.run(main()))
