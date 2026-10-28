"""A prize's picture in the season pass (owner, 2026-10-27), and a month's
cover (2026-10-28): what the
super-admin uploads, decoded and saved again as a JPEG — the server does not
trust the bytes it is sent, as with a person's own avatar
(`custom_avatars.py`). Kept under `data/covers/pass/`, the path relative."""

from __future__ import annotations

import asyncio
import hashlib
import io
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

#: What the endpoint reads at most: a phone photo sent as it is fits.
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
#: The stored picture's longest side: a card's banner on a phone.
SIDE = 1280
MAX_PIXELS = 60_000_000
_FORMATS = {"JPEG", "PNG", "WEBP"}
DIR = Path("data") / "covers" / "pass"


def normalize(body: bytes) -> bytes | None:
    """The picture as a JPEG at most `SIDE` px on its longer side, or None when
    it is not a JPEG/PNG/WebP image."""
    try:
        with Image.open(io.BytesIO(body)) as image:
            if image.format not in _FORMATS:
                return None
            width, height = image.size
            if width < 1 or height < 1 or width * height > MAX_PIXELS:
                return None
            image.draft("RGB", (SIDE, SIDE))
            picture = ImageOps.exif_transpose(image).convert("RGB")
            picture.thumbnail((SIDE, SIDE))
            out = io.BytesIO()
            picture.save(out, format="JPEG", quality=86, optimize=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None


async def store(
    reward_id: int | str, body: bytes, root: Path | None = None, *, kind: str = "reward"
) -> str | None:
    """Save the picture of a prize (or, `kind` "season", a month's cover); its
    path relative to `root`, or None when `body` is no picture."""
    picture = await asyncio.to_thread(normalize, body)
    if picture is None:
        return None
    name = f"{kind}-{reward_id}-{hashlib.sha256(picture).hexdigest()[:12]}.jpg"
    folder = (root or Path.cwd()) / DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(picture)
    return (DIR / name).as_posix()


def read(path: str, root: Path | None = None) -> bytes:
    return ((root or Path.cwd()) / path).read_bytes()


def remove(path: str | None, root: Path | None = None) -> None:
    if not path:
        return
    try:
        ((root or Path.cwd()) / path).unlink(missing_ok=True)
    except OSError:
        pass
