"""A HowLongToBeat entry's whole page (#147): the game or additional content
itself (every field the page gives, in the columns of `hltb_entries`), its
platform rows (`platformData`), the groups of platforms with one set of hours
(`individuality`), the scores of HLTB's users (`userReviews`) and the entries
it names (`relationships`: DLC, mods, another game). Read from the page's
`__NEXT_DATA__`; the raw answer is kept in `source_payloads`, so everything
here can be read again from it, no request."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import httpx

from bot.services.hltb import _NEXT_DATA_RE, _PAGE_HEADERS, _PAGE_REQUEST_TIMEOUT
from bot.services.hltb_match import NOT_A_GAME
from bot.services.rate_limiter import RateLimiter

log = logging.getLogger(__name__)

PAGE_URL = "https://howlongtobeat.com/game/{hltb_id}"
LIMITER = RateLimiter(((1, 2.0), (60, 300.0)))


def _fields() -> tuple[tuple[str, str, str], ...]:
    """`(page field, column, kind)` for every field of an entry's own: i
    integer (seconds, counts), t text. Hours stay seconds, as HLTB gives them;
    the columns are named as HLTB names its fields where we had no name."""
    found: list[tuple[str, str, str]] = [
        ("game_name", "name", "t"),
        ("game_alias", "alias", "t"),
        ("game_type", "game_type", "t"),
        ("game_parent", "parent_hltb_id", "i"),
        ("game_image", "image", "t"),
        ("game_name_date", "name_year", "i"),
        ("profile_steam", "steam_appid", "i"),
        ("profile_steam_alt", "steam_alt", "i"),
        ("profile_itch", "itch_id", "i"),
        ("profile_ign", "ign_id", "t"),
        ("profile_dev", "developer", "t"),
        ("profile_pub", "publisher", "t"),
        ("profile_genre", "genres", "t"),
        ("profile_summary", "summary_en", "t"),
        ("release_world", "release_world", "t"),
        ("release_na", "release_na", "t"),
        ("release_eu", "release_eu", "t"),
        ("release_jp", "release_jp", "t"),
        ("rating_esrb", "rating_esrb", "t"),
        ("rating_pegi", "rating_pegi", "t"),
        ("rating_cero", "rating_cero", "t"),
        ("review_score", "review_score", "i"),
    ]
    for base in ("comp_main", "comp_plus", "comp_100", "comp_all"):
        found += [(base + s, base + s, "i") for s in ("", "_avg", "_med", "_h", "_l", "_count")]
    for base in ("comp_speed", "comp_speed100"):
        found += [(base + s, base + s, "i") for s in ("", "_avg", "_med", "_min", "_max", "_count")]
    for base in ("invested_co", "invested_mp"):
        found += [(base + s, base + s, "i") for s in ("", "_avg", "_med", "_h", "_l", "_count")]
    found += [
        (f"comp_lvl_{flag}", f"comp_lvl_{flag}", "i")
        for flag in ("sp", "co", "mp", "spd", "combine", "platform")
    ]
    found += [
        (f"count_{n}", f"count_{n}", "i")
        for n in (
            "comp",
            "total",
            "backlog",
            "playing",
            "replay",
            "retired",
            "custom",
            "review",
            "discussion",
        )
    ]
    found.append(("added_stats", "added_stats", "t"))
    return tuple(found)


ENTRY_FIELDS = _fields()
# HLTB writes 0 where it has nothing: for an id, a year, a score or an amount of
# time that is no value. A count stays what it says (0 completions is 0).
_ZERO_IS_NONE = frozenset(
    c for _, c, _kind in ENTRY_FIELDS if not c.startswith(("count_", "comp_lvl_")) and _kind == "i"
)
PLATFORM_FIELDS = ("comp_main", "comp_plus", "comp_100", "comp_low", "comp_high")
PLATFORM_COUNTS = ("count_comp", "count_total")
GROUP_FIELDS = ("comp_main", "comp_plus", "comp_100", "comp_all", "count_comp")
# What a relation's row says of the entry it names (not that entry's own page).
RELATION_COLUMNS = (
    "name",
    "game_type",
    "comp_main",
    "comp_plus",
    "comp_100",
    "comp_all",
    "comp_all_count",
    "count_backlog",
    "review_score",
)


@dataclass(slots=True)
class HltbEntry:
    hltb_id: int
    name: str
    game_type: str | None = None
    parent_hltb_id: int | None = None
    steam_appid: int | None = None
    # Its other Steam app (a game's re-release under another id).
    steam_alt: int | None = None
    developer: str | None = None
    publisher: str | None = None
    release_year: int | None = None
    summary_en: str | None = None
    image_url: str | None = None
    # Every column of the entry's own fields (an entry read from its own
    # page; a relation's row holds only `RELATION_COLUMNS`).
    row: dict[str, object] = field(default_factory=dict)
    # The page's platform rows (`hltb_platform_times`), groups of platforms
    # (`hltb_platform_groups`), the platforms it is on, the scores of HLTB's
    # users (score bucket → votes).
    platform_rows: list[dict[str, object]] = field(default_factory=list)
    groups: list[dict[str, object]] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    reviews: dict[int, int] = field(default_factory=dict)
    # The entries it names: its additional content (DLC, expansions, mods)
    # and the others (another game, a compilation), each as its page's row
    # of it says.
    children: list[HltbEntry] = field(default_factory=list)
    others: list[HltbEntry] = field(default_factory=list)
    # On a DLC's page, the game it belongs to (`relationships` lists it beside
    # the DLC's siblings): its parent, never one of its children.
    parent: HltbEntry | None = None


async def fetch_page(hltb_id: int) -> dict | None:
    """The page's `game.data` (game, relationships, platformData, …), or None
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
    row = {column: _value(game.get(page), column, kind) for page, column, kind in ENTRY_FIELDS}
    reviews = data.get("userReviews") or {}
    row["review_count"] = _int(reviews.get("review_count"))
    entry = HltbEntry(
        hltb_id=int(game.get("game_id")),
        name=str(game.get("game_name") or ""),
        game_type=row["game_type"],  # type: ignore[arg-type]
        parent_hltb_id=row["parent_hltb_id"],  # type: ignore[arg-type]
        steam_appid=row["steam_appid"],  # type: ignore[arg-type]
        steam_alt=row["steam_alt"],  # type: ignore[arg-type]
        developer=row["developer"],  # type: ignore[arg-type]
        publisher=row["publisher"],  # type: ignore[arg-type]
        release_year=_year(row["release_world"]) or _int(row["name_year"]),
        summary_en=" ".join(str(row["summary_en"] or "").split()) or None,
        image_url=_image(row["image"]),
        row=row,
        platforms=[
            p.strip() for p in str(game.get("profile_platform") or "").split(",") if p.strip()
        ],
        platform_rows=[
            {
                "platform": str(item["platform"]),
                **{c: _time(item.get(c)) for c in PLATFORM_FIELDS},
                **{c: _count(item.get(c)) for c in PLATFORM_COUNTS},
            }
            for item in data.get("platformData") or []
            if item.get("platform")
        ],
        groups=[
            {
                "platforms": str(item["platform"]),
                **{
                    c: _time(item.get(c)) if c != "count_comp" else _count(item.get(c))
                    for c in GROUP_FIELDS
                },
                "compare": _real(item.get("compare")),
            }
            for item in data.get("individuality") or []
            if item.get("platform")
        ],
        reviews={
            int(score): int(votes)
            for score, votes in reviews.items()
            if score.isdigit() and _int(votes)
        },
    )
    related = [
        _related(child, entry.hltb_id)
        for child in data.get("relationships") or []
        if child.get("game_id")
    ]
    # A DLC's page lists its own game among its relations (2026-10-12: 17
    # games stood as their DLC's "child", Cyberpunk 2077 under Phantom
    # Liberty): the one its `game_parent` names is the parent.
    for item in related:
        if entry.parent_hltb_id and item.hltb_id == entry.parent_hltb_id:
            item.parent_hltb_id = None
            entry.parent = item
    named = [item for item in related if item is not entry.parent]
    entry.children = [item for item in named if (item.game_type or "") in NOT_A_GAME]
    entry.others = [item for item in named if (item.game_type or "") not in NOT_A_GAME]
    return entry


