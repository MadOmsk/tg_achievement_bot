"""Where a downloaded profile picture goes, and how it gets there (#55).

The pictures live as files under `data/avatars/`, not as rows: the database
is copied before every deploy and read by scripts, and a few megabytes of
JPEG per person would make a routine backup expensive for no reason. The
row keeps the path.

One file per subject, overwritten in place — `tg-319472587.jpg`,
`steam-76561197960287930.jpg`. A person has one current face; keeping the
old ones would be a gallery nobody asked for, and the name staying stable is
what lets the mini-app link to it without asking the database twice.

Nothing here decides *when* to fetch: that is `poller/avatars.py`, which
looks at each subject about once a week.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

AVATAR_DIR = Path("data/avatars")

# Xbox and PSN both hand out pictures well over 1MB at their largest sizes,
# and a face in a list is displayed at 50 pixels. This is a sanity bound
# against a redirect to something that is not an image at all, not a quality
# setting.
MAX_BYTES = 4 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 20


def avatar_dir(root: Path | None = None) -> Path:
    return (root or Path.cwd()) / AVATAR_DIR


async def download(url: str, name: str, *, root: Path | None = None) -> tuple[str, str] | None:
    """Fetch one picture and write it as `name`. Returns `(path, hash)`
    relative to the avatar directory, or `None` when the fetch failed —
    which is an ordinary outcome, not an error: a platform CDN having a bad
    minute must never fail the poll tick it rides on.
    """
    try:
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as c:
            response = await c.get(url)
            response.raise_for_status()
            payload = response.content
    except Exception as exc:
        log.info("avatar download failed for %s: %r", name, exc)
        return None

    if not payload or len(payload) > MAX_BYTES:
        log.info("avatar for %s ignored: %s bytes", name, len(payload))
        return None

    directory = avatar_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(payload)
    return name, hashlib.sha256(payload).hexdigest()


def write(payload: bytes, name: str, *, root: Path | None = None) -> tuple[str, str]:
    """The same, for bytes already in hand — Telegram's photo arrives through
    the bot API rather than over plain HTTP."""
    directory = avatar_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(payload)
    return name, hashlib.sha256(payload).hexdigest()


def telegram_name(tg_id: int) -> str:
    return f"tg-{tg_id}.jpg"


def account_name(platform: str, external_id: str) -> str:
    # An external id is a XUID, a SteamID64 or a PSN account_id — digits, or
    # digits and dashes. Sanitized anyway: this becomes a filename.
    safe = "".join(char for char in external_id if char.isalnum() or char in "-_")
    return f"{platform}-{safe}.jpg"
