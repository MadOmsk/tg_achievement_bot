"""Every Steam version's library art of now — its poster and head — asked of
Steam once, a hundred apps a request (owner, 2026-10-30). What the store
collection and an opened game page keep current from then on
(`services/steam_library_art.py`). Safe beside a running bot.

    python scripts/steam_library_art.py [--db data/bot.db]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import get_settings
from bot.db.files import open_database
from bot.db.repo import Repo
from bot.services.stores import steam_store


async def main(db: str) -> None:
    database = await open_database(db)
    repo = Repo(database)
    try:
        cursor = await repo._conn.execute(
            "SELECT version_id, product_id FROM versions"
            " WHERE store = 'steam' AND COALESCE(stand_in, 0) = 0"
        )
        versions = {
            str(row["product_id"]): int(row["version_id"]) for row in await cursor.fetchall()
        }
        print(f"{len(versions)} Steam versions")
        found = await steam_store.library_art(list(versions))
        for appid, art in found.items():
            await repo.set_version_art(versions[appid], art)
        print(f"art kept for {len(found)}")
    finally:
        await database.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None)
    args = parser.parse_args()
    asyncio.run(main(args.db or get_settings().db_path))
