"""A post's picture as a square of one size (owner, 2026-10-10).

Telegram sizes a photo message by its picture: a 64 px Steam or Xbox 360
icon came out as a narrow, blurry card, a wide Xbox artwork as a wide one, and
on the desktop no two posts were the same width. Here the picture the bot
already has — the icon as the platform gave it, cached untouched under
`data/achievements/` — is laid out on a square at the moment it is sent:

- a small icon is scaled up to about half the square, with rounded corners
  and a soft shadow, in the middle;
- a large square picture fills the square;
- a large picture of another shape is shown whole, as wide as the square,
  on its own blurred copy.

What is around a small icon is the style, an admin setting (`post_picture_style`):
`color` — the icon's own average colour, darkened at the edges; `cover` — the
game's cover, blurred, darkened and paled (the colour when there is no
cover); `off` — the picture as it is, as before.

Nothing composed is stored: the originals stay what they were, so a new style
or a new size is one change here. The Mini App will draw the same layout
from the same originals.
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

# The square's side: under Telegram's 1280 px, so it is sent as drawn.
SIDE = 1024
# Smaller than this on its longer side, a picture is an icon to frame; at
# least this, it is artwork to show at the square's full width.
LARGE = 400
# How much of the square a framed icon takes, on its longer side.
ICON_SHARE = 0.56
# Within this of 1:1, a large picture counts as square and fills it.
SQUARE_TOLERANCE = 0.06

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


def _average(picture: Image.Image) -> tuple[int, int, int]:
    """The picture's mean colour, its transparent parts left out."""
    rgb = Image.new("RGB", picture.size, (0, 0, 0))
    rgb.paste(picture, mask=picture.getchannel("A"))
    alpha = picture.getchannel("A")
    seen = alpha.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0)) or 0
    r, g, b = rgb.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))[:3]
    if seen <= 0:
        return (40, 44, 52)
    scale = 255 / seen
    return tuple(min(255, round(c * scale)) for c in (r, g, b))  # type: ignore[return-value]


def _color_ground(picture: Image.Image) -> Image.Image:
    """The icon's average colour, toned down so the icon stands out on it,
    lighter in the middle and darker at the edges."""
    r, g, b = _average(picture)
    # Keep the hue, cap the brightness: a white icon must not sit on white.
    peak = max(r, g, b, 1)
    target = min(peak, 150)
    r, g, b = (round(c * target / peak) for c in (r, g, b))
    centre = tuple(min(255, round(c * 1.1 + 12)) for c in (r, g, b))
    edge = tuple(round(c * 0.45) for c in (r, g, b))
    mask = Image.radial_gradient("L").resize((SIDE, SIDE), Image.Resampling.BICUBIC)
    return Image.composite(
        Image.new("RGB", (SIDE, SIDE), edge), Image.new("RGB", (SIDE, SIDE), centre), mask
    )


def _blurred_ground(cover: Image.Image) -> Image.Image:
    """A picture (the game's cover, or artwork itself) across the whole
    square, blurred, darkened and paled."""
    ground = ImageOps.fit(cover.convert("RGB"), (SIDE, SIDE), Image.Resampling.LANCZOS)
    ground = ground.filter(ImageFilter.GaussianBlur(SIDE // 36))
    ground = ImageEnhance.Color(ground).enhance(0.55)
    return ImageEnhance.Brightness(ground).enhance(0.5)


def _scaled(picture: Image.Image, longest: int) -> Image.Image:
    w, h = picture.size
    factor = longest / max(w, h)
    size = (max(1, round(w * factor)), max(1, round(h * factor)))
    out = picture.resize(size, Image.Resampling.LANCZOS)
    if factor > 3:
        # A 64 px icon blown up eight times is soft; a light sharpening
        # brings its edges back without the ringing of a strong one.
        out = out.filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2))
    return out


