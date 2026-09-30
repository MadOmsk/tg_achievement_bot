"""How to get one achievement, from the Steam community's own guides.

What is read from Steam's community site is kept under data/steam_guides/
for a week (it refuses bursts, and a re-read would otherwise start again); the
tips worked out from it are stored with each achievement (services/
steam_extras.py, title_achievements.tip_*).
Steam's guide search (the same Web API key the bot already holds) names a
game's most popular "achievement" guides; each is read as plain lines, and the
lines that follow an achievement's name — up to the next achievement's name —
are its tip. A guide made of screenshots, or of bare lists of names, gives
nothing and is passed over.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from bot.services.hltb_match import normalize

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    ),
    # Without these two the community site answers 429 whatever the pace.
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
_TIMEOUT = httpx.Timeout(15.0)
_QUERY_URL = "https://api.steampowered.com/IPublishedFileService/QueryFiles/v1/"
_GUIDE_URL = "https://steamcommunity.com/sharedfiles/filedetails/"
# EPublishedFileInfoMatchingFileType: all guides. Sorted by popularity.
_GUIDES_FILETYPE = 10
_QUERY_TRENDING = 3
GUIDES_READ = 7
_GUIDE_GAP_SECONDS = 2.5
_COOLDOWN_SECONDS = 90.0
_DISK_DIR = Path("data") / "steam_guides"
_DISK_SECONDS = 7 * 86400

_BODY_LINES = 40
_BODY_CHARS = 3000
_MIN_BODY_CHARS = 20
# What is left once the description's own words are taken out must still be a
# sentence's worth, or it is only a section label ("Skulls & Terminals").
_MIN_TIP_CHARS = 40
_HEADING_CHARS = 12
_LABEL_CHARS = 40
# A line ending so is part of the advice, not a heading; ":" opens a list.
_SENTENCE_END = (".", "!", "?", "…", ")", '"', "'", "»", ":")
_SEPARATOR = re.compile(r"\s+[-–—|]\s+|:\s+")
_BULLET = re.compile(r"^[\s\-–—•*·▪►>]*(?:\d{1,3}[.)]\s+)?")
_PAGE_END = ("commentthread_area", "rightContents", "responsive_page_frame_footer")
_TITLE_RE = re.compile(r'<div class="workshopItemTitle">(.*?)</div>', re.DOTALL)
# Han, kana and hangul.
_IDEOGRAPHS = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
_IDEOGRAPH_SHARE = 0.05
# Links keep their address, an embedded player becomes its YouTube link — the
# Mini App draws both (a link, a video card).
_ANCHOR = re.compile(r'<a [^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE)
_PLAYER = re.compile(
    r'<div class="sharedFilePreviewYouTubeVideo[^"]*" id="([A-Za-z0-9_-]{11})"[^>]*>',
    re.IGNORECASE,
)
_LINK_OR_BULLET = re.compile(r"^(\[.*\]\(https?://|https?://|[-–—•*·▪►>]|\d{1,3}[.)] )")
# Cached pages from before links and videos were kept are read again.
_DISK_FORMAT = 2
_BREAK = re.compile(r"<br\s*/?>|</div>|</li>|</p>|</h\d>|</tr>", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Guide:
    file_id: str
    title: str
    lines: tuple[str, ...]
    # Each line's possible achievement name, normalized once.
    heads: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Tip:
    text: str
    guide_id: str


@dataclass(frozen=True, slots=True)
class Wanted:
    """One achievement a tip is looked for: its names and its own descriptions
    (a guide that only repeats the description says nothing)."""

    names: tuple[str, ...]
    descriptions: tuple[str, ...] = ()


_locks: dict[int, asyncio.Lock] = {}
_guide_memory: dict[str, Guide | None] = {}
_cooldown_until = 0.0
_community = asyncio.Lock()


def _anchor(match: re.Match[str]) -> str:
    url = html.unescape(match.group(1)).strip()
    label = re.sub(r"<[^>]+>", "", match.group(2)).strip()
    if not label or html.unescape(label) == url:
        return url
    return f"[{label}]({url})"


def guide_lines(page: str) -> list[str]:
    """A guide page's text as readable lines: pictures, scripts and markup
    gone, every block ending a line."""
    start = page.find('<div class="guide subSections">')
    if start < 0:
        return []
    body = page[start:]
    ends = [i for i in (body.find(marker) for marker in _PAGE_END) if i > 0]
    if ends:
        body = body[: min(ends)]
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", body, flags=re.DOTALL)
    body = _PLAYER.sub(lambda m: f"\nhttps://www.youtube.com/watch?v={m.group(1)}\n", body)
    body = _ANCHOR.sub(_anchor, body)
    body = _BREAK.sub("\n", body)
    text = html.unescape(re.sub(r"<[^>]+>", "", body)).replace("\xa0", " ")
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n"))
    return [line for line in lines if line]


def _head_and_rest(line: str) -> tuple[str, str]:
    """A line split into what may be an achievement's name and what follows it
    on the same line ("Name: how to get it")."""
    line = _BULLET.sub("", line, count=1)
    parts = _SEPARATOR.split(line, maxsplit=1)
    return (parts[0], parts[1]) if len(parts) == 2 else (line, "")


def make_guide(file_id: str, title: str, lines: list[str]) -> Guide:
    return Guide(
        file_id, title, tuple(lines), tuple(normalize(_head_and_rest(line)[0]) for line in lines)
    )


def _is_label(line: str) -> bool:
    """A short line that ends no sentence, and is no link or list item: a
    heading, not advice."""
    return (
        len(line) <= _LABEL_CHARS
        and not line.endswith(_SENTENCE_END)
        and not _LINK_OR_BULLET.match(line)
    )


def _repeats(line: str, descriptions: tuple[str, ...]) -> bool:
    """The line only says what the achievement's own description says."""
    said = normalize(line)
    for description in descriptions:
        own = normalize(description)
        if own and own in said and len(said) - len(own) < _MIN_BODY_CHARS:
            return True
    return False


