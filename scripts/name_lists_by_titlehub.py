"""Name the Xbox achievement lists whose name was never learned (#147; owner,
2026-10-15), by asking titlehub about each title id through a login the
operator gave the bot whose database `--auth-db` is (the dev bot's, never
production's: a refresh here would log that person out there). Titlehub
describes any title to any login.

**That bot must be stopped**: Microsoft invalidates the previous refresh token
when it issues a new one, so two processes refreshing one person log them out.
This takes the bot's own lock beside `--auth-db` and refuses while it runs.
The games database is copied into `backups/` first.

    BOT_ENV_FILE=.env.test .venv/Scripts/python.exe -X utf8 -m scripts.name_lists_by_titlehub \
        --auth-db data/test.db --db data/games.db --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from bot.config import get_settings
from bot.db.repo import Database, Repo
from bot.lock import AlreadyRunningError, single_instance
from bot.services.crypto import TokenCipher
from bot.services.xbox.auth import XboxAuthService
from bot.services.xbox.client import XboxApiError, XboxClient


def _backup(db_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    target = Path("backups") / f"{db_path.stem}-pre-names-{stamp}.db"
    source = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    copy = sqlite3.connect(target)
    try:
        source.backup(copy)
    finally:
        copy.close()
        source.close()
    return target


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    games = await Database(Path(args.db)).connect()
    auth_db = await Database(Path(args.auth_db)).connect()
    try:
        repo, auth_repo = Repo(games), Repo(auth_db)
        todo = await repo.unnamed_lists(("xbox_modern", "xbox_360"))
        person = await auth_repo.any_active_xbox_person()
        print(f"{len(todo)} Xbox lists with no name; login of person {person}")
        if args.dry_run or not todo or person is None:
            return 0
        print("database copied to", _backup(Path(args.db)))
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
    parser.add_argument("--db", required=True, help="the games database to name lists in")
    parser.add_argument("--auth-db", required=True, help="the database whose Xbox login is used")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        with single_instance(Path(args.auth_db).parent / "bot.lock"):
            return asyncio.run(run(args))
    except AlreadyRunningError:
        print("that bot is running: stop it first (manage.ps1 stop -Test)")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
