"""A HowLongToBeat entry's whole page (#147): the game, its DLC and expansions
with their own times (`relationships`), and the times per platform
(`platformData`). Read from the page's `__NEXT_DATA__`, as `services/hltb.py`
reads the description; `/hltb`'s own search and `hltb_cache` are untouched."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import httpx

from bot.services.hltb import _NEXT_DATA_RE, _PAGE_HEADERS, _PAGE_REQUEST_TIMEOUT, _extras_of
from bot.services.rate_limiter import RateLimiter

log = logging.getLogger(__name__)

PAGE_URL = "https://howlongtobeat.com/game/{hltb_id}"
LIMITER = RateLimiter(((1, 2.0), (60, 300.0)))


@dataclass(slots=True)
class HltbEntry:
    hltb_id: int
    name: str
    game_type: str | None = None
    parent_hltb_id: int | None = None
    steam_appid: int | None = None
    developer: str | None = None
    publisher: str | None = None
    release_year: int | None = None
    platforms: list[str] = field(default_factory=list)
    times: dict[str, object] = field(default_factory=dict)
    platform_times: dict[str, dict[str, object]] = field(default_factory=dict)
    details: dict[str, object] = field(default_factory=dict)
    summary_en: str | None = None
    image_url: str | None = None
    # The entry's DLC and expansions as its page lists them (no page of their own read).
    children: list[HltbEntry] = field(default_factory=list)


async def fetch_page(hltb_id: int) -> dict | None:
    """The page's `game.data` (game, relationships, platformData), or None
    when HLTB has no such page; raises on a network failure."""
    await LIMITER.acquire()
    async with httpx.AsyncClient(timeout=_PAGE_REQUEST_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(PAGE_URL.format(hltb_id=hltb_id), headers=_PAGE_HEADERS)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    match = _NEXT_DATA_RE.search(response.text)
    if not match:
        return None
    data = json.loads(match.group(1))
    return ((data.get("props") or {}).get("pageProps") or {}).get("game", {}).get("data")


def parse_page(data: dict) -> HltbEntry | None:
    games = data.get("game") or []
    if not games:
        return None
    game = games[0]
    extras = _extras_of(game)
    entry = HltbEntry(
        hltb_id=int(game.get("game_id")),
        name=str(game.get("game_name") or ""),
        game_type=_text(game.get("game_type")),
        parent_hltb_id=_int(game.get("game_parent")),
        steam_appid=_int(game.get("profile_steam")),
        developer=extras.pop("developer", None),
        publisher=extras.pop("publisher", None),
        release_year=_year(game.get("release_world")) or _int(game.get("game_name_date")),
        platforms=[
            p.strip() for p in str(game.get("profile_platform") or "").split(",") if p.strip()
        ],
        times=extras.pop("times", {}),
        platform_times={
            str(row.get("platform")): {
                key: value
                for key, value in (
                    ("main", _hours(row.get("comp_main"))),
                    ("extra", _hours(row.get("comp_plus"))),
                    ("complete", _hours(row.get("comp_100"))),
                    ("fastest", _hours(row.get("comp_low"))),
                    ("slowest", _hours(row.get("comp_high"))),
                    ("count", _int(row.get("count_comp"))),
                )
                if value
            }
            for row in data.get("platformData") or []
            if row.get("platform")
        },
        details=extras,
        summary_en=" ".join(str(game.get("profile_summary") or "").split()) or None,
        image_url=_image(game.get("game_image")),
    )
    entry.children = [
        HltbEntry(
            hltb_id=int(child["game_id"]),
            name=str(child.get("game_name") or ""),
            game_type=_text(child.get("game_type")),
            parent_hltb_id=entry.hltb_id,
            times={
                key: {"average": hours}
                for key, raw in (
                    ("main", child.get("comp_main")),
                    ("extra", child.get("comp_plus")),
                    ("completionist", child.get("comp_100")),
                    ("all", child.get("comp_all")),
                )
                if (hours := _hours(raw))
            },
        )
        for child in data.get("relationships") or []
        if child.get("game_id")
    ]
    return entry


def _hours(seconds: object) -> float | None:
    value = _int(seconds)
    return round(value / 3600, 1) if value and value > 0 else None


def _int(value: object) -> int | None:
    try:
        number = int(value or 0)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None
    return number or None


def _year(value: object) -> int | None:
    text = str(value or "")
    return int(text[:4]) if text[:4].isdigit() and text[:4] != "0000" else None


def _image(name: object) -> str | None:
    return f"https://howlongtobeat.com/games/{name}" if isinstance(name, str) and name else None


def _text(value: object) -> str | None:
    return value.strip() or None if isinstance(value, str) else None
