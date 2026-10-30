"""Look once for the add-ons of every Xbox 360 game that has a store page
(owner, 2026-10-28): a 360 game's add-ons are sold only on their own
(`StoreCollector._x360_addons`, 2026-10-27), and the search runs only when
the game is collected again — weeks away for most, never on a server whose
store collection is off. A game already searched is skipped until due. The
catalog's pace (`xbox_catalog.LIMITER`); beside a running bot (it only adds
DLC rows). The database is copied into `backups/` first.

    .venv/Scripts/python.exe -X utf8 -m scripts.collect_x360_addons --limit 5
    .venv/Scripts/python.exe -X utf8 -m scripts.collect_x360_addons --schema prod
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from bot.config import get_settings
from bot.db import tools
from bot.db.repo import Repo
from bot.services.store_collect import CollectReport, StoreCollector

logging.basicConfig(level="WARNING")


def _backup(schema: str | None) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    name = schema or get_settings().database_schema
    return tools.backup(Path("backups") / f"{name}-pre-x360-addons-{stamp}.dump", schema=schema)


def _titles(schema: str | None) -> list[str]:
    with tools.connect(schema=schema, readonly=True) as conn:
        rows = conn.execute(
            "SELECT DISTINCT title_id FROM versions WHERE store = 'xbox' AND console = '360'"
            " AND stand_in = 0 AND platform = 'xbox_360' AND title_id IS NOT NULL ORDER BY title_id"
        ).fetchall()
    return [str(row[0]) for row in rows]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    tools.add_arguments(parser)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    titles = _titles(args.schema)
    if args.limit:
        titles = titles[: args.limit]
    print(f"{len(titles)} 360 games with a store page")
    print("database copied to", _backup(args.schema))
    database = await tools.open_database(schema=args.schema)
    try:
        collector = StoreCollector(Repo(database))
        asked = dlcs = 0
        errors: list[str] = []
        for n, title_id in enumerate(titles, 1):
            report = CollectReport("xbox_360", title_id)
            await collector._x360_addons(title_id, report, False)
            asked += bool(report.asked)
            dlcs += report.dlcs
            errors += report.errors
            if n % 25 == 0:
                print(f"  {n}/{len(titles)}: searched {asked}, add-ons {dlcs}")
        print(f"searched {asked} (the rest not due), add-ons kept {dlcs}, errors {len(errors)}")
        for error in errors[:10]:
            print("  ", error)
    finally:
        await database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(tools.run(main()))