def tip_in(guide: Guide, wanted: Wanted, everything: set[str]) -> str | None:
    """The lines a guide gives under one achievement's name, or None.
    `everything` holds every achievement's normalized name in the game."""
    targets = {normalize(n) for n in wanted.names if n}
    is_header = [head in everything for head in guide.heads]
    for index, head in enumerate(guide.heads):
        if head not in targets:
            continue
        body: list[str] = []
        size = 0
        rest = _head_and_rest(guide.lines[index])[1]
        if rest:
            body.append(rest)
            size += len(rest)
        for i in range(index + 1, min(index + 1 + _BODY_LINES, len(guide.lines))):
            line = guide.lines[i]
            if is_header[i] or size + len(line) > _BODY_CHARS:
                break
            # A heading once the advice has begun is the next section
            # ("Benefits", "Collectibles"), not more of this one.
            if size >= _MIN_TIP_CHARS and _is_label(line):
                break
            body.append(line)
            size += len(line)
        # A guide that copies the description tells nothing the row does not.
        body = [line for line in body if not _repeats(line, wanted.descriptions)]
        # Table headings ("Ending Achievements", "Description", "How to unlock")
        # trail a section: short, and no sentence's end. The tip itself stays.
        while len(body) > 1 and _is_label(body[-1]):
            body.pop()
        if body and len(body[-1]) <= _HEADING_CHARS:
            body.pop()
        text = "\n".join(body).strip()
        if len(text) >= _MIN_TIP_CHARS:
            return text
    return None


def everything_named(catalog: list[Wanted]) -> set[str]:
    return {normalize(n) for wanted in catalog for n in wanted.names if n}


def tip_for(guides: list[Guide], wanted: Wanted, everything: set[str]) -> Tip | None:
    """The first guide's tip for this achievement."""
    for guide in guides:
        text = tip_in(guide, wanted, everything)
        if text:
            return Tip(text, guide.file_id)
    return None


def _mostly_ideographs(title: str, lines: list[str]) -> bool:
    """A guide written in Chinese, Japanese or Korean: its achievement names
    are not ours, and nobody here reads it."""
    text = title + "".join(lines)
    return len(_IDEOGRAPHS.findall(text)) > len(text) * _IDEOGRAPH_SHARE


class _RateLimited(Exception):
    """Steam's community site asked us to slow down."""


class _Transient(Exception):
    """A guide could not be read this time (network); worth asking again."""


@dataclass(frozen=True, slots=True)
class GuideSet:
    guides: list[Guide]
    # False when some guide could not be read yet (Steam asked us to slow down):
    # the tips are what the others gave, and a later look may find more.
    complete: bool


