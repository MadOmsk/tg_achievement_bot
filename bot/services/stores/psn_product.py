"""A PlayStation store product page: an add-on, an edition, a demo, a theme
(#147; owner, 2026-10-15). A concept (`psn_store`) lists the ids of everything
sold under it by category and names none of them; the product's own public
page does. Network and parsing only — nothing here knows the database.

The page is read like a browser would (`store.playstation.com/<locale>/
product/<id>`), one at a time at a polite pace, and kept as its embedded JSON:
the page's `batarangs` sections (their caches carry the product, its concept,
media, ratings, description) and its `ld+json`. The sections that carry a
price (`cta`, `game-title`) are dropped, and prices anywhere else
(`psn_store.PRICE_KEYS`): they change daily and are not ours to keep."""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass, field

import httpx

from bot.services.rate_limiter import RateLimiter
from bot.services.stores import without_keys
from bot.services.stores.psn_store import PRICE_KEYS

log = logging.getLogger(__name__)

# One page every two seconds: a page is 370 KB and Sony's CDN is not ours.
LIMITER = RateLimiter(((1, 2.0), (30, 120.0)))
PAGE_URL = "https://store.playstation.com/en-us/product/{product_id}"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.8",
}
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_LD_JSON = re.compile(r'application/ld\+json"[^>]*>(.*?)</script>', re.S)
_SECTION_JSON = re.compile(r'<script[^>]*type="application/json">(.*)</script>', re.S)
# Sections that carry a price and nothing we keep.
_PRICED_SECTIONS = frozenset({"cta", "game-title", "upsells", "add-ons"})
_IMAGE_ROLES = ("GAMEHUB_COVER_ART", "MASTER", "FOUR_BY_THREE_BANNER", "PORTRAIT_BANNER")


class ProductPageGone(Exception):
    """The store has no page for this id (404): known, and not asked again soon."""


def extract(page: str) -> dict | None:
    """What a product page keeps for us, or None when it is not a product page."""
    found = _NEXT_DATA.search(page)
    if found is None:
        return None
    data = json.loads(found.group(1))
    props = (data.get("props") or {}).get("pageProps") or {}
    product_id = props.get("productId")
    if not product_id:
        return None
    sections: dict[str, object] = {}
    for name, part in (props.get("batarangs") or {}).items():
        if name in _PRICED_SECTIONS:
            continue
        block = _SECTION_JSON.search(part.get("text") or "")
        if block is not None:
            try:
                sections[name] = json.loads(block.group(1))
            except ValueError:
                continue
    ld = _LD_JSON.search(page)
    try:
        ld_data = json.loads(ld.group(1)) if ld else None
    except ValueError:
        ld_data = None
    payload = {
        "product_id": product_id,
        "locale": props.get("locale"),
        "ld": ld_data,
        "sections": sections,
    }
    return without_keys(payload, PRICE_KEYS | {"ctaLabel", "priceOrText"})  # type: ignore[return-value]


async def fetch_product(product_id: str) -> dict | None:
    """One product page, extracted. None when it is not a product page;
    `ProductPageGone` on a 404; anything else is the site's bad minute."""
    await LIMITER.acquire()
    async with httpx.AsyncClient(
        timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True
    ) as client:
        response = await client.get(PAGE_URL.format(product_id=product_id))
    if response.status_code == 404:
        raise ProductPageGone(product_id)
    response.raise_for_status()
    return extract(response.text)


@dataclass
class PsnProduct:
    product_id: str
    name: str | None = None
    category: str | None = None  # "Add-on", "Game", ... as the page's ld+json says
    classification: str | None = None  # storeDisplayClassification: OTHER, FULL_GAME, ...
    concept_id: str | None = None
    description: str | None = None
    release_date: str | None = None  # ISO day
    publisher: str | None = None
    genres: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    image_url: str | None = None
    rating: str | None = None


def _products(payload: dict) -> dict:
    """Every cached record of this product across the page's sections, merged."""
    wanted = f"Product:{payload['product_id']}"
    merged: dict = {}
    for section in (payload.get("sections") or {}).values():
        cache = (section or {}).get("cache") or {}
        for key, record in cache.items():
            if key.startswith(wanted) and isinstance(record, dict):
                merged.update({k: v for k, v in record.items() if v not in (None, [], "")})
    return merged


def _plain(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip() or None


def parse_product(payload: dict) -> PsnProduct:
    record = _products(payload)
    ld = payload.get("ld") or {}
    description = next(
        (d.get("value") for d in record.get("descriptions") or [] if d.get("type") == "LONG"),
        None,
    ) or ld.get("description")
    images = {
        m.get("role"): m.get("url") for m in record.get("media") or [] if m.get("type") == "IMAGE"
    }
    concept = record.get("concept") or {}
    released = str(record.get("releaseDate") or "")[:10] or None
    return PsnProduct(
        product_id=str(payload["product_id"]),
        name=record.get("name") or ld.get("name"),
        category=ld.get("category"),
        classification=record.get("storeDisplayClassification"),
        concept_id=(concept.get("__ref") or "").removeprefix("Concept:") or None,
        description=_plain(description),
        release_date=released,
        publisher=record.get("publisherName"),
        genres=[g["value"] for g in record.get("localizedGenres") or [] if g.get("value")],
        platforms=[str(p) for p in record.get("platforms") or []],
        image_url=next((images[r] for r in _IMAGE_ROLES if images.get(r)), None),
        rating=(record.get("contentRating") or {}).get("description"),
    )
