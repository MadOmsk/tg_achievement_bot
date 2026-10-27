"""Editions' pictures (#147; owner, 2026-10-15: editions have covers of their
own, kept where they belong, every platform). Reads each edition's pictures
from the answers already kept — Xbox's bundle products, PSN's product pages —
asks Steam for the packages whose answer was not kept before, and downloads
each edition's cover to `data/covers/editions/`. Can be stopped and run again.
The database is copied into `backups/` first.

    .venv/Scripts/python.exe -X utf8 -m scripts.edition_media
    .venv/Scripts/python.exe -X utf8 -m scripts.edition_media --no-steam --no-download
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from bot.db.repo import Database, Repo
from bot.services import edition_media, images
from bot.services.stores import psn_product, steam_store, xbox_catalog

logging.basicConfig(level="WARNING")
PAUSE_SECONDS = 0.5


def _backup(db_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    target = Path("backups") / f"{db_path.stem}-pre-edition-media-{stamp}.db"
    source = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    copy = sqlite3.connect(target)
    try:
        source.backup(copy)
    finally:
        copy.close()
        source.close()
    return target


async def from_kept(repo: Repo) -> dict[str, int]:
    """Xbox's and PSN's editions, from the answers already kept: no request."""
    done = {"xbox": 0, "psn": 0}
    xbox_ids = await repo.edition_ids("xbox")
    seen: set[str] = set()
    for subject in await repo.payload_subjects("xbox_catalog", ""):
        kept = await repo.payload(subject, "xbox_catalog") or []
        if isinstance(kept, dict):  # an add-ons answer: its editions and add-ons
            kept = [*(kept.get("editions") or []), *(kept.get("addons") or [])]
        for product in kept:
            if not isinstance(product, dict):
                continue
            big_id = str(product.get("ProductId") or "")
            if big_id in xbox_ids and big_id not in seen and xbox_catalog.bundle_items(product):
                seen.add(big_id)
                done["xbox"] += await repo.set_edition_media(
                    "xbox", big_id, edition_media.xbox(product)
                )
    for product_id in await repo.edition_ids("psn"):
        payload = await repo.payload(f"psn_product:{product_id}", "psn_product")
        if payload:
            media = edition_media.psn(psn_product._products(payload))
            done["psn"] += await repo.set_edition_media("psn", product_id, media)
    return done


async def steam_packages(repo: Repo) -> dict[str, int]:
    """Steam's packages whose answer was not kept: asked again, kept now."""
    done = {"asked": 0, "kept": 0, "failed": 0}
    for package_id in sorted(await repo.edition_ids("steam")):
        subject = f"steam_package:{package_id}"
        package = await repo.payload(subject, "steam_package")
        if package is None:
            done["asked"] += 1
            try:
                package = await steam_store.package(package_id)
            except Exception as exc:  # Steam's bad minute: the next one
                done["failed"] += 1
                print(f"  package {package_id}: {exc!r}")
                continue
            if package is None:
                continue
            await repo.save_payload(subject, "steam_package", package)
        done["kept"] += await repo.set_edition_media(
            "steam", package_id, edition_media.steam(package)
        )
    return done


async def download(repo: Repo, root: Path) -> dict[str, int]:
    """Each edition's cover on disk, once: found or not, it is stamped."""
    directory = root / "covers" / "editions"
    done = {"saved": 0, "missing": 0}
    for row in await repo.edition_covers_to_fetch():
        url = edition_media.cover_url(json.loads(row["media"] or "{}"))
        saved = None
        if url:
            suffix = "." + url.rsplit(".", 1)[-1].split("?")[0].lower()
            suffix = suffix if suffix in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"
            name = images.safe_name(str(row["store"]), str(row["store_id"]), suffix=suffix)
            saved = await images.download(url, name, directory)
            await asyncio.sleep(PAUSE_SECONDS)
        await repo.set_edition_cover(
            int(row["edition_id"]),
            f"editions/{saved[0]}" if saved else None,
            saved[1] if saved else None,
        )
        done["saved" if saved else "missing"] += 1
        if sum(done.values()) % 200 == 0:
            print(f"  covers: {done}")
    return done


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", default=None)
    parser.add_argument("--no-steam", action="store_true", help="do not ask Steam")
    parser.add_argument("--no-download", action="store_true", help="do not download covers")
    args = parser.parse_args()
    if args.db:
        db_path = Path(args.db)
    else:
        from bot.config import get_settings

        db_path = Path(get_settings().db_path)
    database = await Database(db_path).connect()
    try:
        repo = Repo(database)
        print("database copied to", _backup(db_path))
        print("from what is kept:", await from_kept(repo))
        if not args.no_steam:
            print("steam packages:", await steam_packages(repo))
        if not args.no_download:
            print("covers:", await download(repo, db_path.resolve().parent))
    finally:
        await database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
