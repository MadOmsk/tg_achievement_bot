"""The octopus's queue worked through (#204, #215): entries put in the queue,
then each one's game assembled whole (`services/octopus.py`). Resumable: the
queue is in the database, and a game assembled is assembled again only when
due; `--force` asks everything again. The database is copied into `backups/`
first.

    BOT_ENV_FILE=…/.env.games .venv/Scripts/python.exe -X utf8 -m scripts.octopus \\
        --schema dev --auth-schema dev --seed game:4070
    … --seed list:psn:NPWR12345_00 --seed product:steam:620 --seed dlc:77 \\
      --seed achievement:steam:620:ACH.WAKE_UP --seed hltb:10270 --seed "name:Dead Rising"
    … --seed edition:42 --seed series:7 --seed account:psn:<account id> \\
      --seed https://store.steampowered.com/app/620/ --seed storeid:psn_title:CUSA08455_00
    … --which singles|stand-ins|all [--limit 50]
    … (no seed: only what is already in the queue)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from bot.config import get_settings
from bot.db import tools
from bot.db.repo import Repo
from bot.services import raw_answers
from bot.services.crypto import TokenCipher
from bot.services.octopus import OctopusCollector, entry_key, game_key
from bot.services.psn.auth import PsnAuth
from bot.services.steam.auth import SteamAuth
from bot.services.store_collect import StoreCollector

logging.basicConfig(level="WARNING")


def _backup(schema: str | None) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    name = schema or get_settings().database_schema
    return tools.backup(Path("backups") / f"{name}-pre-octopus-{stamp}.dump", schema=schema)


def _seed_key(seed: str) -> str:
    """A key, a store or HLTB link, or a name (`octopus.entry_key`)."""
    key = entry_key(seed)
    if key is None:
        raise SystemExit(f"--seed {seed!r}: a key (kind:value), a store or HLTB link, or a name")
    return key


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    tools.add_arguments(parser)
    parser.add_argument("--seed", action="append", default=[], help="kind:value, see above")
    parser.add_argument("--which", choices=["all", "singles", "stand-ins"])
    parser.add_argument("--limit", type=int, default=None, help="entries handled at most")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--auth-schema",
        help="the schema whose PSN and Steam keys are used (the dev bot's; never production's)",
    )
    args = parser.parse_args()
    settings = get_settings()
    print("database copied to", _backup(args.schema))
    database = await tools.open_database(schema=args.schema)
    keys_db = None
    try:
        repo = Repo(database)
        raw_answers.set_sink(repo.save_payload)
        cipher = TokenCipher(settings.fernet_key.get_secret_value())
        key = settings.steam_api_key
        keys_repo = repo
        if args.auth_schema:
            # Opened as it is: no bring-up of another bot's schema.
            keys_db = await tools.open_database(schema=args.auth_schema)
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
        if keys_db is not None:
            await keys_db.close()
        await database.close()
    return 0


if __name__ == "__main__":
    code = tools.run(main())
    sys.stdout.flush()
    os._exit(code)  # psnawp's limiter may keep a thread alive
