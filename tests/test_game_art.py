"""A game's store art kept on our disk and served by a signed address."""

from __future__ import annotations

from pathlib import Path

import pytest

from bot.services import game_art

URL = "https://store-images.s-microsoft.com/image/apps.1.2"


def test_store_pictures_are_served_signed_and_others_are_left() -> None:
    assert game_art.served(URL) == URL  # not configured: as it is
    game_art.configure("k1")
    served = game_art.served(URL)
    assert served is not None and served.startswith(f"{game_art.ROUTE}/{game_art.sign(URL)}?u=")
    assert game_art.served("https://evil.example/x.jpg") == "https://evil.example/x.jpg"
    assert game_art.served("http://store-images.s-microsoft.com/x") == (
        "http://store-images.s-microsoft.com/x"
    )
    first = game_art.sign(URL)
    game_art.configure("k2")
    assert game_art.sign(URL) != first


def test_hosts_match_by_suffix_only() -> None:
    assert game_art.allowed("https://shared.akamai.steamstatic.com/a.jpg")
    assert game_art.allowed("https://image.api.playstation.com/a.png")
    assert not game_art.allowed("https://steamstatic.com.evil.net/a.jpg")
    assert not game_art.allowed("https://notplaystation.com/a.jpg")


@pytest.mark.asyncio
async def test_a_picture_is_downloaded_once_and_then_read_from_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    jpeg = b"\xff\xd8\xff" + b"0" * 100

    async def fetch(url: str) -> bytes:
        calls.append(url)
        return jpeg

    monkeypatch.setattr(game_art, "_fetch", fetch)
    assert await game_art.get(URL, root=tmp_path) == (jpeg, "image/jpeg")
    assert await game_art.get(URL, root=tmp_path) == (jpeg, "image/jpeg")
    assert calls == [URL]
    assert game_art.cached(URL, root=tmp_path) is not None


@pytest.mark.asyncio
async def test_a_missing_picture_is_not_asked_for_again_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def fetch(url: str) -> None:
        calls.append(url)

    monkeypatch.setattr(game_art, "_fetch", fetch)
    monkeypatch.setattr(game_art, "_misses", {})
    url = URL + "/missing"
    assert await game_art.get(url, root=tmp_path) is None
    assert await game_art.get(url, root=tmp_path) is None
    assert calls == [url]
