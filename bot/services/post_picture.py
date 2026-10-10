"""A low-resolution post picture, enlarged and set on a square (owner,
2026-10-10).

Steam and Xbox 360 hand out 64 px achievement icons; Telegram showed them
as a tiny, blurry card, every post a different width. Here, at the moment a
post is sent:

- a picture of high resolution goes **as it is**, untouched;
- a low-resolution one (under `LOW_RES` on its longer side) is enlarged ×3
  by a cheap filter and set in the middle of a 1024 × 1024 ground, with
  rounded corners and a soft shadow.

The ground is the style, an admin setting (`post_picture_style`): `color` —
the icon's own average colour, darker at the edges; `cover` — the game's
cover, blurred, darkened and paled (the colour when there is no cover);
`off` — nothing is drawn, as before.

**The original is what is stored** (the icon cache, the cover, the URLs in
the database); nothing composed is kept, so the style can
change at any time. The Mini App is not touched by this.
"""

from __future__ import annotations

import asyncio
import io
import logging
from collections import OrderedDict
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError

from bot.services import achievement_icons, covers, images

if TYPE_CHECKING:
    from bot.db.repo import AchievementRow, Repo

log = logging.getLogger(__name__)

STYLE_KEY = "post_picture_style"
STYLE_OFF, STYLE_COLOR, STYLE_COVER = "off", "color", "cover"
STYLES = (STYLE_OFF, STYLE_COLOR, STYLE_COVER)
STYLE_DEFAULT = STYLE_OFF

# The square's side, and how many times a low-resolution icon is enlarged
# on it (owner, 2026-10-10).
SIDE = 1024
SCALE = 3

# Under this on its longer side, a picture is low-resolution (Steam's and
# Xbox 360's 64 px icons); at least this, it goes as it is.
LOW_RES = 200
# Composed pictures kept for a while: one achievement goes to several chats.
_MEMO_SIZE = 32
_memo: OrderedDict[tuple[str, str, str], bytes] = OrderedDict()


# ------------------------------------------------------------------ drawing


def _open(data: bytes) -> Image.Image | None:
    try:
        picture = Image.open(io.BytesIO(data))
        picture.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None
    picture = ImageOps.exif_transpose(picture)
    return picture.convert("RGBA")


def is_low_res(picture: Image.Image) -> bool:
    return max(picture.size) < LOW_RES


def _average(picture: Image.Image) -> tuple[int, int, int]:
    """The picture's mean colour, its transparent parts left out."""
    rgb = Image.new("RGB", picture.size, (0, 0, 0))
    rgb.paste(picture, mask=picture.getchannel("A"))
    seen = picture.getchannel("A").resize((1, 1), Image.Resampling.BOX).getpixel((0, 0)) or 0
    r, g, b = rgb.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))[:3]
    if seen <= 0:
        return (40, 44, 52)
    scale = 255 / seen
    return tuple(min(255, round(c * scale)) for c in (r, g, b))  # type: ignore[return-value]


def _color_ground(picture: Image.Image, side: int) -> Image.Image:
    """The icon's average colour, toned down so the icon stands out on it,
    lighter in the middle and darker at the edges."""
    r, g, b = _average(picture)
    # Keep the hue, cap the brightness: a white icon must not sit on white.
    peak = max(r, g, b, 1)
    target = min(peak, 150)
    r, g, b = (round(c * target / peak) for c in (r, g, b))
    centre = tuple(min(255, round(c * 1.1 + 12)) for c in (r, g, b))
    edge = tuple(round(c * 0.45) for c in (r, g, b))
    mask = Image.radial_gradient("L").resize((side, side), Image.Resampling.BICUBIC)
    return Image.composite(
        Image.new("RGB", (side, side), edge), Image.new("RGB", (side, side), centre), mask
    )


