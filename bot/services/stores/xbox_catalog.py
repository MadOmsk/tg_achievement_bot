"""An Xbox game as the Microsoft Store catalog describes it: `displaycatalog`,
public, no token. Found by our own title id (`lookup?alternateId=XboxTitleId`),
so no person's login is spent and no refresh token is touched.

One product is one version per console it is made for — the generations the
store calls it optimized for (Smart Delivery: One and Series); a One game
that runs on Series only by backward compatibility is a One version, Series
in its `also_on` (2026-10-12: 879 such "Series versions" were phantoms).
Play Anywhere's PC (a SKU's `XboxXPA`) is `also_on` too, never a version of
its own. A game does not list its add-ons: its related products are its
editions (Deluxe, Ultimate — "Bundle"), and what an edition bundles beside
the game is the add-ons. Of those a Durable is kept, and only when it names
this game as its own (`addOnParent`): an edition of several games bundles
other games' add-ons too. A Consumable (currency, packs) is left out. An
add-on sold only on its own is not found this way."""

from __future__ import annotations

import logging
import re

import httpx

from bot.services.rate_limiter import RateLimiter
from bot.services.stores import StoreDlc, StoreVersion, without_keys

log = logging.getLogger(__name__)

CATALOG = "https://displaycatalog.mp.microsoft.com/v7.0/products"
_PARAMS = {"market": "US", "languages": "en-US"}
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
LIMITER = RateLimiter(((1, 1.0), (100, 300.0)))
# The catalog takes several ids per request; it answers about twenty well.
BATCH = 20

_CONSOLES = {"ConsoleGen8": "one", "ConsoleGen9": "series"}

# Prices, their history and the price offers on them: not kept
# (`stores.without_keys`); whether a product is sold is its actions.
PRICE_KEYS = frozenset(
    {"Price", "HistoricalBestAvailabilities", "BIBlob", "HasXPriceStorewideOffer", "OfferProvider"}
)


def without_prices(products: list[dict]) -> list[dict]:
    return without_keys(products, PRICE_KEYS)  # type: ignore[return-value]


async def products_for_title(title_id: str) -> list[dict]:
    """The catalog's products that carry this Xbox title id."""
    await LIMITER.acquire()
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.get(
            f"{CATALOG}/lookup",
            params={
                "alternateId": "XboxTitleId",
                "value": title_id,
                "fieldsTemplate": "details",
                **_PARAMS,
            },
        )
    response.raise_for_status()
    return without_prices(list((response.json() or {}).get("Products") or []))


async def search(name: str) -> list[dict]:
    """The catalog's games for a name (its autosuggest): `ProductId`, `Title`,
    `Type`. 360 games played on One are here under ids of their own."""
    await LIMITER.acquire()
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.get(
            f"{CATALOG.rsplit('/', 1)[0]}/productFamilies/autosuggest",
            params={"query": name, "productFamilyNames": "Games", **_PARAMS},
        )
    response.raise_for_status()
    found: list[dict] = []
    for family in (response.json() or {}).get("Results") or []:
        found += [p for p in family.get("Products") or [] if p.get("ProductId")]
    return found


async def products(big_ids: list[str]) -> list[dict]:
    """The catalog's products for these ids, a batch at a time."""
    found: list[dict] = []
    for start in range(0, len(big_ids), BATCH):
        batch = big_ids[start : start + BATCH]
        await LIMITER.acquire()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(CATALOG, params={"bigIds": ",".join(batch), **_PARAMS})
        response.raise_for_status()
        found += list((response.json() or {}).get("Products") or [])
    return without_prices(found)


def consoles_of(product: dict) -> tuple[list[str], list[str]]:
    """(the consoles it is a version on, the ones it also runs on). Made for
    a console is what the store calls it optimized for; one it is only
    compatible with (a One game on Series) runs it by backward compatibility,
    which makes no version (owner, 2026-10-08: a One-only game on a Series is
    One). A product naming no optimized generation goes by its compatible
    ones, as before; one naming none at all is a PC (Windows) game."""
    props = product.get("Properties") or {}
    compatible = [
        _CONSOLES[g] for g in props.get("XboxConsoleGenCompatible") or [] if g in _CONSOLES
    ]
    optimized = [_CONSOLES[g] for g in props.get("XboxConsoleGenOptimized") or [] if g in _CONSOLES]
    consoles = [c for c in compatible if c in optimized] or optimized or compatible
    also_on = [c for c in compatible if c not in consoles]
    if props.get("XboxXPA") or _sku_flag(product, "XboxXPA"):
        also_on.append("pc")
    if not consoles:
        return ["pc"], []
    return consoles, also_on


