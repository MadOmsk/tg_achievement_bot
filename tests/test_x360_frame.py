"""Xbox 360 art kept without the console's frame (owner, 2026-10-28)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from bot.services import game_art, game_page, x360_frame


def _jpeg(size: tuple[int, int], corner: tuple[int, int, int] = (40, 40, 40)) -> bytes:
    image = Image.new("RGB", size, (40, 40, 40))
    w, h = size
    image.paste(corner, (0, 0, int(w * 0.17), int(h * 0.2)))
    out = io.BytesIO()
    image.save(out, "JPEG")
    return out.getvalue()


def _size(data: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(data)).size


def test_the_portrait_loses_its_header() -> None:
    stripped = x360_frame.strip(_jpeg((219, 300)))
    assert _size(stripped) == (219, 261)
    assert x360_frame.strip(stripped) is stripped  # cut once only


def test_the_square_tile_loses_its_green_bar() -> None:
    stripped = x360_frame.strip(_jpeg((1080, 1080), corner=(60, 200, 40)))
    assert _size(stripped) == (890, 1080)
    assert x360_frame.strip(stripped) is stripped


def test_the_store_poster_loses_its_white_band() -> None:
    stripped = x360_frame.strip(_jpeg((720, 1080), corner=(255, 255, 255)))
    assert _size(stripped) == (720, 954)
    assert x360_frame.strip(stripped) is stripped  # no longer any frame's shape


def test_other_pictures_are_left_as_they_came() -> None:
    for data in (
        _jpeg((150, 150), corner=(60, 200, 40)),  # a small icon, however green
        _jpeg((1080, 1080)),  # a square with no bar
        _jpeg((720, 1080)),  # a 2:3 poster with no band
        _jpeg((600, 900 * 2)),
        b"not a picture",
    ):
        assert x360_frame.strip(data) is data


def test_only_a_360_lists_icon_is_marked() -> None:
    url = "https://store-images.s-microsoft.com/image/apps.1"
    assert x360_frame.mark(url, "xbox_360") == url + x360_frame.MARK
    assert x360_frame.mark(url + x360_frame.MARK, "xbox_360") == url + x360_frame.MARK
    assert x360_frame.mark(url, "xbox_modern") == url
    assert game_page.list_icons(
        [
            {"platform": "xbox_360", "icon_url": url},
            {"platform": "steam", "icon_url": url + "s"},
            {"platform": "psn", "icon_url": None},
        ]
    ) == [url + x360_frame.MARK, url + "s"]


def test_a_360_products_store_poster_is_marked() -> None:
    poster = "http://store-images.s-microsoft.com/image/apps.6999.1"
    media = json.dumps({"poster": poster})
    versions = [
        {"store": "xbox", "product_id": "BPKD", "console": "one", "media": media},
        {"store": "xbox", "product_id": "BPKD", "console": "360", "media": media},
    ]
    marked = game_page.store_art(versions)["poster"]
    assert marked == "https://store-images.s-microsoft.com/image/apps.6999.1" + x360_frame.MARK
    assert game_page.store_art(versions[:1])["poster"] == game_page.https(poster)


@pytest.mark.asyncio
async def test_a_marked_poster_is_kept_cut(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    framed = _jpeg((219, 300))

    async def fetch(url: str) -> bytes:
        return framed

    monkeypatch.setattr(game_art, "_fetch", fetch)
    url = x360_frame.mark("https://store-images.s-microsoft.com/image/apps.9", "xbox_360")
    data, _ = await game_art.get(url, root=tmp_path)
    assert _size(data) == (219, 261)
    plain, _ = await game_art.get(
        "https://store-images.s-microsoft.com/image/apps.9", root=tmp_path
    )
    assert _size(plain) == (219, 300)
