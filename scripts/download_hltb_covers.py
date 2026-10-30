"""Download the pictures of HowLongToBeat entries to `data/covers/hltb/`
(#147; owner, 2026-10-15). One a second or so, the ones our versions are linked
to first; it can be stopped and run again, and an entry whose picture is gone is
stamped and not asked for again. With the bot and the viewer stopped.

    .venv/Scripts/python.exe -X utf8 -m scripts.download_hltb_covers --limit 20
"""

from __future__ import annotations

import argparse
import asyncio

from bot.config import get_settings
from bot.db import tools
from bot.db.repo import Repo
from bot.services import covers, images, media

PAUSE_SECONDS = 1.0
# The site answers a bare client with 403; a browser's name and a referrer pass.
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://howlongtobeat.com/"}


def _suffix(url: str) -> str:
    tail = url.rsplit(".", 1)[-1].lower()
    return "." + tail if tail in {"png", "jpg", "jpeg", "webp", "gif"} else ".jpg"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    tools.add_arguments(parser)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    media.configure(get_settings().media_dir)
    directory = covers.cover_dir() / "hltb"
    database = await tools.open_database(schema=args.schema)
    try:
        repo = Repo(database)
        todo = await repo.hltb_covers_to_fetch(args.limit)
        print(f"{len(todo)} pictures to fetch")
        got = 0
        for n, (hltb_id, url) in enumerate(todo, 1):
            name = images.safe_name(str(hltb_id), suffix=_suffix(url))
            saved = await images.download(url, name, directory, headers=HEADERS)
            if saved:
                got += 1
            await repo.set_hltb_cover(
                hltb_id, f"hltb/{saved[0]}" if saved else None, saved[1] if saved else None
            )
            if n % 50 == 0:
                print(f"  {n}/{len(todo)}, saved {got}")
            await asyncio.sleep(PAUSE_SECONDS)
        print(f"done: {got} saved of {len(todo)}")
    finally:
        await database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(tools.run(main()))