def parse_product(product: dict) -> list[StoreVersion]:
    """One version per console the product is made for (`consoles_of`)."""
    props = product.get("Properties") or {}
    local = (product.get("LocalizedProperties") or [{}])[0]
    market = (product.get("MarketProperties") or [{}])[0]
    big_id = str(product.get("ProductId") or "")
    consoles, also_on = consoles_of(product)
    title_ids = [
        str(alt.get("Value"))
        for alt in product.get("AlternateIds") or []
        if alt.get("IdType") == "XboxTitleId" and alt.get("Value")
    ]
    common = {
        "name": _text(local.get("ProductTitle")),
        "kind": _kind(product),
        "developer": _text(local.get("DeveloperName")),
        "publisher": _text(local.get("PublisherName")),
        "release_date": _day(market.get("OriginalReleaseDate")),
        "genres": [str(c) for c in props.get("Categories") or [] if c]
        or ([str(props["Category"])] if props.get("Category") else []),
        # Two signs, kept apart: a cross-gen set is one game, a product
        # group can be a series (FF7 Remake and Rebirth share one).
        "store_group": _text(props.get("ProductGroupId")),
        "cross_gen_set": _text(props.get("XboxCrossGenSetId")),
        "description_en": _text(local.get("ShortDescription"))
        or _text(local.get("ProductDescription")),
        "media": _media(local),
        # Its editions, for now: what they bundle is read next (`bundled`).
        "dlc_ids": [
            str(r["RelatedProductId"])
            for r in market.get("RelatedProducts") or []
            if r.get("RelatedProductId") and r.get("RelationshipType") in ("Bundle", "AddOn")
        ],
    }
    on_sale = sold(product)
    return [
        StoreVersion(
            store="xbox",
            product_id=big_id,
            console=console,
            also_on=list(also_on),
            on_sale=on_sale,
            store_ids=[("xbox_product", big_id)] + [("xbox_title", t) for t in title_ids],
            **common,  # type: ignore[arg-type]
        )
        for console in consoles
    ]


def sold(product: dict) -> bool:
    """Whether the store still sells the product: some availability offers to
    buy it (a product off sale keeps only Browse, License, Redeem…)."""
    return any(
        "Purchase" in (availability.get("Actions") or [])
        for sku in product.get("DisplaySkuAvailabilities") or []
        for availability in sku.get("Availabilities") or []
    )


def bundle_items(product: dict) -> list[tuple[str, bool]]:
    """What a bundle product holds, `(bigId, is_primary)`; empty for a product
    that is not a bundle. A bundle is an edition (a pack), never a version."""
    found: dict[str, bool] = {}
    for availability in product.get("DisplaySkuAvailabilities") or []:
        sku_props = (availability.get("Sku") or {}).get("Properties") or {}
        for item in sku_props.get("BundledSkus") or []:
            big_id = str(item.get("BigId") or "")
            if big_id:
                found[big_id] = found.get(big_id, False) or bool(item.get("IsPrimary"))
    own = str(product.get("ProductId") or "")
    found.pop(own, None)
    return list(found.items())


def title_of(product: dict) -> str | None:
    return _text(((product.get("LocalizedProperties") or [{}])[0]).get("ProductTitle"))


def bundled(products: list[dict], game_id: str) -> list[str]:
    """What these editions bundle besides the game itself: its add-ons."""
    found: list[str] = []
    for product in products:
        for availability in product.get("DisplaySkuAvailabilities") or []:
            sku_props = (availability.get("Sku") or {}).get("Properties") or {}
            for item in sku_props.get("BundledSkus") or []:
                big_id = str(item.get("BigId") or "")
                if (
                    big_id
                    and big_id != game_id
                    and not item.get("IsPrimary")
                    and big_id not in found
                ):
                    found.append(big_id)
    return found


def addon_parents(product: dict) -> list[str]:
    """The games an add-on names as its own (`addOnParent`): a cross-gen game
    may be named by each of its products."""
    market = (product.get("MarketProperties") or [{}])[0]
    return [
        str(r["RelatedProductId"])
        for r in market.get("RelatedProducts") or []
        if r.get("RelationshipType") == "addOnParent" and r.get("RelatedProductId")
    ]


