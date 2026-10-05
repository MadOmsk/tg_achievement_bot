"""Tests for Xbox 360 achievement rarity, authentic icons, and proxying."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.db.repo import AchievementRow
from bot.poller.fetcher import Fetcher
from bot.poller.publisher import _gallery
from bot.services.models import ParsedAchievement, Platform
from bot.views.notification import format_digest, format_single
from bot.web.mini_api import _X360_ICON_CACHE, handle_x360_icon
from bot.web.mini_chat import _https_url


def test_https_url_translates_x360_cdn() -> None:
    # Standard Xbox 360 icon URL
    url = "http://image.xboxlive.com/global/t.584109cb/ach/0/3"
    assert _https_url(url) == "/api/mini/x360-icon/584109cb/3"

    url_png = "http://image.xboxlive.com/global/t.584109cb/ach/0/1a.png"
    assert _https_url(url_png) == "/api/mini/x360-icon/584109cb/1a"

    # Generic http -> https upgrade
    assert (
        _https_url("http://images-eds.xboxlive.com/boxart.png")
        == "https://images-eds.xboxlive.com/boxart.png"
    )
    assert (
        _https_url("https://images-eds.xboxlive.com/boxart.png")
        == "https://images-eds.xboxlive.com/boxart.png"
    )
    assert _https_url(None) is None


async def test_handle_x360_icon_success_and_cache(tmp_path: Path, monkeypatch) -> None:
    fake_dir = tmp_path / "achievements"
    monkeypatch.setattr("bot.services.achievement_icons.ACHIEVEMENTS_DIR", fake_dir)
    _X360_ICON_CACHE.clear()

    app = web.Application()
    app.router.add_get("/api/mini/x360-icon/{title_hex}/{image_hex}", handle_x360_icon)
    client = TestClient(TestServer(app))
    await client.start_server()

    mock_resp = httpx.Response(
        status_code=200,
        content=b"\x89PNG\r\n\x1a\nfake_image_data",
        request=httpx.Request("GET", "http://image.xboxlive.com/global/t.584109cb/ach/0/3"),
    )

    try:
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp

            resp = await client.get("/api/mini/x360-icon/584109cb/3")
            assert resp.status == 200
            assert resp.headers["Content-Type"] == "image/png"
            assert "max-age=604800" in resp.headers["Cache-Control"]
            content = await resp.read()
            assert content == b"\x89PNG\r\n\x1a\nfake_image_data"
            assert mock_get.call_count == 1

            # Second request should be served from memory cache without another httpx.get call
            resp2 = await client.get("/api/mini/x360-icon/584109cb/3")
            assert resp2.status == 200
            content2 = await resp2.read()
            assert content2 == b"\x89PNG\r\n\x1a\nfake_image_data"
            assert mock_get.call_count == 1
    finally:
        await client.close()


async def test_handle_x360_icon_invalid_hex() -> None:
    app = web.Application()
    app.router.add_get("/api/mini/x360-icon/{title_hex}/{image_hex}", handle_x360_icon)
    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        resp = await client.get("/api/mini/x360-icon/not_hex!/3")
        assert resp.status == 400
    finally:
        await client.close()


async def test_handle_x360_icon_upstream_404() -> None:
    _X360_ICON_CACHE.clear()

    app = web.Application()
    app.router.add_get("/api/mini/x360-icon/{title_hex}/{image_hex}", handle_x360_icon)
    client = TestClient(TestServer(app))
    await client.start_server()

    mock_resp = httpx.Response(
        status_code=404,
        request=httpx.Request("GET", "http://image.xboxlive.com/global/t.584109cb/ach/0/999"),
    )

    try:
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            resp = await client.get("/api/mini/x360-icon/584109cb/999")
            assert resp.status == 404
    finally:
        await client.close()


async def test_fill_x360_icon_preserves_existing_icon() -> None:
    fetcher = Fetcher(
        repo=AsyncMock(),
        client=AsyncMock(),
        publisher=AsyncMock(),
        anthropic_auth=AsyncMock(),
    )
    fetcher.ensure_title_icon = AsyncMock(return_value="https://boxart.png")

    ach1 = ParsedAchievement(
        achievement_id="1",
        title_id="1480657355",
        title_name="Wolf 3D",
        name="Episode 1",
        description="Done",
        icon_url="http://image.xboxlive.com/global/t.584109cb/ach/0/3",
        unlocked_at=None,
        gamerscore=15,
        rarity_percent=14.8,
        platform=Platform.XBOX_360,
    )
    ach2 = ParsedAchievement(
        achievement_id="2",
        title_id="1480657355",
        title_name="Wolf 3D",
        name="Episode 2",
        description="Done",
        icon_url=None,
        unlocked_at=None,
        gamerscore=15,
        rarity_percent=5.0,
        platform=Platform.XBOX_360,
    )

    await fetcher._fill_x360_icon(1, "1480657355", Platform.XBOX_360, [ach1, ach2])

    # ach1 had an authentic icon, so it was preserved
    assert ach1.icon_url == "http://image.xboxlive.com/global/t.584109cb/ach/0/3"
    # ach2 had None, so it fell back to game box art
    assert ach2.icon_url == "https://boxart.png"


def test_gallery_distinct_icons_for_x360() -> None:
    ach1 = AchievementRow(
        title_id="1480657355",
        achievement_id="1",
        name="Episode 1",
        description="Escape from Wolfenstein",
        icon_url="http://image.xboxlive.com/global/t.584109cb/ach/0/1",
        unlocked_at="2026-09-23T10:00:00Z",
        gamerscore=15,
        rarity_percent=14.8,
        platform=Platform.XBOX_360,
        title_name="Wolfenstein 3D",
        is_secret=False,
    )
    ach2 = AchievementRow(
        title_id="1480657355",
        achievement_id="2",
        name="Secret Room",
        description="Found secret room",
        icon_url="http://image.xboxlive.com/global/t.584109cb/ach/0/2",
        unlocked_at="2026-09-23T10:05:00Z",
        gamerscore=15,
        rarity_percent=5.0,
        platform=Platform.XBOX_360,
        title_name="Wolfenstein 3D",
        is_secret=True,
    )

    gallery = _gallery([ach1, ach2])
    # Individual icons are not grouped into one box art photo
    assert len(gallery) == 2
    assert gallery[0] == ("http://image.xboxlive.com/global/t.584109cb/ach/0/1", False)
    assert gallery[1] == ("http://image.xboxlive.com/global/t.584109cb/ach/0/2", True)


def test_format_digest_x360_rarity_and_spoilers() -> None:
    ach1 = AchievementRow(
        title_id="1480657355",
        achievement_id="1",
        name="Common Achievement",
        description="Common description",
        icon_url="http://image.xboxlive.com/global/t.584109cb/ach/0/1",
        unlocked_at="2026-09-23T10:00:00Z",
        gamerscore=15,
        rarity_percent=25.0,
        platform=Platform.XBOX_360,
        title_name="Wolfenstein 3D",
        is_secret=False,
    )
    ach2 = AchievementRow(
        title_id="1480657355",
        achievement_id="2",
        name="Rare Secret",
        description="Secret description",
        icon_url="http://image.xboxlive.com/global/t.584109cb/ach/0/2",
        unlocked_at="2026-09-23T10:05:00Z",
        gamerscore=30,
        rarity_percent=4.5,
        platform=Platform.XBOX_360,
        title_name="Wolfenstein 3D",
        is_secret=True,
    )

    text = format_digest("Player", "Wolfenstein 3D", [ach1, ach2], locale="ru")

    # Common achievement: 🏆 badge, 25% rarity, no spoiler
    assert "🏆 «Common Achievement» · 15 G · 25%" in text
    assert "Common description" in text

    # Rare secret achievement: 💎 badge, 4.5% rarity, spoiler on title and description
    assert '💎 «<span class="tg-spoiler">Rare Secret</span>» · 30 G · 4.5%' in text
    assert '<span class="tg-spoiler">Secret description</span>' in text


def test_format_single_x360_secret_achievement() -> None:
    ach = AchievementRow(
        title_id="1480657355",
        achievement_id="2",
        name="Rare Secret",
        description="Secret description",
        icon_url="http://image.xboxlive.com/global/t.584109cb/ach/0/2",
        unlocked_at="2026-09-23T10:05:00Z",
        gamerscore=30,
        rarity_percent=4.5,
        platform=Platform.XBOX_360,
        title_name="Wolfenstein 3D",
        is_secret=True,
    )

    text = format_single("Player", ach, "Wolfenstein 3D", locale="ru")
    assert "получает секретное достижение" in text
    assert '💎 «<span class="tg-spoiler">Rare Secret</span>» · 30 G · 4.5%' in text
    assert '<span class="tg-spoiler">Secret description</span>' in text


MIGRATION_061 = Path("bot/db/migrations/061_x360_real_icons.sql").read_text(encoding="utf-8")


async def test_migration_061_gives_old_rows_their_real_icon(tmp_path) -> None:
    import aiosqlite

    sql = MIGRATION_061
    real = "http://image.xboxlive.com/global/t.4d5308ab/ach/0/44"
    box_art = "http://store-images.s-microsoft.com/image/apps.1.box"
    async with aiosqlite.connect(tmp_path / "m061.db") as conn:
        await conn.execute(
            "CREATE TABLE seen_achievements"
            " (platform TEXT, title_id TEXT, achievement_id TEXT, icon_url TEXT)"
        )
        await conn.execute(
            "CREATE TABLE title_achievements"
            " (platform TEXT, title_id TEXT, achievement_id TEXT, icon_url TEXT)"
        )
        await conn.executemany(
            "INSERT INTO seen_achievements VALUES (?, ?, ?, ?)",
            [
                ("xbox_360", "g", "32", box_art),  # box art: replaced
                ("xbox_360", "g", "33", None),  # nothing: filled
                ("xbox_360", "g", "34", box_art),  # catalog has no real one: kept
                ("xbox_modern", "g", "32", box_art),  # not a 360 row: untouched
            ],
        )
        await conn.executemany(
            "INSERT INTO title_achievements VALUES (?, ?, ?, ?)",
            [
                ("xbox_360", "g", "32", real),
                ("xbox_360", "g", "33", real),
                ("xbox_360", "g", "34", None),
                ("xbox_modern", "g", "32", real),
            ],
        )
        await conn.executescript(sql)
        cursor = await conn.execute(
            "SELECT platform, achievement_id, icon_url FROM seen_achievements"
        )
        icons = {(r[0], r[1]): r[2] for r in await cursor.fetchall()}

    assert icons[("xbox_360", "32")] == real
    assert icons[("xbox_360", "33")] == real
    assert icons[("xbox_360", "34")] == box_art
    assert icons[("xbox_modern", "32")] == box_art
