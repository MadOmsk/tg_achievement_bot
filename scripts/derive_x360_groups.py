"""Group every Xbox 360 list's achievements as base or non_base by their ids
and gamerscore (#147; owner, 2026-10-15: a 360 game says nothing of its
groups; `xbox.models.x360_groups`). No request. The database is copied into
`backups/` first.

    .venv/Scripts/python.exe -X utf8 -m scripts.derive_x360_groups --db data/games.db
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from bot.db.repo import Database, Repo


def _backup(db_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    target = Path("backups") / f"{db_path.stem}-pre-x360-groups-{stamp}.db"
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
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    db_path = Path(args.db)
    print("database copied to", _backup(db_path))
    database = await Database(db_path).connect()
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
    raise SystemExit(asyncio.run(main()))
