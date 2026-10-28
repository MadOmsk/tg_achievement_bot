"""Look for the store pages of the Xbox 360 lists by their names (#147;
owner, 2026-10-15): the catalog's lookup by title id knows no 360 game, so 451
of 458 lists stood in for themselves. A product counts only when its own
`[Fission]` mark names the list (`StoreCollector.x360_by_name`); the list's
stand-in then becomes that product. The catalog's pace (`xbox_catalog.LIMITER`).
The database is copied into `backups/` first.

    .venv/Scripts/python.exe -X utf8 -m scripts.collect_x360 --limit 10
    .venv/Scripts/python.exe -X utf8 -m scripts.collect_x360
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from bot.db import files
from bot.db.repo import Database, Repo
from bot.services.game_link import GameLinker
from bot.services.store_collect import StoreCollector

logging.basicConfig(level="WARNING")


def _backup(db_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    target = Path("backups") / f"{db_path.stem}-pre-x360-{stamp}.db"
    files.backup(db_path, target)
    return target


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-relink", action="store_true", help="leave the games as they are")
    args = parser.parse_args()
    if args.db:
        db_path = Path(args.db)
    else:
        from bot.config import get_settings

        db_path = Path(get_settings().db_path)
    database = await Database(db_path).connect()
    try:
        repo = Repo(database)
        lists = await repo.stand_in_lists("xbox_360")
        if args.limit:
            lists = lists[: args.limit]
        print(f"{len(lists)} 360 lists with no store page")
        print("database copied to", _backup(db_path))
        collector = StoreCollector(repo)
        found: list[int] = []
        for n, title_id in enumerate(lists, 1):
            if await collector.x360_by_name(title_id, force=True):
                found += await repo.versions_of_list("xbox_360", title_id)
            if n % 25 == 0:
                print(f"  {n}/{len(lists)}, found {len(found)}")
        print(f"found a store page for {len(found)}")
        if found and not args.no_relink:
            linked = await GameLinker(repo).link_versions(sorted(set(found)))
            print(f"re-linked: {len(linked.games)} games, {len(linked.review)} to review")
    finally:
        await database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
