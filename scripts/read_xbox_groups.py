"""Read each Xbox list once on contract 6 to learn its achievements' groups —
`base`, the list it shipped with, or `non_base`, added later (#147; owner,
2026-10-15) — through a login the operator gave the bot whose schema
`--auth-schema` is (never production's: a refresh here logs that person out
there). The answers are kept whole (`xbox_achievements`). **That bot must be
stopped.** The database is copied into `backups/` first.

    BOT_ENV_FILE=.env.test .venv/Scripts/python.exe -X utf8 -m scripts.read_xbox_groups \
        --auth-schema test --schema dev --limit 5
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from bot.config import get_settings
from bot.db import tools
from bot.db.repo import Repo
from bot.lock import AlreadyRunningError, single_instance
from bot.services import raw_answers
from bot.services.crypto import TokenCipher
from bot.services.xbox.auth import XboxAuthService
from bot.services.xbox.client import PAGE_SIZE, XboxApiError, XboxClient
from bot.services.xbox.models import xbox_group


def _backup(schema: str | None) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    name = schema or get_settings().database_schema
    return tools.backup(Path("backups") / f"{name}-pre-xbox-groups-{stamp}.dump", schema=schema)


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    games = await tools.open_database(schema=args.schema)
    auth_db = await tools.open_database(schema=args.auth_schema)
    try:
        repo = Repo(games)
        todo = await repo.achievement_list_ids("xbox_modern")
        if args.limit:
            todo = todo[: args.limit]
        person = await Repo(auth_db).any_active_xbox_person()
        print(f"{len(todo)} Xbox lists; login of person {person}")
        if person is None:
            return 1
        print("database copied to", _backup(args.schema))
        raw_answers.set_sink(repo.save_payload)
        auth = XboxAuthService(
            settings, Repo(auth_db), TokenCipher(settings.fernet_key.get_secret_value())
        )
        await auth.start()
        client = XboxClient(auth)
        grouped = empty = failed = 0
        try:
            for n, title_id in enumerate(todo, 1):
                groups: dict[str, str] = {}
                params = {"titleId": title_id, "maxItems": str(PAGE_SIZE)}
                try:
                    for _ in range(20):
                        payload = await client._get_achievements(person, "6", params)
                        for item in payload.get("achievements") or []:
                            group = xbox_group(item.get("groupIds"))
                            if group and item.get("id") is not None:
                                groups[str(item["id"])] = group
                        token = (payload.get("pagingInfo") or {}).get("continuationToken")
                        if not token:
                            break
                        params = {**params, "continuationToken": token}
                except XboxApiError as exc:
                    failed += 1
                    print(f"  {title_id}: {exc}")
                    continue
                if groups:
                    await repo.set_achievement_groups("xbox_modern", title_id, groups)
                    grouped += 1
                else:
                    empty += 1
                if n % 50 == 0:
                    print(f"  {n}/{len(todo)}, grouped {grouped}")
        finally:
            raw_answers.set_sink(None)
            await auth.close()
        print(f"grouped {grouped}, no achievements in the answer {empty}, failed {failed}")
    finally:
        await auth_db.close()
        await games.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    tools.add_arguments(parser)
    parser.add_argument("--auth-schema", required=True, help="the schema whose logins are used")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    try:
        with single_instance(get_settings().db_path.parent / "bot.lock"):
            return tools.run(run(args))
    except AlreadyRunningError:
        print("that bot is running: stop it first (manage.ps1 stop -Test)")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
