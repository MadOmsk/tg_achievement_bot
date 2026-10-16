"""Rebuild every game from what is stored now (#147): `GameLinker.link_all`,
the operator's and the advisers' labels kept as they are. The database is
copied into `backups/` first. With the viewer stopped or not: the linker's
work is the viewer's own on a decision, so run it when nobody is answering.

    .venv/Scripts/python.exe -X utf8 -m scripts.relink_games --db data/games.db
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from bot.db.repo import Database, Repo
from bot.services.game_link import GameLinker, spread_hltb


def _backup(db_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    target = Path("backups") / f"{db_path.stem}-pre-relink-{stamp}.db"
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
    parser.add_argument(
        "--hltb-only",
        action="store_true",
        help="only spread each game's HLTB entry to its releases",
    )
    args = parser.parse_args()
    print("database copied to", _backup(Path(args.db)))
    database = await Database(Path(args.db)).connect()
    try:
        if args.hltb_only:
            print("HLTB links made:", await spread_hltb(Repo(database)))
            return 0
        report = await GameLinker(Repo(database)).link_all()
        print(f"games {len(report.games)}, to review {len(report.review)}")
    finally:
        await database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
