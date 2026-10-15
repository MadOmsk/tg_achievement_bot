"""Match the achievement lists of a platform that have no HowLongToBeat entry
yet (#147; owner, 2026-10-15): the match is lazy — asked when a game's first
new achievement is published, or its page opened — so a library nobody earned
anything in since never had one. Each list is asked again whatever its
schedule said (`hltb_match`), through the same matcher (`ensure_title_match`):
HLTB's search at its own pace, refusals and the rules as always. The database
is copied into `backups/` first.

    .venv/Scripts/python.exe -X utf8 -m scripts.match_hltb_lists --platform steam --limit 10
    .venv/Scripts/python.exe -X utf8 -m scripts.match_hltb_lists --platform steam
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from bot.db.repo import Database, Repo
from bot.services.hltb import ensure_title_match

logging.basicConfig(level="WARNING")


def _backup(db_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    target = Path("backups") / f"{db_path.stem}-pre-hltb-match-{stamp}.db"
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
    parser.add_argument("--platform", required=True)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    if args.db:
        db_path = Path(args.db)
    else:
        from bot.config import get_settings

        db_path = Path(get_settings().db_path)
    database = await Database(db_path).connect()
    try:
        repo = Repo(database)
        todo = [
            title_id
            for title_id in await repo.achievement_list_ids(args.platform)
            if await repo.list_hltb_match(args.platform, title_id) is None
        ][: args.limit]
        print(f"{len(todo)} {args.platform} lists with no HLTB entry")
        print("database copied to", _backup(db_path))
        matched = 0
        for n, title_id in enumerate(todo, 1):
            await repo.make_fetch_due(f"{args.platform}:{title_id}", "hltb_match")
            try:
                await ensure_title_match(repo, args.platform, title_id)
            except Exception as exc:  # HLTB's bad minute: the next list
                print(f"  {title_id}: {exc!r}")
            if await repo.list_hltb_match(args.platform, title_id) is not None:
                matched += 1
            if n % 25 == 0:
                print(f"  {n}/{len(todo)}, matched {matched}")
        print(f"matched {matched} of {len(todo)}")
    finally:
        await database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
