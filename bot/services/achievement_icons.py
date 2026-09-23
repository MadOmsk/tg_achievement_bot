"""Local storage and caching for achievement icons (#99, owner request 2026-09-23).

Icons are saved to `data/achievements/{platform}/` to eliminate repeat
downloads from platform CDNs (Xbox Live, Steam, Sony) when users browse the Mini App.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from bot.db.repo import Repo

log = logging.getLogger(__name__)

ACHIEVEMENTS_DIR = Path("data/achievements")
DOWNLOAD_TIMEOUT_SECONDS = 15.0
MAX_BYTES = 4 * 1024 * 1024  # 4MB sanity bound

_HEX_CHARS = set("0123456789abcdefABCDEF")
_KNOWN_EXTENSIONS = (".png", ".jpg", ".webp", ".jpeg")


def achievements_dir(root: Path | None = None) -> Path:
    return (root or Path.cwd()) / ACHIEVEMENTS_DIR


def platform_dir(platform: str, *, root: Path | None = None) -> Path:
    return achievements_dir(root) / platform.lower()


def detect_mime(data: bytes) -> tuple[str, str]:
    """Detect MIME type and matching extension from image header bytes."""
    if data.startswith(b"\x89PNG"):
        return "image/png", ".png"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return "image/webp", ".webp"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    return "image/png", ".png"


def safe_part(val: str | int, fallback: str = "0") -> str:
    """Sanitize path component for game id or achievement id."""
    text = str(val).strip()
    clean = "".join(c for c in text if c.isalnum() or c in "-_")
    if not clean:
        return fallback
    if (
        any(
            c not in "-_0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
            for c in text
        )
        or len(text) > 40
    ):
        digest = hashlib.sha256(text.encode()).hexdigest()[:8]
        return f"{clean[:20]}_{digest}"
    return clean


def game_icon_dir(platform: str, title_id: str, *, root: Path | None = None) -> Path:
    """Return the game-specific directory under data/achievements/{platform}/{title_id}/."""
    return achievements_dir(root) / platform.lower() / safe_part(title_id)


def x360_icon_path(title_hex: str, image_hex: str, *, root: Path | None = None) -> Path:
    """Xbox 360 icon path under data/achievements/xbox_360/{title_hex}/{image_hex}.png."""
    return achievements_dir(root) / "xbox_360" / title_hex.lower() / f"{image_hex.lower()}.png"


def find_cached_icon(
    platform: str, title_id: str, achievement_id: str, *, root: Path | None = None
) -> Path | None:
    """Check if an icon already exists on disk under any known image extension."""
    if platform.lower() in ("xbox_360", "xbox360"):
        try:
            p = x360_icon_path(f"{int(title_id):08x}", f"{int(achievement_id):x}", root=root)
            if p.is_file():
                return p
        except (ValueError, TypeError):
            pass
        # Fallback check for flat path
        flat = (
            achievements_dir(root)
            / "xbox_360"
            / f"{safe_part(title_id)}_{safe_part(achievement_id)}.png"
        )
        if flat.is_file():
            return flat

    g_dir = game_icon_dir(platform, title_id, root=root)
    ach_name = safe_part(achievement_id)
    for ext in _KNOWN_EXTENSIONS:
        candidate = g_dir / f"{ach_name}{ext}"
        if candidate.is_file():
            return candidate

    # Legacy flat platform directory fallback
    flat_dir = platform_dir(platform, root=root)
    for ext in _KNOWN_EXTENSIONS:
        flat_candidate = flat_dir / f"{safe_part(title_id)}_{ach_name}{ext}"
        if flat_candidate.is_file():
            return flat_candidate

    return None


async def get_or_download_x360_icon(
    title_hex: str, image_hex: str, *, root: Path | None = None
) -> tuple[bytes, str] | None:
    """Get x360 icon bytes and mime from disk, or download and persist to disk."""
    title_hex = title_hex.lower()
    image_hex = image_hex.lower()
    if not (set(title_hex).issubset(_HEX_CHARS) and set(image_hex).issubset(_HEX_CHARS)):
        return None

    path = x360_icon_path(title_hex, image_hex, root=root)
    if path.is_file():
        try:
            return path.read_bytes(), "image/png"
        except OSError as exc:
            log.warning("failed reading cached x360 icon %s: %r", path, exc)

    url = f"http://image.xboxlive.com/global/t.{title_hex}/ach/0/{image_hex}"
    try:
        async with httpx.AsyncClient(
            timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and resp.content:
                data = resp.content
                if len(data) <= MAX_BYTES:
                    try:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(data)
                    except OSError as exc:
                        log.warning("failed writing cached x360 icon %s: %r", path, exc)
                    return data, "image/png"
            if resp.status_code == 404:
                return None
    except Exception as exc:
        log.info("failed downloading x360 icon %s: %r", url, exc)
    return None


async def get_or_download_achievement_icon(
    repo: Repo,
    platform: str,
    title_id: str,
    achievement_id: str,
    *,
    url: str | None = None,
    root: Path | None = None,
) -> tuple[bytes, str] | None:
    """Get achievement icon bytes and mime from disk, or download and persist to disk."""
    cached = find_cached_icon(platform, title_id, achievement_id, root=root)
    if cached is not None:
        try:
            data = cached.read_bytes()
            mime, _ = detect_mime(data)
            return data, mime
        except OSError as exc:
            log.warning("failed reading cached icon %s: %r", cached, exc)

    if not url:
        url = await repo.achievement_icon_url(platform, title_id, achievement_id)
    if not url:
        return None

    # If it's an x360 URL, delegate to x360 downloader
    if url.startswith("http://image.xboxlive.com/global/t."):
        parts = url.split("/")
        if len(parts) >= 8 and parts[4].startswith("t."):
            t_hex = parts[4][2:]
            img_hex = parts[7].removesuffix(".png")
            return await get_or_download_x360_icon(t_hex, img_hex, root=root)

    try:
        async with httpx.AsyncClient(
            timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and resp.content:
                data = resp.content
                if len(data) <= MAX_BYTES:
                    mime, ext = detect_mime(data)
                    g_dir = game_icon_dir(platform, title_id, root=root)
                    save_path = g_dir / f"{safe_part(achievement_id)}{ext}"
                    try:
                        g_dir.mkdir(parents=True, exist_ok=True)
                        save_path.write_bytes(data)
                    except OSError as exc:
                        log.warning("failed writing cached icon %s: %r", save_path, exc)
                    return data, mime
            if resp.status_code == 404:
                return None
    except Exception as exc:
        log.info(
            "failed downloading icon for %s/%s/%s from %s: %r",
            platform,
            title_id,
            achievement_id,
            url,
            exc,
        )
    return None


async def pre_cache_icon(
    platform: str,
    title_id: str,
    achievement_id: str,
    icon_url: str,
    *,
    root: Path | None = None,
) -> None:
    """Best-effort background pre-cache of an icon to disk."""
    try:
        if find_cached_icon(platform, title_id, achievement_id, root=root) is not None:
            return
        if icon_url.startswith("http://image.xboxlive.com/global/t."):
            parts = icon_url.split("/")
            if len(parts) >= 8 and parts[4].startswith("t."):
                t_hex = parts[4][2:]
                img_hex = parts[7].removesuffix(".png")
                await get_or_download_x360_icon(t_hex, img_hex, root=root)
                return

        g_dir = game_icon_dir(platform, title_id, root=root)
        async with httpx.AsyncClient(
            timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True
        ) as client:
            resp = await client.get(icon_url)
            if resp.status_code == 200 and resp.content and len(resp.content) <= MAX_BYTES:
                _mime, ext = detect_mime(resp.content)
                save_path = g_dir / f"{safe_part(achievement_id)}{ext}"
                g_dir.mkdir(parents=True, exist_ok=True)
                save_path.write_bytes(resp.content)
    except Exception as exc:
        log.debug("pre_cache_icon ignored failure for %s/%s: %r", title_id, achievement_id, exc)


def format_achievement_icon_url(
    platform: str | None,
    title_id: str | None,
    achievement_id: str | None,
    raw_icon_url: str | None,
) -> str | None:
    """Format an achievement icon URL for client delivery in Mini App."""
    if not raw_icon_url:
        return None
    # 1. Xbox 360 image.xboxlive.com -> /api/mini/x360-icon/{title_hex}/{image_hex}
    if raw_icon_url.startswith("http://image.xboxlive.com/global/t."):
        parts = raw_icon_url.split("/")
        if len(parts) >= 8 and parts[4].startswith("t."):
            title_hex = parts[4][2:]
            image_hex = parts[7].removesuffix(".png")
            return f"/api/mini/x360-icon/{title_hex}/{image_hex}"
    # 2. Local proxy: /api/mini/ach-icon/{platform}/{title_id}/{achievement_id}
    if platform and title_id and achievement_id:
        return f"/api/mini/ach-icon/{platform}/{title_id}/{achievement_id}"
    # 3. Fallback: ensure https
    if raw_icon_url.startswith("http://"):
        return "https://" + raw_icon_url[len("http://") :]
    return raw_icon_url
