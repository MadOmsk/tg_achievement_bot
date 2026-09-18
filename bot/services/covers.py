"""Where a downloaded game cover goes (owner request, 2026-09-18).

The same shape `services/avatars.py` gives faces, for the art the Mini App
shows beside every achievement: the URL is kept in `titles.icon_url`, the
downloaded copy lands in `data/covers/`, and `titles.cover_path` maps the
row to the file.

Files rather than rows, for the reason the avatars have: the database is
copied before every deploy and read by scripts, and a few hundred megabytes
of JPEG would make a routine backup expensive for nothing.

**The filename carries the platform, not just the title id.** A Steam appid
and an Xbox title id are both bare numbers and can collide by accident —
CLAUDE.md says so about grouping, and `titles` is keyed by `title_id` alone,
so the file is the one place the collision can still be kept apart.

Nothing here decides *when* to fetch: that is `poller/covers.py`.
"""

from __future__ import annotations

from pathlib import Path

from bot.services import images

COVER_DIR = Path("data/covers")


def cover_dir(root: Path | None = None) -> Path:
    return (root or Path.cwd()) / COVER_DIR


def cover_name(platform: str | None, title_id: str) -> str:
    return images.safe_name(platform or "unknown", title_id)


async def download(url: str, name: str, *, root: Path | None = None) -> tuple[str, str] | None:
    """Fetch one cover and write it as `name`. `(name, sha256)`, or `None`
    when the fetch failed — an ordinary outcome for somebody else's CDN, and
    never a reason to fail the tick this rides on."""
    return await images.download(url, name, cover_dir(root))
