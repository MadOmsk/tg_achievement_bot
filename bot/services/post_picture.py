"""A low-resolution post picture, enlarged and set on a square (owner,
2026-10-10).

Steam and Xbox 360 hand out 64 px achievement icons; Telegram showed them
as a tiny, blurry card, every post a different width. Here, at the moment a
post is sent:

- a picture of high resolution goes **as it is**, untouched;
- a low-resolution one (under `post_picture_low_res` on its longer side,
  200 px by default) is enlarged ×1–×8
  by a cheap filter (`post_picture_scale`, ×4 by default; never past 90% of
  the card) and set in the middle of a card —
  1024 × 1024 (default), 720 × 1280, or none at all, the icon alone
  (`post_picture_size`) — with rounded corners and a soft shadow.

The ground is the style, an admin setting (`post_picture_style`): `color`
(the default) — the icon's own average colour, darker at the edges; `cover` — the game's
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
from dataclasses import dataclass
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
STYLE_DEFAULT = STYLE_COLOR

# The card a low-resolution icon is set on, and how many times it is
# enlarged — the admin's, global (owner, 2026-10-10). `original` is no card:
# the enlarged icon alone.
SIZE_KEY = "post_picture_size"
SIZE_ORIGINAL = "original"
SIZES = ("1024x1024", "720x1280", SIZE_ORIGINAL)
SIZE_DEFAULT = "1024x1024"
SCALE_KEY = "post_picture_scale"
SCALES = (1, 2, 3, 4, 5, 6, 7, 8)
SCALE_DEFAULT = 4
# An enlarged icon never takes more of the card than this, whatever the scale.
MAX_SHARE = 0.9

# Under this on its longer side, a picture is low-resolution and is drawn
# on a card; at least this, it goes as it is — the admin's (owner,
# 2026-10-10). 128 takes only Steam's and Xbox 360's 64 px icons; 256 also
# PS4's 240 px trophies; 512 everything but large artwork.
LOW_RES_KEY = "post_picture_low_res"
LOW_RES_CHOICES = (128, 200, 256, 512)
LOW_RES_DEFAULT = 200
# Composed pictures kept for a while: one achievement goes to several chats.
_MEMO_SIZE = 32
_memo: OrderedDict[tuple[str, str, int, int, str, str], bytes] = OrderedDict()


@dataclass(frozen=True, slots=True)
class Look:
    """How a low-resolution picture is drawn: the ground, the card, the
    scale — and below which size a picture counts as low-resolution."""

    style: str = STYLE_DEFAULT
    size: str = SIZE_DEFAULT
    scale: int = SCALE_DEFAULT
    low_res: int = LOW_RES_DEFAULT

    @property
    def on(self) -> bool:
        return self.style in (STYLE_COLOR, STYLE_COVER)

    def card(self) -> tuple[int, int] | None:
        """The card's width and height; None for no card."""
        if self.size == SIZE_ORIGINAL:
            return None
        width, _, height = self.size.partition("x")
        return int(width), int(height)


# ------------------------------------------------------------------ drawing


def _open(data: bytes) -> Image.Image | None:
    try:
        picture = Image.open(io.BytesIO(data))
        picture.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None
    picture = ImageOps.exif_transpose(picture)
    return picture.convert("RGBA")


def is_low_res(picture: Image.Image, limit: int = LOW_RES_DEFAULT) -> bool:
    return max(picture.size) < limit


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


def _color_ground(picture: Image.Image, size: tuple[int, int]) -> Image.Image:
    """The icon's average colour, toned down so the icon stands out on it,
    lighter in the middle and darker at the edges."""
    r, g, b = _average(picture)
    # Keep the hue, cap the brightness: a white icon must not sit on white.
    peak = max(r, g, b, 1)
    target = min(peak, 150)
    r, g, b = (round(c * target / peak) for c in (r, g, b))
    centre = tuple(min(255, round(c * 1.1 + 12)) for c in (r, g, b))
    edge = tuple(round(c * 0.45) for c in (r, g, b))
    mask = Image.radial_gradient("L").resize(size, Image.Resampling.BICUBIC)
    return Image.composite(Image.new("RGB", size, edge), Image.new("RGB", size, centre), mask)


