"""Link the Steam versions to the HowLongToBeat entries whose pages name
their app (#147; owner, 2026-10-15) — the surest evidence there is; the lazy
match never ran for a Steam list nobody published in. Nothing that has a link
(or a refusal) is touched. The database is copied into `backups/` first.

    .venv/Scripts/python.exe -X utf8 -m scripts.link_hltb_by_steam_app --dry-run
    .venv/Scripts/python.exe -X utf8 -m scripts.link_hltb_by_steam_app
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path

from bot.db import files
from bot.db.repo import Database, Repo
from bot.services.store_collect import link_steam_apps_to_hltb


def _backup(db_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    target = Path("backups") / f"{db_path.stem}-pre-steam-hltb-{stamp}.db"
    files.backup(db_path, target)
    return target


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.db:
        db_path = Path(args.db)
    else:
        from bot.config import get_settings

        db_path = Path(get_settings().db_path)
    database = await Database(db_path).connect()
    try:
        repo = Repo(database)
        if args.dry_run:
            rows = await repo.steam_versions_with_hltb_by_app()
            print(f"{len({r['version_id'] for r in rows})} Steam versions have a candidate")
            return 0
        print("database copied to", _backup(db_path))
        print(await link_steam_apps_to_hltb(repo))
    finally:
        await database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
