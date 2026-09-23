"""Batch pre-caching of achievement icons into data/achievements/ (#99, owner request 2026-09-23).

Reads achievement icon URLs from `title_achievements` and `seen_achievements`,
checks which icons are missing on disk, and downloads them.

Usage:
    .venv/bin/python -m scripts.cache_achievement_icons --dry-run
    .venv/bin/python -m scripts.cache_achievement_icons --platform xbox_360
    .venv/bin/python -m scripts.cache_achievement_icons --limit 100
    .venv/bin/python -m scripts.cache_achievement_icons
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from bot.config import get_settings
from bot.db.repo import Database, Repo
from bot.services import achievement_icons

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", stream=sys.stdout
)
log = logging.getLogger("cache_achievement_icons")


async def run() -> None:
    parser = argparse.ArgumentParser(description="Pre-cache achievement icons to disk.")
    parser.add_argument(
        "--platform",
        type=str,
        default=None,
        help="Filter by platform (xbox_modern, xbox_360, steam, psn)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of missing icons to download",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Concurrent download limit (default 5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only scan and report counts without downloading",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Custom SQLite db path",
    )
    args = parser.parse_args()

    settings = get_settings()
    db_path = Path(args.db) if args.db else settings.db_path
    if not db_path.is_file():
        log.error("Database not found at %s", db_path)
        sys.exit(1)

    database = await Database(db_path).connect()
    repo = Repo(database)

    try:
        # Collect distinct (platform, title_id, achievement_id, icon_url)
        where_ta = "WHERE icon_url IS NOT NULL AND icon_url != ''"
        where_sa = "WHERE icon_url IS NOT NULL AND icon_url != ''"
        params_ta: list[str] = []
        params_sa: list[str] = []
        if args.platform:
            where_ta += " AND platform = ?"
            where_sa += " AND platform = ?"
            params_ta.append(args.platform)
            params_sa.append(args.platform)

        query = f"""
            SELECT platform, title_id, achievement_id, icon_url FROM (
                SELECT platform, title_id, achievement_id, icon_url
                FROM title_achievements {where_ta}
                UNION
                SELECT platform, title_id, achievement_id, icon_url
                FROM seen_achievements {where_sa}
            )
        """
        params = params_ta + params_sa
        cursor = await repo._conn.execute(query, tuple(params))
        all_rows = await cursor.fetchall()
        total = len(all_rows)
        log.info("Found %d distinct achievements with icon_url in database.", total)

        missing: list[tuple[str, str, str, str]] = []
        already_cached = 0

        for row in all_rows:
            plat = row["platform"]
            tid = str(row["title_id"])
            aid = str(row["achievement_id"])
            url = row["icon_url"]

            if achievement_icons.find_cached_icon(plat, tid, aid) is not None:
                already_cached += 1
            else:
                missing.append((plat, tid, aid, url))

        log.info("Already cached on disk: %d / %d", already_cached, total)
        log.info("Missing on disk: %d", len(missing))

        if args.dry_run:
            log.info("Dry-run requested, exiting without downloading.")
            return

        to_download = missing[: args.limit] if args.limit else missing
        log.info(
            "Starting download of %d icons (concurrency=%d)...",
            len(to_download),
            args.concurrency,
        )

        sem = asyncio.Semaphore(args.concurrency)
        success = 0
        failed = 0

        async def _fetch_one(plat: str, tid: str, aid: str, url: str) -> None:
            nonlocal success, failed
            async with sem:
                res = await achievement_icons.get_or_download_achievement_icon(
                    repo, plat, tid, aid, url=url
                )
                if res is not None:
                    success += 1
                else:
                    failed += 1

        tasks = [_fetch_one(p, t, a, u) for p, t, a, u in to_download]
        await asyncio.gather(*tasks)

        log.info("Finished: %d succeeded, %d failed.", success, failed)
    finally:
        await database.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