def _cover_ground(cover: Image.Image, size: tuple[int, int]) -> Image.Image:
    """The game's cover across the whole card, blurred, darkened and paled."""
    ground = ImageOps.fit(cover.convert("RGB"), size, Image.Resampling.LANCZOS)
    ground = ground.filter(ImageFilter.GaussianBlur(max(2, min(size) // 36)))
    ground = ImageEnhance.Color(ground).enhance(0.55)
    return ImageEnhance.Brightness(ground).enhance(0.5)


def compose(icon: bytes, look: Look, cover: bytes | None = None) -> bytes | None:
    """A low-resolution `icon` enlarged `look.scale` times — on its card in
    `look.style`, or alone for the `original` size — as a JPEG; None when it
    is of high resolution (it goes as it is), when the style is off, or when
    `icon` is not a picture. CPU work — run it in a thread."""
    if not look.on:
        return None
    picture = _open(icon)
    if picture is None or not is_low_res(picture, look.low_res):
        return None
    card = look.card()
    scale = look.scale
    if card is not None:
        # Never past 90% of the card, whatever scale was picked (owner,
        # 2026-10-10).
        scale = min(scale, min(card) * MAX_SHARE / max(picture.size))
    size = (max(1, round(picture.width * scale)), max(1, round(picture.height * scale)))
    # A cheap filter, as asked: bicubic, no sharpening, nothing learned.
    big = picture.resize(size, Image.Resampling.BICUBIC)
    if card is None:
        return _jpeg(Image.alpha_composite(Image.new("RGBA", big.size, (0, 0, 0, 255)), big))

    cover_picture = _open(cover) if cover and look.style == STYLE_COVER else None
    ground = _cover_ground(cover_picture, card) if cover_picture else _color_ground(picture, card)

    radius = max(2, round(min(big.size) * 0.08))
    rounded = Image.new("L", big.size, 0)
    ImageDraw.Draw(rounded).rounded_rectangle((0, 0, *big.size), radius=radius, fill=255)
    alpha = Image.composite(big.getchannel("A"), rounded, rounded)
    big.putalpha(alpha)
    at = ((card[0] - big.width) // 2, (card[1] - big.height) // 2)

    shadow = Image.new("RGBA", card, (0, 0, 0, 0))
    drop = Image.new("RGBA", big.size, (0, 0, 0, 0))
    drop.putalpha(Image.eval(alpha, lambda a: a * 150 // 255))
    # The shadow belongs to the icon, so it is sized by the icon, not the card.
    shadow.paste(drop, (at[0], at[1] + max(2, big.height // 24)), drop)
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(2, big.height // 14)))

    canvas = Image.alpha_composite(ground.convert("RGBA"), shadow)
    canvas.paste(big, at, big)
    return _jpeg(canvas)


def _jpeg(canvas: Image.Image) -> bytes:
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


async def look_of(repo: Repo, style: str | None = None) -> Look:
    """The admin's style, card, scale and low-resolution limit, read on every post so a change
    applies at once; `style` overrides the admin's (the DM test)."""
    stored_style = await repo.get_app_setting(STYLE_KEY)
    size = await repo.get_app_setting(SIZE_KEY)
    scale = await repo.get_app_setting(SCALE_KEY)
    low_res = await repo.get_app_setting(LOW_RES_KEY)
    return Look(
        style=style or (stored_style if stored_style in STYLES else STYLE_DEFAULT),
        size=size if size in SIZES else SIZE_DEFAULT,
        scale=int(scale) if scale in {str(n) for n in SCALES} else SCALE_DEFAULT,
        low_res=(int(low_res) if low_res in {str(n) for n in LOW_RES_CHOICES} else LOW_RES_DEFAULT),
    )


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


def _low_res_bytes(data: bytes, limit: int) -> bool:
    """Whether a picture is low-resolution, from its header alone."""
    try:
        with Image.open(io.BytesIO(data)) as picture:
            return max(picture.size) < limit
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return False


async def build(
    icon_sources: Sequence[str], cover_sources: Sequence[str], look: Look
) -> bytes | None:
    """A post's enlarged picture on its card, from the first icon source that
    loads (a file or a URL), on the first cover that loads; None — send the
    original as it is — when the style is off, the icon is of high
    resolution, nothing loads, or what loaded is not a picture."""
    if not look.on or not icon_sources:
        return None
    key = (
        look.style,
        look.size,
        look.scale,
        look.low_res,
        icon_sources[0],
        cover_sources[0] if cover_sources else "",
    )
    if key in _memo:
        _memo.move_to_end(key)
        return _memo[key] or None
    icon = await _first(icon_sources)
    if icon is None:
        return None
    composed: bytes | None = None
    if _low_res_bytes(icon[1], look.low_res):
        cover = await _first(cover_sources) if look.style == STYLE_COVER else None
        try:
            composed = await asyncio.to_thread(compose, icon[1], look, cover[1] if cover else None)
        except Exception:
            log.exception("could not compose a post picture from %s", icon[0])
            return None
    # A high-resolution icon is remembered too, as nothing to draw: the next
    # chat's copy of the post does not fetch it again.
    _memo[key] = composed or b""
    if len(_memo) > _MEMO_SIZE:
        _memo.popitem(last=False)
    return composed
