"""A game's Steam poster and head kept current (owner, 2026-10-30).

A live game changes its library art every season, and the store collection
asks again only every 7 to 90 days. So opening a game's page asks Steam for
the art of now (`steam_store.library_art`, one request for the game) in the
background, at most every `CHECK_HOURS` a game, and keeps it on the Steam
version (`versions.media` `poster` / `hero`): the next look — the page, a
favorite's card, a search hit — shows it. The page never waits for it, and it
waits for the store switch like every store request (`store_collect.collection_on`).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from bot.services.stores import steam_store

if TYPE_CHECKING:
    from bot.db.repo import Repo

log = logging.getLogger(__name__)

CHECK_HOURS = 6
_checked: dict[str, float] = {}
_tasks: set[asyncio.Task] = set()


def refresh_later(repo: Repo, versions: list[dict[str, Any]]) -> None:
    """Ask for the art of the game's Steam versions, when not asked lately."""
    now = time.monotonic()
    steam = {
        str(v["product_id"]): int(v["version_id"])
        for v in versions
        if v.get("store") == "steam" and not v.get("stand_in") and v.get("product_id")
    }
    due = {appid: vid for appid, vid in steam.items() if _checked.get(appid, 0) <= now}
    if not due:
        return
    for appid in due:
        _checked[appid] = now + CHECK_HOURS * 3600
    task = asyncio.create_task(_refresh(repo, due))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _refresh(repo: Repo, versions: dict[str, int]) -> None:
    from bot.services.store_collect import collection_on

    try:
        if not await collection_on(repo):
            return
        found = await steam_store.library_art(list(versions))
        for appid, art in found.items():
            if appid in versions:
                await repo.set_version_art(versions[appid], art)
    except Exception as exc:  # a picture never fails the page
        log.info("steam library art not refreshed: %r", exc)
