"""Telegram profile-photo proxy for the Mini App.

The SPA cannot read anyone else's avatar from ``initData`` — only the current
user's ``photo_url``. Everyone else is ``users.photo_file_id`` from the
database: download those bytes, or there is no face. No live
``getUserProfilePhotos`` from this path. Bytes are cached in-process so a
club roster doesn't hammer Telegram on every paint. The bot token never
leaves this module.
"""

from __future__ import annotations

import logging
import time
from io import BytesIO
from typing import Any

from aiogram.exceptions import TelegramAPIError

log = logging.getLogger(__name__)

HIT_TTL_SECONDS = 6 * 3600
MISS_TTL_SECONDS = 15 * 60

# tg_id -> (expires_at, bytes or None for a confirmed miss, mime)
_cache: dict[int, tuple[float, bytes | None, str]] = {}


def clear_avatar_cache() -> None:
    _cache.clear()


def _mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return "image/webp"
    return "image/jpeg"


def _from_cache(tg_id: int) -> tuple[bytes, str] | object | None:
    """Hit bytes, ``None`` for a cached miss, or a sentinel if nothing stored."""
    row = _cache.get(tg_id)
    if row is None:
        return _MISSING
    expires_at, body, mime = row
    if expires_at <= time.time():
        _cache.pop(tg_id, None)
        return _MISSING
    if body is None:
        return None
    return body, mime


_MISSING = object()


async def load_avatar_bytes(
    bot: Any, tg_id: int, *, file_id: str | None = None
) -> tuple[bytes, str] | None:
    cached = _from_cache(tg_id)
    if cached is not _MISSING:
        if cached is None:
            return None
        return cached  # type: ignore[return-value]

    if not file_id:
        _cache[tg_id] = (time.time() + MISS_TTL_SECONDS, None, "")
        return None

    buffer = BytesIO()
    try:
        await bot.download(file_id, destination=buffer)
    except TelegramAPIError:
        log.info("telegram photo download unavailable tg_id=%s", tg_id)
        _cache[tg_id] = (time.time() + MISS_TTL_SECONDS, None, "")
        return None
    except Exception:
        log.exception("telegram photo download failed tg_id=%s", tg_id)
        _cache[tg_id] = (time.time() + MISS_TTL_SECONDS, None, "")
        return None

    body = buffer.getvalue()
    if not body:
        _cache[tg_id] = (time.time() + MISS_TTL_SECONDS, None, "")
        return None
    mime = _mime(body)
    _cache[tg_id] = (time.time() + HIT_TTL_SECONDS, body, mime)
    return body, mime
