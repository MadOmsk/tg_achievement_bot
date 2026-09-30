"""Steam's side of a game: which Steam app it is, and that app's patch notes
from its developer's own announcements.

Network only — nothing here touches the database (services/steam_extras.py
stores what these find). Steam's news API needs no key. A game that is not a
Steam game here (an Xbox or PlayStation title) is found through the Steam
appid its HowLongToBeat page lists, else Steam's store search by name, where
only a confident match is taken — no patches beat another game's patches.
Console exclusives have no Steam page, so they get none.
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from bot.services.hltb import steam_appid_of
from bot.services.hltb_match import ACCEPT_SCORE, CLEAR_MARGIN, core, normalize, similarity

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    )
}
_TIMEOUT = httpx.Timeout(10.0)
_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
_NEWS_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v0002/"

# Steam's own announcements; the same feed also carries other sites' articles.
_OFFICIAL_FEED = "steam_community_announcements"
PATCHES_SHOWN = 10
_NEWS_FETCHED = 30
TEXT_CHARS = 4000

# A title that is a patch: the word for it, or a version number. A bare
# "9.18" is not one — it is as likely a date.
_PATCH_TITLE = re.compile(
    r"\b(update|patch|hotfix|hot fix|changelog|release notes)\b"
    r"|\bv\d+\.\d+|\b\d+\.\d+\.\d+",
    re.IGNORECASE,
)
# Posts about a demo or a playtest are not the game's patches even when they
# say "update".
_NOT_A_PATCH = re.compile(r"\b(demo|playtest)\b", re.IGNORECASE)
# Store entries that are a game's extras, not the game.
_NOT_THE_GAME = re.compile(
    r"\b(soundtrack|dlc|pack|upgrade|bundle|demo|playtest|dedicated server|costume|"
    r"skin|set|edition upgrade)\b",
    re.IGNORECASE,
)
_SEARCH_NOISE = re.compile(r"[™©®℠:,]")

_BB_BLOCKS = re.compile(
    r"\[(img|previewyoutube|video|table|code|quote)[^\]]*\].*?\[/\1\]",
    re.DOTALL | re.IGNORECASE,
)
_CLAN_IMAGE = re.compile(r"\{STEAM_CLAN_IMAGE\}\S*")
_BB_LINK = re.compile(r"\[url=([^\]]*)\](.*?)\[/url\]", re.DOTALL | re.IGNORECASE)
_HALF_LINK = re.compile(r"\[[^\]]*$|\]\([^)]*$")
_BB_HEADING = re.compile(r"\[h[1-6]\](.*?)\[/h[1-6]\]", re.DOTALL | re.IGNORECASE)
_BB_BREAK = re.compile(r"\[/p\]|\[br\s*/?\]|\[hr\]\[/hr\]|\[/list\]", re.IGNORECASE)
_BB_ITEM = re.compile(r"\[\*\]")
# Not one followed by "(": that is a link already turned into `[label](url)`.
_BB_TAG = re.compile(r"\[/?[a-z0-9*]+(?:[ =][^\]]*)?\](?!\()", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Patch:
    gid: str
    title: str
    date: str  # ISO date, UTC
    text: str  # the whole post, cleaned, cut only when very long


def is_patch_title(title: str) -> bool:
    return bool(_PATCH_TITLE.search(title)) and not _NOT_A_PATCH.search(title)


def _link(match: re.Match[str]) -> str:
    """`[url=X]label[/url]` as `[label](X)` — the Mini App draws it as a link.
    Only web addresses; anything else keeps just its words."""
    url = match.group(1).strip()
    label = match.group(2).strip()
    if not url.lower().startswith(("http://", "https://")) or not label:
        return label
    return f"[{label}]({url})"


def plain_text(bbcode: str) -> str:
    """Steam's BBCode reduced to readable paragraphs: pictures, videos and
    tables go, links and headings keep their words, list items become dashes."""
    text = _BB_BLOCKS.sub("", bbcode)
    text = _CLAN_IMAGE.sub("", text)
    text = _BB_LINK.sub(_link, text)
    text = _BB_HEADING.sub(r"\n\1\n", text)
    text = _BB_BREAK.sub("\n", text)
    text = _BB_ITEM.sub("\n- ", text)
    text = _BB_TAG.sub("", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def shorten(text: str, limit: int = TEXT_CHARS) -> str:
    if len(text) <= limit:
        return text
    cut = _HALF_LINK.sub("", text[:limit])
    return cut.rsplit(" ", 1)[0].rstrip(",;:-") + "…" if " " in cut else cut + "…"


def pick_appid(items: list[dict], names: list[str]) -> int | None:
    """The store entry that is this game, or None when it is not clear.
    `type` says "app" for a game's extras too, so only the name can tell."""
    ours = [n for n in (normalize(name) for name in names) if n]
    ours += [n for n in (normalize(core(name)) for name in names) if n and n not in ours]
    scored: list[tuple[float, int]] = []
    for item in items:
        name = str(item.get("name") or "")
        if item.get("type") != "app" or _NOT_THE_GAME.search(name):
            continue
        theirs = normalize(name)
        score = max((similarity(o, theirs) for o in ours), default=0.0)
        scored.append((score, int(item["id"])))
    scored.sort(reverse=True)
    if not scored or scored[0][0] < ACCEPT_SCORE:
        return None
    if (
        len(scored) > 1
        and scored[1][0] >= ACCEPT_SCORE
        and scored[0][0] - scored[1][0] < CLEAR_MARGIN
    ):
        return None
    return scored[0][1]


