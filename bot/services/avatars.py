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

from pathlib import Path

from bot.services import images

AVATAR_DIR = Path("data/avatars")

#: Kept as re-exports: the poller and its tests reach for these by name, and
#: the sizes/timeouts are one decision shared with every other picture the
#: bot downloads (bot/services/images.py).
MAX_BYTES = images.MAX_BYTES
DOWNLOAD_TIMEOUT_SECONDS = images.DOWNLOAD_TIMEOUT_SECONDS


def avatar_dir(root: Path | None = None) -> Path:
    return (root or Path.cwd()) / AVATAR_DIR


async def download(url: str, name: str, *, root: Path | None = None) -> tuple[str, str] | None:
    """Fetch one picture and write it as `name`. Returns `(path, hash)`
    relative to the avatar directory, or `None` when the fetch failed —
    which is an ordinary outcome, not an error: a platform CDN having a bad
    minute must never fail the poll tick it rides on.
    """
    return await images.download(url, name, avatar_dir(root))


def write(payload: bytes, name: str, *, root: Path | None = None) -> tuple[str, str]:
    """The same, for bytes already in hand — Telegram's photo arrives through
    the bot API rather than over plain HTTP."""
    return images.write(payload, name, avatar_dir(root))


def telegram_name(tg_id: int) -> str:
    return f"tg-{tg_id}.jpg"


def account_name(platform: str, external_id: str) -> str:
    # An external id is a XUID, a SteamID64 or a PSN account_id — digits, or
    # digits and dashes. Sanitized anyway: this becomes a filename.
    return images.safe_name(platform, external_id)