def _related(child: dict, page_id: int) -> HltbEntry:
    """A relation as its page row gives it: name, type, average times, the
    number who backlog it, its score. Only additional content (a DLC, an
    expansion, a mod) is the page's child; any other entry it names is only
    named."""
    kind = _text(child.get("game_type"))
    item = HltbEntry(
        hltb_id=int(child["game_id"]),
        name=str(child.get("game_name") or ""),
        game_type=kind,
        parent_hltb_id=page_id if (kind or "") in NOT_A_GAME else None,
    )
    item.row = {
        "name": item.name,
        "game_type": kind,
        "comp_main": _time(child.get("comp_main")),
        "comp_plus": _time(child.get("comp_plus")),
        "comp_100": _time(child.get("comp_100")),
        "comp_all": _time(child.get("comp_all")),
        "comp_all_count": _count(child.get("comp_all_count")),
        "count_backlog": _count(child.get("count_backlog")),
        "review_score": _int(child.get("review_score")),
    }
    return item


def hours(seconds: object) -> float | None:
    """HLTB's seconds as hours, to a tenth; None when it has none."""
    value = _int(seconds)
    return round(value / 3600, 1) if value and value > 0 else None


def _int(value: object) -> int | None:
    try:
        number = int(float(value or 0))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number or None


def _count(value: object) -> int | None:
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _time(value: object) -> int | None:
    number = _count(value)
    return number if number and number > 0 else None


def _real(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _value(raw: object, column: str, kind: str) -> object:
    if kind == "t":
        text = _text(raw)
        return None if text is None or text.startswith("0000") else text
    if column in _ZERO_IS_NONE:
        return _int(raw)
    return _count(raw)


def _year(value: object) -> int | None:
    text = str(value or "")
    return int(text[:4]) if text[:4].isdigit() and text[:4] != "0000" else None


def _image(name: object) -> str | None:
    return f"https://howlongtobeat.com/games/{name}" if isinstance(name, str) and name else None


def _text(value: object) -> str | None:
    return value.strip() or None if isinstance(value, str) else None
