"""A PlayStation game as the store describes it: a concept (the game, every
edition and console) with its CUSA (PS4) and PPSA (PS5) title ids. The
requests are `services/psn/client.py`'s (psnawp, paced there); this module
only reads the answers.

Our id for a PSN game is its trophy list (`NPWR…`), which the store never
names: a concept is found by searching the store for the game's name and is
accepted only when Sony's trophy API says one of its title ids has that very
list (`client.trophy_lists_of`). A version is one console of a concept: its
PS4 ids are one version, its PS5 ids another, even when they share a list."""

from __future__ import annotations

import re

from bot.services.stores import StoreVersion

_TITLE_ID = re.compile(r"\b((?:CUSA|PPSA)\d{5}_\d{2})\b")
_CONSOLE = {"CUSA": "ps4", "PPSA": "ps5"}
_IMAGE_ROLES = {
    "GAMEHUB_COVER_ART": "cover",
    "MASTER": "cover",
    "BACKGROUND": "background",
    "PORTRAIT_BANNER": "poster",
}


def title_ids_in_search(results: list[dict]) -> list[str]:
    """The CUSA/PPSA ids the search's concepts name through their default
    products ("UP4497-PPSA03972_00-00000000000GOTY7")."""
    found: list[str] = []
    for item in results:
        product = ((item.get("result") or {}).get("defaultProduct")) or {}
        for match in _TITLE_ID.findall(str(product.get("id") or "")):
            if match not in found:
                found.append(match)
    return found


def concept_title_ids(concept: dict) -> list[str]:
    return [str(t) for t in concept.get("titleIds") or [] if _TITLE_ID.fullmatch(str(t))]


def parse_concept(concept: dict) -> list[StoreVersion]:
    concept_id = str(concept.get("id") or "")
    by_console: dict[str, list[str]] = {}
    for title_id in concept_title_ids(concept):
        by_console.setdefault(_CONSOLE[title_id[:4]], []).append(title_id)
    descriptions = {str(d.get("type")): d.get("desc") for d in concept.get("descriptions") or []}
    genres = [str(g.get("value")) for g in concept.get("localizedGenres") or [] if g.get("value")]
    addons = [
        str(product_id)
        for group in concept.get("categorizedProducts") or []
        if group.get("topCategory") == "ADD_ON"
        for product_id in group.get("ids") or []
        if "VIRTUAL" not in str(product_id).upper()
    ]
    return [
        StoreVersion(
            store="psn",
            product_id=concept_id,
            console=console,
            name=_text(concept.get("nameEn") or concept.get("name")),
            kind="game"
            if str(concept.get("type") or "GAME") == "GAME"
            else str(concept["type"]).lower(),
            publisher=_text(concept.get("publisherName")),
            release_date=_day((concept.get("releaseDate") or {}).get("date")),
            genres=genres,
            store_group=concept_id,
            description_en=_text(descriptions.get("SHORT") or descriptions.get("LONG")),
            media=_media(concept),
            store_ids=[("psn_concept", concept_id)] + [("psn_title", t) for t in title_ids],
            dlc_ids=addons,
        )
        for console, title_ids in sorted(by_console.items())
    ]


def _media(concept: dict) -> dict[str, object]:
    media: dict[str, object] = {}
    raw = concept.get("media") or {}
    shots: list[str] = []
    for image in raw.get("images") or []:
        url = image.get("url")
        if not url:
            continue
        if image.get("type") == "SCREENSHOT" or image.get("role") == "SCREENSHOT":
            shots.append(str(url))
        elif (
            role := _IMAGE_ROLES.get(str(image.get("role") or image.get("type")))
        ) and role not in media:
            media[role] = str(url)
    if shots:
        media["screenshots"] = shots
    videos = [{"url": v.get("url")} for v in raw.get("videos") or [] if v.get("url")]
    if videos:
        media["videos"] = videos
    rating = concept.get("starRating") or {}
    if rating.get("score"):
        media["store_rating"] = rating["score"]
    return media


def _day(raw: object) -> str | None:
    text = str(raw or "")
    return text[:10] if re.match(r"\d{4}-\d{2}-\d{2}", text) else None


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return re.sub(r"\s+", " ", value).strip() or None
