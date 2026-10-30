"""Mark each Xbox account's Mythic and completion of every game it played,
from what is stored (#147; owner, 2026-10-16): the earned row that finished the
game's base list is `mythic`, the one that finished its whole list
`completes` (`repo.mark_xbox_completions`). No request; marks once.

    .venv/Scripts/python.exe -X utf8 -m scripts.mark_completions --schema dev
"""

from __future__ import annotations

import argparse

from bot.db import tools
from bot.db.repo import Repo


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    tools.add_arguments(parser)
    args = parser.parse_args()
    database = await tools.open_database(schema=args.schema)
    try:
        repo = Repo(database)
        for platform in ("xbox_modern", "xbox_360"):
            for title_id in await repo.achievement_list_ids(platform):
                await repo.mark_xbox_completions_of_title(platform, title_id)
        print(await repo.completion_marks())
    finally:
        await database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(tools.run(main()))
