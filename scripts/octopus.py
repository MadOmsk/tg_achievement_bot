"""The octopus's queue worked through (#204, #215): entries put in the queue,
then each one's game assembled whole (`services/octopus.py`). Resumable: the
queue is in the database, and a game assembled is assembled again only when
due; `--force` asks everything again. The database is copied into `backups/`
first.

    BOT_ENV_FILE=…/.env.games .venv/Scripts/python.exe -X utf8 -m scripts.octopus \\
        --db data/games.db --auth-db data/games-bot.db --seed game:4070
    … --seed list:psn:NPWR12345_00 --seed product:steam:620 --seed dlc:77 \\
      --seed achievement:steam:620:ACH.WAKE_UP --seed hltb:10270 --seed "name:Dead Rising"
    … --which singles|stand-ins|all [--limit 50]
    … (no seed: only what is already in the queue)
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
from bot.services.octopus import KINDS, OctopusCollector, game_key, search_key
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


def _seed_key(seed: str) -> str:
    kind, _, value = seed.partition(":")
    if kind not in KINDS or not value:
        raise SystemExit(f"--seed {seed!r}: one of {', '.join(KINDS)}, then ':' and a value")
    return search_key(value) if kind == "name" else seed


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", required=True)
    parser.add_argument("--seed", action="append", default=[], help="kind:value, see above")
    parser.add_argument("--which", choices=["all", "singles", "stand-ins"])
    parser.add_argument("--limit", type=int, default=None, help="entries handled at most")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--auth-db",
        help="the database whose PSN and Steam keys are used (the dev bot's; never production's)",
    )
    args = parser.parse_args()
    settings = get_settings()
    db_path = Path(args.db)
    print("database copied to", _backup(db_path))
    database = await Database(db_path).connect()
    keys_db: Database | None = None
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
        seeds = [_seed_key(s) for s in args.seed]
        if args.which:
            seeds += [game_key(g) for g in await repo.game_ids_for_sweep(args.which)]
        added = sum([await octopus.enqueue(s, reason="seed") for s in seeds])
        print(f"queued {added} new of {len(seeds)} seeds; waiting {await repo.octopus_waiting()}")
        report = await octopus.run(limit=args.limit, force=args.force)
        for game in report.games:
            print(
                f"{game.entry} → game {game.game_id} {game.name!r}: versions"
                f" {game.versions_before} → {game.versions_after} in {game.rounds} rounds,"
                f" found {len(set(game.found))}, to review {game.review};"
                f" stand-ins {game.stand_ins}, HLTB on {game.hltb} versions"
                + (f"; errors {len(game.errors)}" if game.errors else "")
            )
        print(
            f"handled {report.handled}: games {len(report.games)}, not due {report.skipped},"
            f" led nowhere {report.gone}, queued on the way {report.queued}"
        )
        for line in report.failed[:20]:
            print("  error:", line)
        lone = await repo.lone_versions()
        print(
            f"left in the queue: {await repo.octopus_waiting()}; versions in no game: {len(lone)}"
        )
    finally:
        raw_answers.set_sink(None)
        if keys_db is not None and keys_db._conn is not None:
            await keys_db._conn.close()
        await database.close()
    return 0


if __name__ == "__main__":
    code = asyncio.run(main())
    sys.stdout.flush()
    os._exit(code)  # psnawp's limiter may keep a thread alive