def belongs_to(addon: dict, owners: set[str]) -> bool:
    """Whether an add-on is one of these products' (a game's products): it
    names one of them as its parent. An edition of several games bundles
    the others' add-ons too ("Life is Strange: True Colors" outfits in the
    Remastered Collection's bundle), and one naming no parent is nobody's."""
    return any(parent in owners for parent in addon_parents(addon))


def _sku_flag(product: dict, name: str) -> bool:
    return any(
        ((availability.get("Sku") or {}).get("Properties") or {}).get(name)
        for availability in product.get("DisplaySkuAvailabilities") or []
    )


def parse_addon(product: dict) -> StoreDlc | None:
    """An add-on of a game, or None for what is not one: a game bundle, a
    consumable (currency, packs), a product with no name."""
    if str(product.get("ProductType") or "") != "Durable":
        return None
    local = (product.get("LocalizedProperties") or [{}])[0]
    market = (product.get("MarketProperties") or [{}])[0]
    name = _text(local.get("ProductTitle"))
    if not name:
        return None
    lowered = name.lower()
    kind = (
        "season_pass"
        if "season pass" in lowered or "expansion pass" in lowered
        else "soundtrack"
        if "soundtrack" in lowered
        else "dlc"
    )
    images = _media(local)
    return StoreDlc(
        store_id=str(product.get("ProductId") or ""),
        name=name,
        kind=kind,
        release_date=_day(market.get("OriginalReleaseDate")),
        description_en=_text(local.get("ShortDescription"))
        or _text(local.get("ProductDescription")),
        image_url=str(images.get("cover")) if images.get("cover") else None,
    )


def _kind(product: dict) -> str:
    props = product.get("Properties") or {}
    if props.get("IsDemo"):
        return "demo"
    product_type = str(product.get("ProductType") or "")
    if product_type == "Durable":
        return "dlc"
    if product_type == "Application":
        return "app"
    return "game"


_IMAGE_ROLES = {"BoxArt": "cover", "Poster": "poster", "SuperHeroArt": "background"}


def _media(local: dict) -> dict[str, object]:
    media: dict[str, object] = {}
    shots: list[str] = []
    for image in local.get("Images") or []:
        uri = str(image.get("Uri") or "")
        if not uri:
            continue
        url = "https:" + uri if uri.startswith("//") else uri
        purpose = image.get("ImagePurpose")
        if purpose == "Screenshot":
            shots.append(url)
        elif (role := _IMAGE_ROLES.get(str(purpose))) and role not in media:
            media[role] = url
    if shots:
        media["screenshots"] = shots
    if videos := _videos(local):
        media["videos"] = videos
    return media


def _videos(local: dict) -> list[dict[str, object]]:
    """The trailers a browser can play: `CMSVideos`' HLS and DASH streams,
    over https, with their preview picture. The old `Videos` are Smooth
    Streaming manifests over plain http (`….ism/manifest`) that nothing plays
    — kept only were one ever https. Links only: nothing is downloaded."""
    found: list[dict[str, object]] = []
    for video in local.get("CMSVideos") or []:
        hls, dash = _https(video.get("HLS")), _https(video.get("DASH"))
        if not (hls or dash):
            continue
        item: dict[str, object] = {"name": video.get("Caption"), "url": hls or dash}
        if hls:
            item["hls"] = hls
        if dash:
            item["dash"] = dash
        if poster := _https((video.get("PreviewImage") or {}).get("Uri")):
            item["poster"] = poster
        found.append(item)
    if not found:
        found = [
            {"name": v.get("Caption"), "url": url}
            for v in local.get("Videos") or []
            if (url := _https(v.get("Uri")))
        ]
    return found


def _https(raw: object) -> str | None:
    url = str(raw or "")
    if url.startswith("//"):
        url = "https:" + url
    return url if url.startswith("https://") else None


def _day(raw: object) -> str | None:
    text = str(raw or "")
    # The catalog's "unknown" is year 1 or 1753, as titlehub's; 9998 is a
    # product no longer (or not yet) on sale.
    if not re.match(r"\d{4}-\d{2}-\d{2}", text) or text[:4] in ("0001", "1753") or text >= "9000":
        return None
    return text[:10]


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return re.sub(r"\s+", " ", value).strip() or None