def _recall(file_id: str) -> tuple[bool, Guide | None]:
    """A guide read before — in memory, or on disk from an earlier run — and
    whether it was usable. `known` is False when it has never been read."""
    if file_id in _guide_memory:
        return True, _guide_memory[file_id]
    path = _DISK_DIR / f"{file_id}.json"
    try:
        if time.time() - path.stat().st_mtime > _DISK_SECONDS:
            return False, None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, None
    if data.get("format") != _DISK_FORMAT:
        return False, None
    guide = (
        make_guide(file_id, str(data.get("title", "")), data["lines"])
        if data.get("lines") and data.get("format") == _DISK_FORMAT
        else None
    )
    _guide_memory[file_id] = guide
    return True, guide


def _remember(file_id: str, guide: Guide | None) -> None:
    """Keep what was read, unusable guides included (so they are not read
    again), beside the other downloaded pictures and texts under data/."""
    _guide_memory[file_id] = guide
    payload = (
        {"format": _DISK_FORMAT, "title": guide.title, "lines": list(guide.lines)}
        if guide
        else {"format": _DISK_FORMAT}
    )
    try:
        _DISK_DIR.mkdir(parents=True, exist_ok=True)
        (_DISK_DIR / f"{file_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as exc:
        log.info("steam guide %s could not be kept on disk: %r", file_id, exc)


async def _read_guide(client: httpx.AsyncClient, file_id: str, title: str) -> Guide | None:
    try:
        response = await client.get(_GUIDE_URL, params={"id": file_id})
    except httpx.HTTPError as exc:
        log.info("steam guide %s could not be read: %r", file_id, exc)
        raise _Transient from exc
    if response.status_code == 429:
        raise _RateLimited
    if response.status_code != 200:
        return None
    lines = guide_lines(response.text)
    if not title:
        found = _TITLE_RE.search(response.text)
        title = html.unescape(found.group(1)).strip() if found else ""
    if len(lines) < 10 or _mostly_ideographs(title, lines):
        return None
    return make_guide(file_id, title, lines)


async def guides_of(appid: int, api_key: str) -> GuideSet:
    """A game's most popular achievement guides, most popular first. One read
    per app at a time: a published achievement and a visit to the page may
    both ask, and the second waits for the first. Pages already read come
    from the disk cache, so a second read costs no request to the site."""
    async with _locks.setdefault(appid, asyncio.Lock()):
        return await _fetch_guides(appid, api_key)


async def _fetch_guides(appid: int, api_key: str) -> GuideSet:
    global _cooldown_until
    try:
        async with httpx.AsyncClient(
            headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True
        ) as client:
            response = await client.get(
                _QUERY_URL,
                params={
                    "key": api_key,
                    "appid": appid,
                    "query_type": _QUERY_TRENDING,
                    "filetype": _GUIDES_FILETYPE,
                    "search_text": "achievement",
                    "numperpage": GUIDES_READ,
                    "format": "json",
                },
            )
            response.raise_for_status()
            files = response.json().get("response", {}).get("publishedfiledetails", [])
            guides: list[Guide] = []
            complete = True
            for f in files:
                file_id = str(f.get("publishedfileid") or "")
                if not file_id:
                    continue
                known, guide = _recall(file_id)
                if not known:
                    # The community site answers a burst with 429, and one bot
                    # serves every game: reads go one at a time, paced, and a
                    # refusal pauses them all for a while. What was read stays
                    # kept, so the next look picks up where this one stopped.
                    if time.monotonic() < _cooldown_until:
                        complete = False
                        break
                    try:
                        async with _community:
                            known, guide = _recall(file_id)
                            if not known:
                                guide = await _read_guide(
                                    client, file_id, str(f.get("title") or "")
                                )
                                _remember(file_id, guide)
                                await asyncio.sleep(_GUIDE_GAP_SECONDS)
                    except _RateLimited:
                        _cooldown_until = time.monotonic() + _COOLDOWN_SECONDS
                        log.info("steam guides for %s: rate limited, %s read", appid, len(guides))
                        complete = False
                        break
                    except _Transient:
                        complete = False
                        continue
                if guide is not None:
                    guides.append(guide)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        # The key rides in this request's URL: log the class, never the message.
        log.info("steam guides lookup failed for %s: %s", appid, type(exc).__name__)
        return GuideSet([], False)
    return GuideSet(guides, complete)
