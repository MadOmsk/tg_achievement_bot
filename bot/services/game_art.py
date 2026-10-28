"""A game's poster, hero and header art kept on our disk and served from it
(owner, 2026-10-28): the Mini App never loads them from a store's CDN.

A picture is named by its store address, signed (`sign`), so the public
route `/api/mini/art/{sig}?u=<address>` fetches only addresses this server
handed out — a stranger cannot make it download whatever they like. The
first request downloads it, shrinks it like an achievement icon (at most
1280 px) and keeps it under `data/covers/art/`; every later one reads the
file. The octopus fetches a game's art as it assembles it (`ensure`). An
address marked as a 360 game's art (`x360_frame.MARK`) is kept without the
console's frame.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

from bot.services import achievement_icons, images, x360_frame

log = logging.getLogger(__name__)

ART_DIR = Path("data/covers/art")
ROUTE = "/api/mini/art"
DOWNLOAD_TIMEOUT_SECONDS = 20.0
# Xbox's hero art comes at 1920 px and several MB; what is kept is shrunk.
MAX_BYTES = 16 * 1024 * 1024
# A picture that could not be fetched is not asked for again for this long.
MISS_SECONDS = 3600
_EXTENSIONS = (".jpg", ".png", ".webp")
# The stores' picture hosts, matched by suffix; nothing else is fetched.
HOSTS = (
    "microsoft.com",
    "s-microsoft.com",
    "xboxlive.com",
    "xboxservices.com",
    "steamstatic.com",
    "akamaihd.net",
    "playstation.com",
    "playstation.net",
)

_secret: bytes | None = None
_misses: dict[str, float] = {}
_locks: dict[str, asyncio.Lock] = {}


def configure(fernet_key: str) -> None:
    """Key the signatures off the app's own secret; until then (tests,
    scripts) `served` hands addresses back unchanged."""
    global _secret
    _secret = hashlib.sha256(b"game-art:" + fernet_key.encode()).digest()


def allowed(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == h or host.endswith("." + h) for h in HOSTS)


def sign(url: str) -> str:
    assert _secret is not None
    return hmac.new(_secret, url.encode(), hashlib.sha256).hexdigest()[:32]


def served(url: str | None) -> str | None:
    """Where the Mini App reads `url` from: our route for a store picture,
    the address itself for anything else (or before `configure`)."""
    if not url or _secret is None or not allowed(url):
        return url
    return f"{ROUTE}/{sign(url)}?u={quote(url, safe='')}"


def art_dir(root: Path | None = None) -> Path:
    return (root or Path.cwd()) / ART_DIR


def file_key(url: str) -> str:
    """The file's name: the address hashed, not signed, so a script with
    another key (or none) finds the same files the bot keeps."""
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def _path(key: str, ext: str, root: Path | None) -> Path:
    return art_dir(root) / key[:2] / f"{key}{ext}"


def cached(url: str, *, root: Path | None = None) -> Path | None:
    key = file_key(url)
    for ext in _EXTENSIONS:
        path = _path(key, ext, root)
        if path.is_file():
            return path
    return None


async def _fetch(url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as c:
            response = await c.get(images.current_url(url))
            response.raise_for_status()
            payload = response.content
    except Exception as exc:
        log.info("game art fetch failed: %r", exc)
        return None
    if not payload or len(payload) > MAX_BYTES:
        return None
    return payload


async def get(url: str, *, root: Path | None = None) -> tuple[bytes, str] | None:
    """The picture's bytes and MIME, from disk or downloaded and kept now;
    None when the store has none (remembered for an hour)."""
    key = file_key(url)
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        try:
            path = cached(url, root=root)
            if path is not None:
                data = await asyncio.to_thread(path.read_bytes)
                return data, achievement_icons.detect_mime(data)[0]
            if time.monotonic() - _misses.get(key, -MISS_SECONDS) < MISS_SECONDS:
                return None
            data = await _fetch(url)
            if data is None:
                _misses[key] = time.monotonic()
                return None
            if x360_frame.marked(url):
                data = await asyncio.to_thread(x360_frame.strip, data)
            data = await asyncio.to_thread(achievement_icons.shrink, data)
            mime, ext = achievement_icons.detect_mime(data)
            path = _path(key, ext, root)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(path.name + ".part")
                temporary.write_bytes(data)
                temporary.replace(path)
            except OSError as exc:
                log.warning("failed writing game art %s: %r", path, exc)
            return data, mime
        finally:
            _locks.pop(key, None)


async def ensure(urls: list[str | None], *, root: Path | None = None) -> int:
    """Keep each store picture of `urls` on disk; how many were fetched now."""
    fetched = 0
    for url in dict.fromkeys(u for u in urls if u and allowed(u)):
        if cached(url, root=root) is None and await get(url, root=root):
            fetched += 1
    return fetched
