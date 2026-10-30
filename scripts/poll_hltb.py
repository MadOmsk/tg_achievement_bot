"""Read the HowLongToBeat pages the mirror lacks (#147; owner, 2026-10-15: a
full poll first, lazy reading later): every entry whose own page was never
read and that something of ours reaches — linked to a version or a DLC of ours,
or additional content of a game we have. Each page is kept as HLTB answered
(`source_payloads`) and read into the mirror (`hltb_entries` and its child
tables). One page every few seconds (`hltb_page.LIMITER`, the site's limit:
about 60 in five minutes), so ~1100 pages take about an hour and a half.

It stops after a few failures in a row (the site asking us to slow down), and can
be run again: it reads only what is still unread. The database is copied into
`backups/` first. **With the bot and the viewer stopped** (one process writes).

Usage:
    .venv/Scripts/python.exe -X utf8 -m scripts.poll_hltb --dry-run
    .venv/Scripts/python.exe -X utf8 -m scripts.poll_hltb --limit 20
    .venv/Scripts/python.exe -X utf8 -m scripts.poll_hltb
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from bot.config import get_settings
from bot.db import tools
from bot.db.repo import Repo
from bot.services.stores import hltb_page

logging.basicConfig(level="WARNING")
SOURCE = "hltb_page"


def _backup(schema: str | None) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    name = schema or get_settings().database_schema
    return tools.backup(Path("backups") / f"{name}-pre-hltb-poll-{stamp}.dump", schema=schema)


async def poll(repo: Repo, ids: list[int], *, stop_after: int) -> dict[str, int]:
    done = {"read": 0, "gone": 0, "failed": 0}
    in_a_row = 0
    started = time.monotonic()
    for n, hltb_id in enumerate(ids, 1):
        subject = f"hltb:{hltb_id}"
        try:
            data = await hltb_page.fetch_page(hltb_id)
        except Exception as exc:  # the site, the network: expected, never fatal to the loop
            done["failed"] += 1
            in_a_row += 1
            await repo.record_fetch(subject, SOURCE, status="error", error=repr(exc))
            print(f"  {hltb_id}: {exc!r}")
            if in_a_row >= stop_after:
                print(f"stopping: {in_a_row} failures in a row")
                break
            continue
        in_a_row = 0
        entry = hltb_page.parse_page(data) if data else None
        if entry is None:
            done["gone"] += 1
            await repo.record_fetch(subject, SOURCE, status="not_found")
            # No page of its own: not asked for again at once.
            await repo._conn.execute(
                "UPDATE hltb_entries SET page_read_at = checked_at WHERE hltb_id = ?", (hltb_id,)
            )
            await repo._conn.commit()
            continue
        changed = await repo.save_payload(subject, SOURCE, data)
        await repo.save_hltb_page(entry)
        await repo.record_fetch(subject, SOURCE, status="ok", changed=changed)
        done["read"] += 1
        if n % 25 == 0:
            rate = n / (time.monotonic() - started)
            print(f"  {n}/{len(ids)} ({rate * 60:.0f} a minute) {done}")
    return done


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    tools.add_arguments(parser)
    parser.add_argument("--limit", type=int, default=None, help="read at most this many")
    parser.add_argument("--dry-run", action="store_true", help="only count")
    parser.add_argument("--stop-after", type=int, default=5, help="failures in a row")
    args = parser.parse_args()
    database = await tools.open_database(schema=args.schema)
    try:
        repo = Repo(database)
        ids = await repo.hltb_pages_to_read(args.limit)
        print(f"{len(ids)} pages to read")
        if args.dry_run or not ids:
            return 0
        print("database copied to", _backup(args.schema))
        done = await poll(repo, ids, stop_after=args.stop_after)
        print("done:", done)
    finally:
        await database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(tools.run(main()))
