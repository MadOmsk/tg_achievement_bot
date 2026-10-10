"""Collect what the stores and HLTB say about one game, now (#147, stage 2) —
the manual way in while collecting is being tuned. The bot does the same by
itself when a game's first new achievement is published or its page is
opened, and only when something is due; `--force` asks regardless.

Safe beside a running bot: no Xbox login is used (the catalog is public),
the PSN client is this process's own, every write is a single statement.

Usage:
    .venv/Scripts/python.exe -X utf8 -m scripts.collect_game steam 292030
    .venv/Scripts/python.exe -X utf8 -m scripts.collect_game xbox_modern 1799887933 --force
    .venv/Scripts/python.exe -X utf8 -m scripts.collect_game psn NPWR07207_00
    .venv/Scripts/python.exe -X utf8 -m scripts.collect_game --name "Skyrim" --name "Fallout 4"
    (the test server: BOT_ENV_FILE=.env.test …)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from bot.config import get_settings
from bot.db.repo import Database, Repo
from bot.services.crypto import TokenCipher
from bot.services.psn.auth import PsnAuth
from bot.services.steam.auth import SteamAuth
from bot.services.store_collect import StoreCollector

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-7s %(message)s")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("platform", nargs="?", choices=("steam", "xbox_modern", "xbox_360", "psn"))
    parser.add_argument("title_id", nargs="?")
    parser.add_argument(
        "--name", action="append", help="collect a game by its name on every store (repeatable)"
    )
    parser.add_argument("--force", action="store_true", help="ask even what is not due")
    args = parser.parse_args()

    settings = get_settings()
    database = await Database(Path(settings.db_path)).connect()
    repo = Repo(database)
    cipher = TokenCipher(settings.fernet_key.get_secret_value())
    psn = PsnAuth(repo, cipher)
    key = settings.steam_api_key
    steam = SteamAuth(repo, cipher, env_key=key.get_secret_value() if key else None)
    collector = StoreCollector(repo, psn, steam)
    if args.name:
        for name in args.name:
            found = await collector.collect_name(name)
            print(
                f"{name}: versions {len(set(found.versions))}, dlc {found.dlcs},"
                f" games {found.games}, to review {found.review}"
                + (f", errors {found.errors}" if found.errors else "")
            )
        await database.close()
        return 0
    if not args.platform or not args.title_id:
        parser.error("a platform and a title id, or --name")
    report = await collector.collect(args.platform, args.title_id, force=args.force)

    print(f"asked:   {', '.join(report.asked) or '—'}")
    print(f"skipped: {', '.join(report.skipped) or '—'} (not due; --force asks anyway)")
    print(f"errors:  {'; '.join(report.errors) or '—'}")
    for version in await repo.versions_of_title(args.platform, args.title_id):
        print(
            f"version {version['version_id']}: {version['store']} {version['product_id']}"
            f" [{version['console']}] {version['name']} · {version['developer']} /"
            f" {version['publisher']} · {version['release_date']}"
            f" · also on {json.loads(version['also_on'] or '[]')}"
        )
    print(f"dlc named this pass: {report.dlcs}; hltb: {report.hltb_id}")
    await database.close()
    return 0


if __name__ == "__main__":
    code = asyncio.run(main())
    # psnawp's limiter may keep a thread alive; nothing is left to wait for.
    os._exit(code)
