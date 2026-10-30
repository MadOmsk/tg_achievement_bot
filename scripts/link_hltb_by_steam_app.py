"""Link the Steam versions to the HowLongToBeat entries whose pages name
their app (#147; owner, 2026-10-15) — the surest evidence there is; the lazy
match never ran for a Steam list nobody published in. Nothing that has a link
(or a refusal) is touched. The database is copied into `backups/` first.

    .venv/Scripts/python.exe -X utf8 -m scripts.link_hltb_by_steam_app --dry-run
    .venv/Scripts/python.exe -X utf8 -m scripts.link_hltb_by_steam_app
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from bot.config import get_settings
from bot.db import tools
from bot.db.repo import Repo
from bot.services.store_collect import link_steam_apps_to_hltb


def _backup(schema: str | None) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    name = schema or get_settings().database_schema
    return tools.backup(Path("backups") / f"{name}-pre-steam-hltb-{stamp}.dump", schema=schema)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    tools.add_arguments(parser)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    database = await tools.open_database(schema=args.schema)
    try:
        repo = Repo(database)
        if args.dry_run:
            rows = await repo.steam_versions_with_hltb_by_app()
            print(f"{len({r['version_id'] for r in rows})} Steam versions have a candidate")
            return 0
        print("database copied to", _backup(args.schema))
        print(await link_steam_apps_to_hltb(repo))
    finally:
        await database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(tools.run(main()))
