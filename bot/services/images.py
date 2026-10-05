"""Fetching a picture, bounding it, hashing it, writing it down.

Written for avatars (#55) and needed again for game covers (2026-09-18):
the two differ only in where the file lands and what it is called, so the
fetch itself lives here rather than in two copies that would drift on the
day one of them learns something.

Nothing here decides *when* to fetch or *what* to keep — that is each
caller's own poller.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

# A sanity bound against a redirect to something that is not an image at
# all, not a quality setting: Xbox and PSN both hand out pictures over a
# megabyte at their largest sizes, and a Steam library capsule is well
# under one.
MAX_BYTES = 4 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 20


async def download(url: str, name: str, directory: Path) -> tuple[str, str] | None:
    """Fetch one picture and write it as `name` inside `directory`.

    Returns `(name, sha256)`, or `None` when the fetch failed — which is an
    ordinary outcome and not an error: a platform CDN having a bad minute
    must never fail the poll tick this rides on.
    """
    try:
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as c:
            response = await c.get(url)
            response.raise_for_status()
            payload = response.content
    except Exception as exc:
        log.info("image download failed for %s: %r", name, exc)
        return None

    if not payload or len(payload) > MAX_BYTES:
        log.info("image for %s ignored: %s bytes", name, len(payload))
        return None

    return write(payload, name, directory)


def write(payload: bytes, name: str, directory: Path) -> tuple[str, str]:
    """The same, for bytes already in hand — Telegram's own photo arrives
    through the bot API rather than over plain HTTP."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(payload)
    return name, hashlib.sha256(payload).hexdigest()


def safe_name(*parts: str, suffix: str = ".jpg") -> str:
    """A filename from identifiers that came from somebody else's API.

    A XUID, a SteamID64, a PSN account_id or a title id is digits, or digits
    and dashes and underscores — sanitized anyway, because this becomes a
    path.
    """
    cleaned = [
        "".join(char for char in part if char.isalnum() or char in "-_") for part in parts if part
    ]
    return "-".join(cleaned) + suffix
