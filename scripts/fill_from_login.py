"""Fill what only a login can read (#147; owner, 2026-10-16), through the
logins and keys of the bot whose schema `--auth-schema` is — the dev bot's,
never production's (a refreshed Xbox token there would log its person out
here and there).

1. **Achievement lists read whole** for the lists the catalog has no whole list
   of (`title_achievements.listed`): Xbox and 360 through the Xbox login, PSN
   through the NPSSO, Steam through the key — `TitleCatalogService`, forced, no
   translation (no Anthropic key is handed over).
2. **Titlehub's word on every Xbox list** (`StoreCollector.remember_title`):
   studio, publisher, day, genres for the stand-ins, and a 360 game's store
   product when its own mark names the game.

**The bot of `--auth-schema` must be stopped.** The database is copied into
`backups/` first.

    BOT_ENV_FILE=.env.test .venv/Scripts/python.exe -X utf8 -m scripts.fill_from_login \\
        --auth-schema test --schema dev [--limit 5] [--skip-catalog] [--skip-titlehub]
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from bot.config import get_settings
from bot.db import tools
from bot.db.repo import Repo
from bot.lock import AlreadyRunningError, single_instance
from bot.services import raw_answers
from bot.services.crypto import TokenCipher
from bot.services.psn.auth import PsnAuth
from bot.services.steam.auth import SteamAuth
from bot.services.store_collect import StoreCollector
from bot.services.title_catalog import TitleCatalogService
from bot.services.xbox.auth import XboxAuthService
from bot.services.xbox.client import XboxApiError, XboxClient


def _backup(schema: str | None) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    name = schema or get_settings().database_schema
    return tools.backup(Path("backups") / f"{name}-pre-login-fill-{stamp}.dump", schema=schema)


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    games = await tools.open_database(schema=args.schema)
    auth_db = await tools.open_database(schema=args.auth_schema)
    try:
        repo, auth_repo = Repo(games), Repo(auth_db)
        person = await auth_repo.any_active_xbox_person()
        print(f"Xbox login of person {person} (in {args.auth_schema})")
        print("database copied to", _backup(args.schema))
        cipher = TokenCipher(settings.fernet_key.get_secret_value())
        xbox_auth = XboxAuthService(settings, auth_repo, cipher)
        await xbox_auth.start()
        xbox = XboxClient(xbox_auth)
        key = settings.steam_api_key
        steam = SteamAuth(auth_repo, cipher, env_key=key.get_secret_value() if key else None)
        psn = PsnAuth(auth_repo, cipher)
        raw_answers.set_sink(repo.save_payload)
        try:
            if not args.skip_catalog:
                catalog = TitleCatalogService(
                    repo, xbox_client=xbox, psn_auth=psn, steam_auth=steam
                )
                for platform in ("xbox_modern", "xbox_360", "psn", "steam"):
                    todo = await repo.lists_without_whole_list(platform)
                    todo = todo[: args.limit] if args.limit else todo
                    filled = 0
                    for n, title_id in enumerate(todo, 1):
                        rows = await catalog.ensure_title_achievements_fresh(
                            platform,
                            title_id,
                            person_id=person if platform.startswith("xbox") else None,
                            force=True,
                        )
                        filled += bool(rows)
                        if n % 25 == 0:
                            print(f"  {platform}: {n}/{len(todo)}, with a list {filled}")
                    print(f"catalog {platform}: {filled} of {len(todo)} have a list now")
            if not args.skip_titlehub and person is not None:
                collector = StoreCollector(repo)
                for platform in ("xbox_modern", "xbox_360"):
                    todo = await repo.achievement_list_ids(platform)
                    todo = todo[: args.limit] if args.limit else todo
                    told = failed = 0
                    for n, title_id in enumerate(todo, 1):
                        try:
                            entry = await xbox.resolve_title(person, title_id)
                        except XboxApiError:
                            failed += 1
                            continue
                        if entry is not None:
                            await collector.remember_title(entry)
                            told += 1
                        if n % 100 == 0:
                            print(f"  titlehub {platform}: {n}/{len(todo)}, answered {told}")
                    print(f"titlehub {platform}: {told} of {len(todo)} answered, {failed} failed")
        finally:
            raw_answers.set_sink(None)
            await xbox_auth.close()
    finally:
        await auth_db.close()
        await games.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    tools.add_arguments(parser)
    parser.add_argument("--auth-schema", required=True, help="the schema whose logins are used")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip-catalog", action="store_true")
    parser.add_argument("--skip-titlehub", action="store_true")
    args = parser.parse_args()
    try:
        with single_instance(get_settings().db_path.parent / "bot.lock"):
            return tools.run(run(args))
    except AlreadyRunningError:
        print("that bot is running: stop it first (manage.ps1 stop -Test)")
        return 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)  # psnawp's limiter may keep a thread alive