def parse_patches(payload: dict) -> list[Patch]:
    patches = []
    for item in payload.get("appnews", {}).get("newsitems", []):
        title = str(item.get("title") or "").strip()
        # The developer's own "patchnotes" tag is the surest sign; a title that
        # reads like a patch covers the posts nobody tagged.
        tagged = "patchnotes" in (item.get("tags") or [])
        if item.get("feedname") != _OFFICIAL_FEED or not (tagged or is_patch_title(title)):
            continue
        published = datetime.fromtimestamp(int(item["date"]), UTC).date().isoformat()
        patches.append(
            Patch(
                gid=str(item["gid"]),
                title=title,
                date=published,
                text=shorten(plain_text(str(item.get("contents") or ""))),
            )
        )
    patches.sort(key=lambda p: p.date, reverse=True)
    return patches[:PATCHES_SHOWN]


async def _search_appid(client: httpx.AsyncClient, names: list[str]) -> int | None:
    for name in dict.fromkeys(n for n in names if n):
        term = " ".join(_SEARCH_NOISE.sub(" ", name).split())
        response = await client.get(_SEARCH_URL, params={"term": term, "cc": "us", "l": "en"})
        response.raise_for_status()
        appid = pick_appid(response.json().get("items", []), names)
        if appid is not None:
            return appid
    return None


async def find_appid(names: list[str], hltb_id: int | None) -> int | None:
    """The Steam app a non-Steam game is: the one its HowLongToBeat page lists
    (exact — Steam's search shows only its ten most popular hits, and a small
    game called "Haven" is lost among Sun Haven and Space Haven), else a
    careful name search. None when there is none, or Steam cannot be reached."""
    try:
        appid = await steam_appid_of(hltb_id) if hltb_id else None
        if appid is not None:
            return appid
        async with httpx.AsyncClient(
            headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True
        ) as client:
            return await _search_appid(client, names)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.info("steam appid lookup failed for %s: %r", names[:1], exc)
        return None


async def fetch_patches(appid: int) -> list[Patch] | None:
    """The app's latest patches, newest first; None when Steam cannot be reached
    (as opposed to an empty list: it answered, and there are none)."""
    try:
        async with httpx.AsyncClient(
            headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True
        ) as client:
            response = await client.get(
                _NEWS_URL,
                # Only the developer's own posts: on a busy day the default feed
                # is thirty articles from other sites and no patch at all.
                params={
                    "appid": appid,
                    "count": _NEWS_FETCHED,
                    "maxlength": 0,
                    "format": "json",
                    "feeds": _OFFICIAL_FEED,
                },
            )
            response.raise_for_status()
            return parse_patches(response.json())
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.info("steam news lookup failed for app %s: %r", appid, exc)
        return None
