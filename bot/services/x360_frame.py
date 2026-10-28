"""Xbox 360 box art without the console's frame (owner, 2026-10-28).

Microsoft hands a 360 game's art out framed: the portrait box art (219×300)
under a header — the "XBOX 360" logo with its green swoosh, Platinum Hits,
Games for Windows LIVE or ARCADE —, the store's 2:3 poster (720×1080) under
a white "XBOX 360" band, the square tile (1080×1080) beside a green "XBOX
360" bar. Both are cut off before the picture is kept: a list's
cover (`covers`) and a game's poster (`game_art`) alike.

The frame is one template, so the cut is a share of the size — measured on
every 360 cover we had: the header ends at 38 of 300 rows, the store poster's
band at 125 of 1080, the bar at 189 of 1080 columns. Anything else (a small
icon, a modern game's art) is left as it came; a picture already cut is
neither shape, so cutting twice changes nothing.
"""

from __future__ import annotations

import io
import logging

from PIL import Image, ImageStat

log = logging.getLogger(__name__)

# A URL marked so is a 360 game's art: `game_art` strips its frame. A
# fragment is never sent to the server, so the address still fetches.
MARK = "#x360"

HEADER = 0.13  # of the portrait's height
BAR = 190 / 1080  # of the square's width
PORTRAIT = (0.70, 0.76)  # 219×300 is 0.73
PORTRAIT_MAX = 400  # wider is no box art: a store poster cut once is 0.75 too
BAND = 126 / 1080  # of the store poster's height
POSTER = (0.66, 0.675)  # 720×1080 is 0.667
SQUARE_MIN = 1000  # smaller squares are icons, not the framed tile


def mark(url: str | None, platform: str | None) -> str | None:
    """`url`, marked as a 360 game's art when its list is a 360 list."""
    if not url or platform != "xbox_360" or url.endswith(MARK):
        return url
    return url + MARK


def marked(url: str) -> bool:
    return url.endswith(MARK)


def _green_corner(image: Image.Image) -> bool:
    """The bar's top is green; a tile of another kind is not."""
    w, h = image.size
    r, g, b = ImageStat.Stat(
        image.convert("RGB").crop((int(w * 0.02), int(h * 0.02), int(w * 0.15), int(h * 0.12)))
    ).mean
    return g > r + 20 and g > b + 20


def _white_corner(image: Image.Image) -> bool:
    """The band is white at its left, behind the logo; a poster is not."""
    w, h = image.size
    r, g, b = ImageStat.Stat(image.convert("RGB").crop((0, 0, int(w * 0.03), int(h * 0.1)))).mean
    return min(r, g, b) > 235


def strip(data: bytes) -> bytes:
    """The picture without its 360 frame, as JPEG; `data` itself when it
    shows none (or cannot be read)."""
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        log.info("360 art not readable: %r", exc)
        return data
    w, h = image.size
    if w < PORTRAIT_MAX and PORTRAIT[0] <= w / h <= PORTRAIT[1]:
        box = (0, round(h * HEADER), w, h)
    elif POSTER[0] <= w / h <= POSTER[1] and _white_corner(image):
        box = (0, round(h * BAND), w, h)
    elif w == h and w >= SQUARE_MIN and _green_corner(image):
        box = (round(w * BAR), 0, w, h)
    else:
        return data
    out = io.BytesIO()
    image.convert("RGB").crop(box).save(out, "JPEG", quality=90)
    return out.getvalue()