def _cover_ground(cover: Image.Image, side: int) -> Image.Image:
    """The game's cover across the whole square, blurred, darkened and paled."""
    ground = ImageOps.fit(cover.convert("RGB"), (side, side), Image.Resampling.LANCZOS)
    ground = ground.filter(ImageFilter.GaussianBlur(max(2, side // 36)))
    ground = ImageEnhance.Color(ground).enhance(0.55)
    return ImageEnhance.Brightness(ground).enhance(0.5)


def compose(icon: bytes, style: str, cover: bytes | None = None) -> bytes | None:
    """A low-resolution `icon` enlarged `SCALE` times on a `SIDE` square in
    `style`, as a JPEG; None when it is of high resolution (it goes as it
    is), when the style is off, or when `icon` is not a picture. CPU work —
    run it in a thread."""
    if style not in (STYLE_COLOR, STYLE_COVER):
        return None
    picture = _open(icon)
    if picture is None or not is_low_res(picture):
        return None
    # A cheap filter, as asked: bicubic, no sharpening, nothing learned.
    big = picture.resize((picture.width * SCALE, picture.height * SCALE), Image.Resampling.BICUBIC)
    side = SIDE

    cover_picture = _open(cover) if cover and style == STYLE_COVER else None
    ground = _cover_ground(cover_picture, side) if cover_picture else _color_ground(picture, side)

    radius = max(2, round(min(big.size) * 0.08))
    rounded = Image.new("L", big.size, 0)
    ImageDraw.Draw(rounded).rounded_rectangle((0, 0, *big.size), radius=radius, fill=255)
    alpha = Image.composite(big.getchannel("A"), rounded, rounded)
    big.putalpha(alpha)
    at = ((side - big.width) // 2, (side - big.height) // 2)

    shadow = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    drop = Image.new("RGBA", big.size, (0, 0, 0, 0))
    drop.putalpha(Image.eval(alpha, lambda a: a * 150 // 255))
    # The shadow belongs to the icon, so it is sized by the icon, not the square.
    shadow.paste(drop, (at[0], at[1] + max(2, big.height // 24)), drop)
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(2, big.height // 14)))

    canvas = Image.alpha_composite(ground.convert("RGBA"), shadow)
    canvas.paste(big, at, big)
    out = io.BytesIO()
    canvas.convert("RGB").save(out, "JPEG", quality=92, optimize=True)
    return out.getvalue()


# ------------------------------------------------------------------ sources


async def sources(repo: Repo, item: AchievementRow) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Where an achievement's picture and its game's cover can be read from:
    the icon cached on disk before its URL, the cover's file before its URL."""
    cached = achievement_icons.find_cached_icon(item.platform, item.title_id, item.achievement_id)
    icon = tuple(s for s in (str(cached) if cached else None, item.icon_url) if s)
    cover_path, cover_url = await repo.title_cover(item.title_id)
    cover = tuple(
        s for s in (str(covers.cover_dir() / cover_path) if cover_path else None, cover_url) if s
    )
    return icon, cover


async def style_of(repo: Repo) -> str:
    """The admin's style, read on every post so a change applies at once."""
    style = await repo.get_app_setting(STYLE_KEY)
    return style if style in STYLES else STYLE_DEFAULT


async def _load(source: str) -> bytes | None:
    """A picture's bytes from a URL or a file on disk."""
    if source.startswith(("http://", "https://")):
        return await images.fetch(source)
    try:
        return await asyncio.to_thread(Path(source).read_bytes)
    except OSError:
        return None


async def _first(sources: Sequence[str]) -> tuple[str, bytes] | None:
    for source in sources:
        data = await _load(source)
        if data:
            return source, data
    return None


def _low_res_bytes(data: bytes) -> bool:
    """Whether a picture is low-resolution, from its header alone."""
    try:
        with Image.open(io.BytesIO(data)) as picture:
            return max(picture.size) < LOW_RES
    except (UnidentifiedImageError, OSError, ValueError):
        return False


async def build(
    icon_sources: Sequence[str], cover_sources: Sequence[str], style: str
) -> bytes | None:
    """A post's enlarged, squared picture from the first icon source that
    loads (a file or a URL), on the first cover that loads; None — send the
    original as it is — when the style is off, the icon is of high
    resolution, nothing loads, or what loaded is not a picture."""
    if style not in (STYLE_COLOR, STYLE_COVER) or not icon_sources:
        return None
    key = (style, icon_sources[0], cover_sources[0] if cover_sources else "")
    if key in _memo:
        _memo.move_to_end(key)
        return _memo[key] or None
    icon = await _first(icon_sources)
    if icon is None:
        return None
    composed: bytes | None = None
    if _low_res_bytes(icon[1]):
        cover = await _first(cover_sources) if style == STYLE_COVER else None
        try:
            composed = await asyncio.to_thread(compose, icon[1], style, cover[1] if cover else None)
        except Exception:
            log.exception("could not compose a post picture from %s", icon[0])
            return None
    # A high-resolution icon is remembered too, as nothing to draw: the next
    # chat's copy of the post does not fetch it again.
    _memo[key] = composed or b""
    if len(_memo) > _MEMO_SIZE:
        _memo.popitem(last=False)
    return composed
