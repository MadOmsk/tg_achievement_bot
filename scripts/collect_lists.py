"""Collect many achievement lists from the stores and HLTB, one after
another (#147; owner, 2026-10-16) — `scripts/collect_game.py` for a whole
platform. `--stand-ins`: only the lists no store product describes yet (after
their names were found, a search by name may find them now). `--no-link`
leaves the games as they are (an operator reviewing them). The database is
copied into `backups/` first.

    BOT_ENV_FILE=.env.test .venv/Scripts/python.exe -X utf8 -m scripts.collect_lists \
        --db data/games.db --platform xbox_modern --stand-ins --force --no-link
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from bot.config import get_settings
from bot.db.repo import Database, Repo
from bot.services.crypto import TokenCipher
from bot.services.psn.auth import PsnAuth
from bot.services.steam.auth import SteamAuth
from bot.services.store_collect import StoreCollector

logging.basicConfig(level="WARNING")


def _backup(db_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    target = Path("backups") / f"{db_path.stem}-pre-collect-{stamp}.db"
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
    parser.add_argument("--platform", required=True)
    parser.add_argument("--stand-ins", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-link", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    settings = get_settings()
    db_path = Path(args.db)
    database = await Database(db_path).connect()
    try:
        repo = Repo(database)
        lists = (
            await repo.stand_in_lists(args.platform)
            if args.stand_ins
            else await repo.achievement_list_ids(args.platform)
        )[: args.limit]
        print(f"{len(lists)} {args.platform} lists")
        print("database copied to", _backup(db_path))
        cipher = TokenCipher(settings.fernet_key.get_secret_value())
        key = settings.steam_api_key
        collector = StoreCollector(
            repo,
            PsnAuth(repo, cipher),
            SteamAuth(repo, cipher, env_key=key.get_secret_value() if key else None),
        )
        before = len(await repo.stand_in_lists(args.platform)) if args.stand_ins else 0
        errors = 0
        for n, title_id in enumerate(lists, 1):
            try:
                report = await collector.collect(
                    args.platform, title_id, force=args.force, link=not args.no_link
                )
                errors += bool(report.errors)
            except Exception as exc:  # one list's bad minute: the next one
                errors += 1
                print(f"  {title_id}: {exc!r}")
            if n % 25 == 0:
                left = len(await repo.stand_in_lists(args.platform)) if args.stand_ins else 0
                print(
                    f"  {n}/{len(lists)}, errors {errors}"
                    + (f", stand-ins left {left}" if args.stand_ins else "")
                )
        if args.stand_ins:
            left = len(await repo.stand_in_lists(args.platform))
            print(f"done: {before - left} of {len(lists)} found a store product; errors {errors}")
        else:
            print(f"done; errors {errors}")
    finally:
        await database.close()
    return 0


if __name__ == "__main__":
    code = asyncio.run(main())
    sys.stdout.flush()
    os._exit(code)  # psnawp's limiter may keep a thread alive