def _framed_icon(icon: Image.Image) -> tuple[Image.Image, Image.Image]:
    """The icon with rounded corners, and its shadow, both the square's size."""
    side = round(SIDE * ICON_SHARE)
    icon = _scaled(icon, side)
    radius = round(min(icon.size) * 0.08)
    rounded = Image.new("L", icon.size, 0)
    ImageDraw.Draw(rounded).rounded_rectangle((0, 0, *icon.size), radius=radius, fill=255)
    alpha = Image.composite(icon.getchannel("A"), rounded, rounded)
    icon.putalpha(alpha)

    layer = Image.new("RGBA", (SIDE, SIDE), (0, 0, 0, 0))
    at = ((SIDE - icon.width) // 2, (SIDE - icon.height) // 2)
    layer.paste(icon, at, icon)

    shadow = Image.new("RGBA", (SIDE, SIDE), (0, 0, 0, 0))
    drop = Image.new("RGBA", icon.size, (0, 0, 0, 150))
    drop.putalpha(Image.eval(alpha, lambda a: a * 150 // 255))
    shadow.paste(drop, (at[0], at[1] + SIDE // 64), drop)
    shadow = shadow.filter(ImageFilter.GaussianBlur(SIDE // 40))
    return layer, shadow


def compose(icon: bytes, style: str, cover: bytes | None = None) -> bytes | None:
    """`icon` on a square in `style`, as a JPEG; None when `icon` is not a
    picture. CPU work — run it in a thread."""
    picture = _open(icon)
    if picture is None:
        return None
    w, h = picture.size
    large = max(w, h) >= LARGE
    if large and abs(w / h - 1) <= SQUARE_TOLERANCE:
        canvas = ImageOps.fit(picture.convert("RGB"), (SIDE, SIDE), Image.Resampling.LANCZOS)
        return _jpeg(canvas)

    if large:
        # Artwork of its own shape: its own blurred copy around it, as the
        # Mini App's feed shows a picture whole.
        canvas = _blurred_ground(picture)
    else:
        cover_picture = _open(cover) if cover and style == STYLE_COVER else None
        canvas = _blurred_ground(cover_picture) if cover_picture else _color_ground(picture)

    if large:
        whole = _scaled(picture, SIDE)
        layer = Image.new("RGBA", (SIDE, SIDE), (0, 0, 0, 0))
        layer.paste(whole, ((SIDE - whole.width) // 2, (SIDE - whole.height) // 2), whole)
        canvas = Image.alpha_composite(canvas.convert("RGBA"), layer)
    else:
        layer, shadow = _framed_icon(picture)
        canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow)
        canvas = Image.alpha_composite(canvas, layer)
    return _jpeg(canvas.convert("RGB"))


def _jpeg(canvas: Image.Image) -> bytes:
    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=90, optimize=True)
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
    stored = await repo.get_app_setting(STYLE_KEY)
    return stored if stored in STYLES else STYLE_DEFAULT


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


async def build(
    icon_sources: Sequence[str], cover_sources: Sequence[str], style: str
) -> bytes | None:
    """A post's square picture from the first icon source that loads (a file
    or a URL), on the first cover that loads; None when the style is `off`,
    no icon loads, or what loaded is not a picture."""
    if style not in (STYLE_COLOR, STYLE_COVER) or not icon_sources:
        return None
    key = (style, icon_sources[0], cover_sources[0] if cover_sources else "")
    if key in _memo:
        _memo.move_to_end(key)
        return _memo[key]
    icon = await _first(icon_sources)
    if icon is None:
        return None
    cover = await _first(cover_sources) if style == STYLE_COVER else None
    try:
        composed = await asyncio.to_thread(compose, icon[1], style, cover[1] if cover else None)
    except Exception:
        log.exception("could not compose a post picture from %s", icon[0])
        return None
    if composed is not None:
        _memo[key] = composed
        if len(_memo) > _MEMO_SIZE:
            _memo.popitem(last=False)
    return composed
