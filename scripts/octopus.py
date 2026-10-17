"""The octopus sweep (#204): games looked for in every store, one after
another (`services/octopus.py`), then the checks of step 12. Resumable: a game
done is stamped (`fetch_state`, source `octopus`) and skipped while not due;
`--force` asks everything again. The database is copied into `backups/` first.

    BOT_ENV_FILE=.env.test .venv/Scripts/python.exe -X utf8 -m scripts.octopus \\
        --db data/games.db --game 4070
    … --which singles|stand-ins|all [--limit 50] [--no-link]
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
from bot.services import raw_answers
from bot.services.crypto import TokenCipher
from bot.services.octopus import SOURCE, OctopusCollector
from bot.services.psn.auth import PsnAuth
from bot.services.steam.auth import SteamAuth
from bot.services.store_collect import StoreCollector

logging.basicConfig(level="WARNING")


def _backup(db_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    target = Path("backups") / f"{db_path.stem}-pre-octopus-{stamp}.db"
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
    parser.add_argument("--game", type=int, action="append")
    parser.add_argument("--which", choices=["all", "singles", "stand-ins"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-link", action="store_true", help="leave the games as they are")
    parser.add_argument(
        "--auth-db",
        help="the database whose PSN and Steam keys are used (the dev bot's; never production's)",
    )
    args = parser.parse_args()
    if not args.game and not args.which:
        parser.error("--game or --which")
    settings = get_settings()
    db_path = Path(args.db)
    print("database copied to", _backup(db_path))
    database = await Database(db_path).connect()
    try:
        repo = Repo(database)
        raw_answers.set_sink(repo.save_payload)
        cipher = TokenCipher(settings.fernet_key.get_secret_value())
        key = settings.steam_api_key
        keys_repo = repo
        if args.auth_db:
            # Opened as it is: no schema, no migration of another bot's file.
            import aiosqlite

            keys_db = Database(Path(args.auth_db))
            keys_db._conn = await aiosqlite.connect(args.auth_db)
            keys_db._conn.row_factory = aiosqlite.Row
            keys_repo = Repo(keys_db)
        collector = StoreCollector(
            repo,
            PsnAuth(keys_repo, cipher),
            SteamAuth(keys_repo, cipher, env_key=key.get_secret_value() if key else None),
        )
        octopus = OctopusCollector(repo, collector)
        games = args.game or await repo.game_ids_for_sweep(args.which)
        done = 0
        for game_id in games:
            if args.limit is not None and done >= args.limit:
                break
            if (
                not args.force
                and not args.game
                and not await repo.fetch_due(f"game:{game_id}", SOURCE)
            ):
                continue
            report = await octopus.game(game_id, force=args.force, link=not args.no_link)
            done += 1
            print(
                f"game {game_id} {report.name!r}: lists {report.lists},"
                f" versions {report.versions_before} → {report.versions_after},"
                f" found {len(set(report.found))}, psn pages {report.psn_pages},"
                f" hltb spread {report.hltb_spread}"
                + (f", errors {len(report.errors)}" if report.errors else "")
            )
        lone = await repo.lone_versions()
        print(f"{done} games; versions in no game: {len(lone)}")
    finally:
        raw_answers.set_sink(None)
        await database.close()
    return 0


if __name__ == "__main__":
    code = asyncio.run(main())
    sys.stdout.flush()
    os._exit(code)  # psnawp's limiter may keep a thread alive
