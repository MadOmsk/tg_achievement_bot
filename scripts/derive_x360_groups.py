"""Group every Xbox 360 list's achievements as base or non_base by their ids
and gamerscore (#147; owner, 2026-10-15: a 360 game says nothing of its
groups; `xbox.models.x360_groups`). No request. The database is copied into
`backups/` first.

    .venv/Scripts/python.exe -X utf8 -m scripts.derive_x360_groups --schema dev
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from bot.config import get_settings
from bot.db import tools
from bot.db.repo import Repo


def _backup(schema: str | None) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    name = schema or get_settings().database_schema
    return tools.backup(Path("backups") / f"{name}-pre-x360-groups-{stamp}.dump", schema=schema)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    tools.add_arguments(parser)
    args = parser.parse_args()
    print("database copied to", _backup(args.schema))
    database = await tools.open_database(schema=args.schema)
    try:
        repo = Repo(database)
        lists = await repo.achievement_list_ids("xbox_360")
        grouped = 0
        for title_id in lists:
            grouped += await repo.derive_x360_groups(title_id)
        print(f"{len(lists)} 360 lists, {grouped} achievements grouped")
    finally:
        await database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(tools.run(main()))
