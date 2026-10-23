"""Cached achievement icons are at most 1280 px (owner, 2026-10-23): Xbox's
1920x1080 PNGs, kept whole, took 4 GB and reached phones at 4 MB each."""

from __future__ import annotations

import io

from PIL import Image

from bot.services import achievement_icons as icons


def _png(size: tuple[int, int], alpha: int = 255) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", size, (30, 120, 200, alpha)).save(out, "PNG")
    return out.getvalue()


def _opened(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def test_a_large_opaque_icon_becomes_a_1280_jpeg() -> None:
    shrunk = icons.shrink(_png((1920, 1080)))
    picture = _opened(shrunk)
    assert picture.format == "JPEG"
    assert picture.size == (1280, 720)


def test_a_large_see_through_icon_stays_png() -> None:
    picture = _opened(icons.shrink(_png((1920, 1080), alpha=0)))
    assert picture.format == "PNG"
    assert picture.size == (1280, 720)


def test_a_small_icon_or_not_a_picture_is_left_alone() -> None:
    small = _png((512, 512))
    assert icons.shrink(small) is small
    assert icons.shrink(b"nope") == b"nope"


async def test_a_downloaded_icon_is_stored_shrunk(tmp_path) -> None:
    _data, mime = await icons.store_icon("xbox_modern", "1", "7", _png((1920, 1080)), root=tmp_path)
    assert mime == "image/jpeg"
    cached = icons.find_cached_icon("xbox_modern", "1", "7", root=tmp_path)
    assert cached is not None and cached.suffix == ".jpg"
    assert _opened(cached.read_bytes()).size == (1280, 720)


async def test_the_cache_is_shrunk_once(repo, tmp_path) -> None:
    folder = icons.game_icon_dir("xbox_modern", "1", root=tmp_path)
    folder.mkdir(parents=True)
    (folder / "7.png").write_bytes(_png((1920, 1080)))
    small = _png((64, 64))
    (folder / "8.png").write_bytes(small)

    assert await icons.shrink_cached_once(repo, root=tmp_path) == 1
    assert not (folder / "7.png").exists()
    assert _opened((folder / "7.jpg").read_bytes()).size == (1280, 720)
    assert (folder / "8.png").read_bytes() == small

    (folder / "9.png").write_bytes(_png((1920, 1080)))
    assert await icons.shrink_cached_once(repo, root=tmp_path) == 0
    assert (folder / "9.png").exists()
