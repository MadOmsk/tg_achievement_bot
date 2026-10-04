"""A picture a person chose for themself in the Mini App (#157, migration 077).

Whatever arrives is decoded and saved again as a plain square-bounded JPEG
(`normalize`): the file on disk is then an image and nothing else — no EXIF
(a phone photo's GPS position), no bytes after the image, no oversized
canvas — whichever client sent it. The Mini App already crops and shrinks;
this is the server not trusting that.

Stored beside the Telegram photos under `data/avatars/`, a new name for every
picture so no cache keeps the old face; the previous file is removed. A
super-admin can take a picture down (`clear`) — anybody can upload anything,
and everybody sees it.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging

from PIL import Image, ImageOps, UnidentifiedImageError

from bot.db.repo import Repo
from bot.services import avatars

log = logging.getLogger(__name__)

#: What the endpoint reads at most. The app sends ~50 KB; a phone photo sent
#: as it is fits too, and is shrunk below.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
#: The stored picture's longest side.
SIDE = 512
#: Refuse to decode anything bigger than this many pixels — a small file can
#: declare a huge canvas (a decompression bomb).
MAX_PIXELS = 40_000_000
_FORMATS = {"JPEG", "PNG", "WEBP"}


def normalize(body: bytes) -> bytes | None:
    """The picture as a JPEG at most `SIDE` px on its longer side, or None when
    `body` is not a JPEG/PNG/WebP image this can read."""
    try:
        with Image.open(io.BytesIO(body)) as image:
            if image.format not in _FORMATS:
                return None
            width, height = image.size
            if width < 1 or height < 1 or width * height > MAX_PIXELS:
                return None
            image.draft("RGB", (SIDE, SIDE))  # JPEG: decode at a smaller scale
            # Honour the phone's rotation flag before it is dropped with the EXIF.
            picture = ImageOps.exif_transpose(image).convert("RGB")
            picture.thumbnail((SIDE, SIDE))
            out = io.BytesIO()
            picture.save(out, format="JPEG", quality=88, optimize=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None


async def store(repo: Repo, tg_id: int, body: bytes) -> bool:
    """Make `body` this person's picture. False when it is not an image."""
    picture = await asyncio.to_thread(normalize, body)
    if picture is None:
        return False
    name = f"custom-{tg_id}-{hashlib.sha256(picture).hexdigest()[:12]}.jpg"
    path, _digest = avatars.write(picture, name)
    previous = await repo.custom_avatar_path(await repo.person_id(tg_id))
    await repo.set_custom_avatar_path(await repo.person_id(tg_id), path)
    if previous and previous != path:
        _remove(previous)
    return True


async def clear(repo: Repo, tg_id: int) -> bool:
    """Back to the Telegram photo. False when there was no chosen picture."""
    previous = await repo.custom_avatar_path(await repo.person_id(tg_id))
    if not previous:
        return False
    await repo.set_custom_avatar_path(await repo.person_id(tg_id), None)
    _remove(previous)
    return True


def _remove(path: str) -> None:
    try:
        (avatars.avatar_dir() / path).unlink(missing_ok=True)
    except OSError as exc:
        log.warning("failed to remove a chosen picture %s: %r", path, exc)
