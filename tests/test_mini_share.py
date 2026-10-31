"""A shared post's link carries its card for a messenger (owner, 2026-10-30)."""

from __future__ import annotations

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.db.repo import Repo
from bot.db.repo._steam import StoredPatch
from bot.web.mini_api import setup_mini_api


@pytest.mark.asyncio
async def test_a_shared_post_has_its_card_and_leads_to_the_app(repo: Repo, settings) -> None:
    await repo.save_game_patches(
        10,
        [
            StoredPatch(
                gid="5", title="Live Update 2.3.0", published_at="2026-10-30T00:00:00Z",
                text_en="Fixed a crash.", title_ru=None, text_ru=None,
                image_url="https://clan.steamstatic.com/p.jpg",
            )
        ],
    )  # fmt: skip
    await repo.set_patch_translation(
        10, "5", of=("Live Update 2.3.0", "Fixed a crash."),
        title_ru="Обновление 2.3.0", text_ru="Исправлен вылет.",
    )  # fmt: skip
    app = web.Application()
    setup_mini_api(app, settings, repo)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        page = await (await client.get("/api/mini/share/news/10/5?b=/app/")).text()
        assert '<meta property="og:title" content="Обновление 2.3.0">' in page
        assert '<meta property="og:description" content="Исправлен вылет.">' in page
        assert '<meta property="og:image" content="https://clan.steamstatic.com/p.jpg">' in page
        assert 'url=/app/?n=10%3A5"' in page
        # Never another site's address as the way on.
        page = await (await client.get("/api/mini/share/news/10/5?b=//evil.example/")).text()
        assert 'url=/?n=10%3A5"' in page
        assert (await client.get("/api/mini/share/news/10/404")).status == 404
    finally:
        await client.close()
