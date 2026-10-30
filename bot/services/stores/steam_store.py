"""A Steam app as the storefront describes it: `appdetails`, one request per
app and language, no key. The storefront answers about 200 requests in five
minutes; the limiter below keeps well under it."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime

import httpx

from bot.services.rate_limiter import RateLimiter
from bot.services.stores import StoreDlc, StoreVersion, without_keys

log = logging.getLogger(__name__)

APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
# One request every 1.6 s at most, 150 in five minutes.
LIMITER = RateLimiter(((1, 1.6), (150, 300.0)))

# A price and what is said about it (a package's option text is its name and
# price, "Skyrim - $39.99"): not kept (`stores.without_keys`).
PRICE_KEYS = frozenset(
    {
        "price_overview",
        "price",
        "price_in_cents_with_discount",
        "percent_savings",
        "percent_savings_text",
        "option_text",
        "save_text",
    }
)

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
    return without_prices(entry.get("data")) if entry.get("success") else None


ITEMS_URL = "https://api.steampowered.com/IStoreBrowseService/GetItems/v1/"
ASSETS_HOST = "https://shared.steamstatic.com/store_item_assets/"
# One request names this many apps.
ITEMS_PER_CALL = 100


# Steam's library art, as `versions.media` keeps it: the portrait capsule
# (600x900) is the poster, the wide library hero the page's head.
LIBRARY_ART = {"poster": "library_capsule", "hero": "library_hero"}


async def library_art(appids: list[str]) -> dict[str, dict[str, str]]:
    """Each app's current library art by appid, `{"poster": url, "hero": url}`
    (owner, 2026-10-30): the fixed `library_600x900.jpg` keeps the art a game
    had when its library page was made, while a live game changes it every
    season, kept in a folder named by a hash that only the store knows. A
    hundred apps a request, no key; an app with none is left out. Raises on a
    network failure."""
    found: dict[str, dict[str, str]] = {}
    for start in range(0, len(appids), ITEMS_PER_CALL):
        batch = appids[start : start + ITEMS_PER_CALL]
        request = {
            "ids": [{"appid": int(appid)} for appid in batch],
            "context": {"language": "english", "country_code": "US"},
            "data_request": {"include_assets": True},
        }
        await LIMITER.acquire()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(ITEMS_URL, params={"input_json": json.dumps(request)})
        response.raise_for_status()
        for item in (response.json().get("response") or {}).get("store_items") or []:
            assets = item.get("assets") or {}
            form = assets.get("asset_url_format")
            if not item.get("appid") or not form or "${FILENAME}" not in form:
                continue
            art = {}
            for role, asset in LIBRARY_ART.items():
                name = assets.get(f"{asset}_2x") or assets.get(asset)
                if name:
                    art[role] = ASSETS_HOST + form.replace("${FILENAME}", name)
            if art:
                found[str(item["appid"])] = art
    return found


def without_prices(data: dict | None) -> dict | None:
    return without_keys(data, PRICE_KEYS) if data else data  # type: ignore[return-value]


SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
PACKAGES_URL = "https://store.steampowered.com/api/packagedetails"


async def search(term: str) -> list[dict]:
    """The storefront's hits for a name: `id`, `name`, `type`."""
    await LIMITER.acquire()
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.get(SEARCH_URL, params={"term": term, "cc": "us", "l": "en"})
    response.raise_for_status()
    return list((response.json() or {}).get("items") or [])


async def package(package_id: str) -> dict | None:
    """A package (an edition the app is sold as): its name and its apps."""
    await LIMITER.acquire()
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.get(PACKAGES_URL, params={"packageids": package_id, "cc": "us"})
    response.raise_for_status()
    entry = (response.json() or {}).get(str(package_id)) or {}
    return without_prices(entry.get("data")) if entry.get("success") else None


def sold_package_ids(data: dict) -> list[str]:
    """The packages an app's page sells it as now: its editions on sale."""
    return [
        str(sub["packageid"])
        for group in data.get("package_groups") or []
        for sub in group.get("subs") or []
        if sub.get("packageid")
    ]


def package_ids(data: dict) -> list[str]:
    """Every package the app is in, sold now or no longer (`packages` keeps
    the ones a store page stopped offering): its editions."""
    sold = sold_package_ids(data)
    return sold + [str(p) for p in data.get("packages") or [] if str(p) not in sold]


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
        on_sale=available(data),
    )
    return version


def available(data: dict) -> bool:
    """Steam offers the app now: free, or sold as some package on its page
    (a pre-order included). Known to Steam with neither is off sale."""
    return bool(data.get("is_free")) or bool(sold_package_ids(data))


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
        on_sale=available(data),
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
    # A soundtrack or a video app keeps its own type: not a game (an extra).
    return {"game": "game", "demo": "demo", "dlc": "dlc"}.get(kind, kind)


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
