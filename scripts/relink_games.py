"""Rebuild every game from what is stored now (#147): `GameLinker.link_all`,
the operator's and the advisers' labels kept as they are. The database is
copied into `backups/` first. With the viewer stopped or not: the linker's
work is the viewer's own on a decision, so run it when nobody is answering.

    .venv/Scripts/python.exe -X utf8 -m scripts.relink_games [--schema dev]
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from bot.db import tools
from bot.db.repo import Repo
from bot.services.game_link import GameLinker, spread_hltb


def _backup(schema: str | None) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = Path("backups") / f"{schema or 'database'}-pre-relink-{stamp}.dump"
    return tools.backup(target, schema=schema)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    tools.add_arguments(parser)
    parser.add_argument(
        "--hltb-only",
        action="store_true",
        help="only spread each game's HLTB entry to its releases",
    )
    args = parser.parse_args()
    print("database copied to", _backup(args.schema))
    database = await tools.open_database(schema=args.schema)
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
    raise SystemExit(tools.run(main()))
