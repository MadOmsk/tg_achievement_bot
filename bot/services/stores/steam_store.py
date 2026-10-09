"""A Steam app as the storefront describes it: `appdetails`, one request per
app and language, no key. The storefront answers about 200 requests in five
minutes; the limiter below keeps well under it."""

from __future__ import annotations

import logging
import re
from datetime import datetime

import httpx

from bot.services.rate_limiter import RateLimiter
from bot.services.stores import StoreDlc, StoreVersion

log = logging.getLogger(__name__)

APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
# One request every 1.6 s at most, 150 in five minutes.
LIMITER = RateLimiter(((1, 1.6), (150, 300.0)))

# Steam's category ids that say a game keeps selling and changing.
_IN_APP_PURCHASES = 35
_MMO = 20
_MASSIVELY_MULTIPLAYER_GENRE = "29"


async def app_details(appid: str, language: str = "english") -> dict | None:
    """The storefront's `data` for one app, or None when Steam has none
    (a delisted app, a region lock) — raises on a network failure."""
    await LIMITER.acquire()
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.get(APPDETAILS_URL, params={"appids": appid, "l": language})
    response.raise_for_status()
    entry = (response.json() or {}).get(str(appid)) or {}
    return entry.get("data") if entry.get("success") else None


def parse_app(data: dict, data_ru: dict | None = None) -> StoreVersion:
    appid = str(data.get("steam_appid") or "")
    categories = {int(c.get("id", 0)) for c in data.get("categories") or [] if c.get("id")}
    genres = data.get("genres") or []
    live = bool(data.get("is_free")) and (
        _IN_APP_PURCHASES in categories
        or _MMO in categories
        or any(str(g.get("id")) == _MASSIVELY_MULTIPLAYER_GENRE for g in genres)
    )
    version = StoreVersion(
        store="steam",
        product_id=appid,
        console="steam",
        name=_text(data.get("name")),
        name_ru=_text((data_ru or {}).get("name")),
        kind=_kind(data),
        developer=_first(data.get("developers")),
        publisher=_first(data.get("publishers")),
        release_date=release_day((data.get("release_date") or {}).get("date")),
        genres=[str(g.get("description")) for g in genres if g.get("description")],
        also_on=[name for name, on in (data.get("platforms") or {}).items() if on],
        store_group=str((data.get("fullgame") or {}).get("appid") or "") or None,
        description_en=_text(data.get("short_description")),
        description_ru=_text((data_ru or {}).get("short_description")),
        media=_media(data),
        live_service=live,
        store_ids=[("steam_app", appid)],
        dlc_ids=[str(d) for d in data.get("dlc") or []],
    )
    return version


def parse_dlc(data: dict) -> StoreDlc:
    name = _text(data.get("name"))
    kind = (
        "soundtrack"
        if data.get("type") == "music" or "soundtrack" in (name or "").lower()
        else "dlc"
    )
    return StoreDlc(
        store_id=str(data.get("steam_appid") or ""),
        name=name,
        kind=kind,
        release_date=release_day((data.get("release_date") or {}).get("date")),
        description_en=_text(data.get("short_description")),
        image_url=_text(data.get("header_image")),
    )


_DATE_FORMATS = ("%d %b, %Y", "%b %d, %Y", "%d %B, %Y", "%B %d, %Y", "%Y-%m-%d")


def release_day(raw: str | None) -> str | None:
    """Steam's English release date ("18 May, 2015") as an ISO day; a month
    or a quarter ("Q1 2027", "Coming soon") is no day at all."""
    text = (raw or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _kind(data: dict) -> str:
    kind = str(data.get("type") or "game")
    return {"game": "game", "demo": "demo", "dlc": "dlc", "music": "dlc"}.get(kind, kind)


def _media(data: dict) -> dict[str, object]:
    media: dict[str, object] = {}
    if data.get("header_image"):
        media["cover"] = data["header_image"]
    if data.get("background_raw") or data.get("background"):
        media["background"] = data.get("background_raw") or data.get("background")
    shots = [s.get("path_full") for s in data.get("screenshots") or [] if s.get("path_full")]
    if shots:
        media["screenshots"] = shots
    videos = []
    for movie in data.get("movies") or []:
        url = (movie.get("mp4") or {}).get("max") or movie.get("hls_h264") or movie.get("dash_h264")
        if url:
            videos.append(
                {"name": movie.get("name"), "thumbnail": movie.get("thumbnail"), "url": url}
            )
    if videos:
        media["videos"] = videos
    if (data.get("metacritic") or {}).get("score"):
        media["metacritic"] = data["metacritic"]["score"]
    return media


def _first(values: list | None) -> str | None:
    for value in values or []:
        if text := _text(value):
            return text
    return None


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return re.sub(r"\s+", " ", value).strip() or None
