"""Tests for local achievement icon storage and caching (#99)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.constants import Platform
from bot.db.repo import Repo, TitleAchievementRow
from bot.services import achievement_icons
from bot.services.achievement_icons import (
    detect_mime,
    format_achievement_icon_url,
    game_icon_dir,
    get_or_download_achievement_icon,
    get_or_download_x360_icon,
    safe_part,
    x360_icon_path,
)
from bot.web.mini_api import handle_achievement_icon, handle_game_details


def test_detect_mime() -> None:
    assert detect_mime(b"\x89PNG\r\n\x1a\n") == ("image/png", ".png")
    assert detect_mime(b"\xff\xd8\xff\xe0\x00\x10JFIF") == ("image/jpeg", ".jpg")
    assert detect_mime(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == ("image/webp", ".webp")
    assert detect_mime(b"random-bytes") == ("image/png", ".png")


def test_safe_part_and_subdirectories(tmp_path: Path) -> None:
    # Standard clean ids
    assert safe_part("220") == "220"
    assert safe_part("ACH_1") == "ACH_1"
    # Special characters or long paths get hashed safely
    part = safe_part("app:123/dlc")
    assert "app123dlc" in part
    assert not any(c in part for c in ":/*")

    # Subdirectories structure: data/achievements/{platform}/{title_id}/
    gdir = game_icon_dir("steam", "220", root=tmp_path)
    assert gdir == tmp_path / "data" / "achievements" / "steam" / "220"

    # Xbox 360 subdirectories: data/achievements/xbox_360/{title_hex}/{image_hex}.png
    xdir = x360_icon_path("584109cb", "3", root=tmp_path)
    assert xdir == tmp_path / "data" / "achievements" / "xbox_360" / "584109cb" / "3.png"


def test_format_achievement_icon_url() -> None:
    # x360 URL
    x360_url = "http://image.xboxlive.com/global/t.584109cb/ach/0/3"
    assert (
        format_achievement_icon_url("xbox_360", "1480657355", "3", x360_url)
        == "/api/mini/x360-icon/584109cb/3"
    )

    # Steam achievement
    assert (
        format_achievement_icon_url(
            "steam", "220", "ACH_1", "https://steamcdn-a.akamaihd.net/icon.jpg"
        )
        == "/api/mini/ach-icon/steam/220/ACH_1"
    )

    # PSN trophy
    assert (
        format_achievement_icon_url(
            "psn", "NPWR00123_00", "0", "https://image.api.playstation.com/trophy.png"
        )
        == "/api/mini/ach-icon/psn/NPWR00123_00/0"
    )

    # None / empty
    assert format_achievement_icon_url("steam", "220", "ACH_1", None) is None
    assert format_achievement_icon_url("steam", "220", "ACH_1", "") is None


@pytest.mark.asyncio
async def test_get_or_download_x360_icon_disk_cache(tmp_path: Path) -> None:
    title_hex = "584109cb"
    image_hex = "3"
    target_file = x360_icon_path(title_hex, image_hex, root=tmp_path)
    target_file.parent.mkdir(parents=True, exist_ok=True)
    fake_png = b"\x89PNG\r\n\x1a\npre_cached_icon"
    target_file.write_bytes(fake_png)

    # Should read from disk directly without making any HTTP call
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        res = await get_or_download_x360_icon(title_hex, image_hex, root=tmp_path)
        assert res is not None
        body, mime = res
        assert body == fake_png
        assert mime == "image/png"
        assert mock_get.call_count == 0


@pytest.mark.asyncio
async def test_get_or_download_x360_icon_download_and_save(tmp_path: Path) -> None:
    title_hex = "584109cb"
    image_hex = "4"
    fake_png = b"\x89PNG\r\n\x1a\ndownloaded_icon"

    mock_resp = httpx.Response(
        status_code=200,
        content=fake_png,
        request=httpx.Request(
            "GET", f"http://image.xboxlive.com/global/t.{title_hex}/ach/0/{image_hex}"
        ),
    )

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = await get_or_download_x360_icon(title_hex, image_hex, root=tmp_path)
        assert res is not None
        body, mime = res
        assert body == fake_png
        assert mime == "image/png"
        assert mock_get.call_count == 1

        # File must be written to disk
        target_file = x360_icon_path(title_hex, image_hex, root=tmp_path)
        assert target_file.is_file()
        assert target_file.read_bytes() == fake_png

        # Second call should read from disk
        res2 = await get_or_download_x360_icon(title_hex, image_hex, root=tmp_path)
        assert res2 == res
        assert mock_get.call_count == 1


@pytest.mark.asyncio
async def test_get_or_download_achievement_icon(tmp_path: Path) -> None:
    repo = AsyncMock(spec=Repo)
    repo.achievement_icon_url = AsyncMock(
        return_value="https://steamcdn-a.akamaihd.net/ach_icon.jpg"
    )

    fake_jpg = b"\xff\xd8\xff\xe0\x00\x10JFIFfake_jpg"
    mock_resp = httpx.Response(
        status_code=200,
        content=fake_jpg,
        request=httpx.Request("GET", "https://steamcdn-a.akamaihd.net/ach_icon.jpg"),
    )

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = await get_or_download_achievement_icon(repo, "steam", "220", "ACH_1", root=tmp_path)
        assert res is not None
        body, mime = res
        assert body == fake_jpg
        assert mime == "image/jpeg"
        assert mock_get.call_count == 1

        # Second call hits disk cache
        res2 = await get_or_download_achievement_icon(repo, "steam", "220", "ACH_1", root=tmp_path)
        assert res2 == res
        assert mock_get.call_count == 1


@pytest.mark.asyncio
async def test_handle_achievement_icon_route(tmp_path: Path) -> None:
    repo = AsyncMock(spec=Repo)
    repo.achievement_icon_url = AsyncMock(return_value="https://cdn.example.com/icon.png")

    fake_png = b"\x89PNG\r\n\x1a\nroute_png"
    mock_resp = httpx.Response(
        status_code=200,
        content=fake_png,
        request=httpx.Request("GET", "https://cdn.example.com/icon.png"),
    )

    app = web.Application()
    app["mini_repo"] = repo
    app.router.add_get(
        "/api/mini/ach-icon/{platform}/{title_id}/{achievement_id:.+}",
        handle_achievement_icon,
    )

    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        fake_ach_dir = tmp_path / "data" / "achievements"
        with (
            patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get,
            patch.object(achievement_icons, "achievements_dir", return_value=fake_ach_dir),
        ):
            mock_get.return_value = mock_resp

            resp = await client.get("/api/mini/ach-icon/steam/220/ACH_LEVEL_1")
            assert resp.status == 200
            assert resp.headers["Content-Type"] == "image/png"
            assert "max-age=31536000" in resp.headers["Cache-Control"]
            assert "immutable" in resp.headers["Cache-Control"]
            content = await resp.read()
            assert content == fake_png

            # 404 case
            repo.achievement_icon_url.return_value = None
            resp_404 = await client.get("/api/mini/ach-icon/steam/220/NON_EXISTENT")
            assert resp_404.status == 404
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_game_details_formats_achievement_icons() -> None:
    repo = AsyncMock(spec=Repo)
    repo.title_record = AsyncMock(
        return_value={"name": "Portal", "icon_url": "https://cdn.example.com/cover.jpg"}
    )
    repo.get_user_settings = AsyncMock(return_value=None)

    catalog_service = AsyncMock()
    catalog_service.get_title_checklist_for_user = AsyncMock(
        return_value=[
            AsyncMock(
                achievement=TitleAchievementRow(
                    platform=Platform.STEAM,
                    title_id="400",
                    achievement_id="ACH_01",
                    name_ru="Портал",
                    name_en="Portal",
                    description_ru="Описание",
                    description_en="Description",
                    icon_url="https://steamcdn-a.akamaihd.net/portal_ach.jpg",
                    is_secret=False,
                ),
                is_unlocked=True,
                unlocked_at="2026-09-01T12:00:00Z",
            )
        ]
    )

    app = web.Application()
    app["mini_repo"] = repo
    app["mini_title_catalog"] = catalog_service
    settings = AsyncMock()
    settings.bot_token.get_secret_value = lambda: "fake_token"
    app["mini_settings"] = settings

    app.router.add_get(
        "/api/mini/games/{platform}/{title_id}",
        handle_game_details,
    )

    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        with patch("bot.web.mini_api._require_user") as mock_user:
            mock_user.return_value = AsyncMock(tg_id=123)
            resp = await client.get("/api/mini/games/steam/400")
            assert resp.status == 200
            data = await resp.json()
            assert data["ok"] is True
            assert len(data["achievements"]) == 1
            ach = data["achievements"][0]
            # Must be formatted through local endpoint!
            assert ach["icon_url"] == "/api/mini/ach-icon/steam/400/ACH_01"
    finally:
        await client.close()
