"""Name the Xbox achievement lists whose name was never learned (#147; owner,
2026-10-15), by asking titlehub about each title id through a login the
operator gave the bot whose schema `--auth-schema` is (the dev bot's, never
production's: a refresh here would log that person out there). Titlehub
describes any title to any login.

**That bot must be stopped**: Microsoft invalidates the previous refresh token
when it issues a new one, so two processes refreshing one person log them out.
This takes the bot's own lock (that of the env file) and refuses while it
runs. The database is copied into `backups/` first.

    BOT_ENV_FILE=.env.test .venv/Scripts/python.exe -X utf8 -m scripts.name_lists_by_titlehub \
        --auth-schema test --schema dev --dry-run
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from bot.config import get_settings
from bot.db import tools
from bot.db.repo import Repo
from bot.lock import AlreadyRunningError, single_instance
from bot.services.crypto import TokenCipher
from bot.services.xbox.auth import XboxAuthService
from bot.services.xbox.client import XboxApiError, XboxClient


def _backup(schema: str | None) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    name = schema or get_settings().database_schema
    return tools.backup(Path("backups") / f"{name}-pre-names-{stamp}.dump", schema=schema)


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    games = await tools.open_database(schema=args.schema)
    auth_db = await tools.open_database(schema=args.auth_schema)
    try:
        repo, auth_repo = Repo(games), Repo(auth_db)
        todo = await repo.unnamed_lists(("xbox_modern", "xbox_360"))
        person = await auth_repo.any_active_xbox_person()
        print(f"{len(todo)} Xbox lists with no name; login of person {person}")
        if args.dry_run or not todo or person is None:
            return 0
        print("database copied to", _backup(args.schema))
        auth = XboxAuthService(
            settings, auth_repo, TokenCipher(settings.fernet_key.get_secret_value())
        )
        await auth.start()
        client = XboxClient(auth)
        named = unanswered = failed = 0
        try:
            for n, (platform, title_id) in enumerate(todo, 1):
                try:
                    entry = await client.resolve_title(person, title_id)
                except XboxApiError as exc:
                    failed += 1
                    print(f"  {title_id}: {exc}")
                    continue
                if entry is None or not entry.name:
                    unanswered += 1
                    continue
                await repo.name_list(platform, title_id, entry.name)
                named += 1
                if n % 25 == 0:
                    print(f"  {n}/{len(todo)}, named {named}")
        finally:
            await auth.close()
        print(f"named {named}, titlehub had no name for {unanswered}, failed {failed}")
    finally:
        await auth_db.close()
        await games.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    tools.add_arguments(parser)
    parser.add_argument("--auth-schema", required=True, help="the schema whose logins are used")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        with single_instance(get_settings().db_path.parent / "bot.lock"):
            return tools.run(run(args))
    except AlreadyRunningError:
        print("that bot is running: stop it first (manage.ps1 stop -Test)")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
