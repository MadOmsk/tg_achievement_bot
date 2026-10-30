"""A Steam game's poster and head kept current (owner, 2026-10-30)."""

from __future__ import annotations

import asyncio

import pytest

from bot.db.repo import Repo
from bot.services import game_page, steam_library_art
from bot.services.stores import StoreVersion, steam_store

ART = {
    "poster": "https://shared.steamstatic.com/p.jpg",
    "hero": "https://shared.steamstatic.com/h.jpg",
}


@pytest.mark.asyncio
async def test_opening_a_game_keeps_steam_art_of_now(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[list[str]] = []

    async def art(appids: list[str]) -> dict:
        asked.append(appids)
        return {"10": ART}

    async def on(repo: Repo) -> bool:
        return True

    monkeypatch.setattr(steam_store, "library_art", art)
    monkeypatch.setattr("bot.services.store_collect.collection_on", on)
    monkeypatch.setattr(steam_library_art, "_checked", {})
    await repo.save_version(
        StoreVersion(
            store="steam", product_id="10", console="steam",
            media={"cover": "https://shared.steamstatic.com/c.jpg"},
        ),
        platform=None,
        title_id=None,
    )  # fmt: skip
    versions = [dict(v) for v in await repo.versions_of_product("steam", "10")]
    steam_library_art.refresh_later(repo, versions)
    steam_library_art.refresh_later(repo, versions)  # asked lately: not again
    await asyncio.gather(*steam_library_art._tasks)
    assert asked == [["10"]]
    stored = await repo.versions_of_product("steam", "10")
    art_now = game_page.store_art(stored)
    assert (art_now["poster"], art_now["hero"]) == (ART["poster"], ART["hero"])

    # A re-parse of the kept answer, which has no library art, keeps it.
    await repo.save_version(
        StoreVersion(store="steam", product_id="10", console="steam", media={"cover": "x"}),
        platform=None,
        title_id=None,
    )
    assert (
        game_page.store_art(await repo.versions_of_product("steam", "10"))["poster"]
        == ART["poster"]
    )
