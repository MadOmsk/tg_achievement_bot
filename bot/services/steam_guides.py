"""How to get one achievement, from the Steam community's own guides.

What is read from Steam's community site is kept under data/steam_guides/
for a week (it refuses bursts, and a re-read would otherwise start again); the
tips worked out from it are stored with each achievement (services/
steam_extras.py, title_achievements.tip_*).
Steam's guide search (the same Web API key the bot already holds) names a
game's most popular "achievement" guides; each is read as plain lines. Which
lines are which achievement's tip is for a model to say
(services/translate/guide_tips.py): guides are laid out differently by everyone
and rules guessing it broke on each new one.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx

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
_COOLDOWN_MAX_SECONDS = 900.0
_DISK_DIR = Path("data") / "steam_guides"
_DISK_SECONDS = 7 * 86400

# A very long tip (a table of every artifact) is cut at a line, not mid-line.
_BODY_CHARS = 8000
# What is left once the description's own words are taken out must still be a
# sentence's worth, or it is only a section label ("Skulls & Terminals").
_MIN_TIP_CHARS = 40
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
# An address alone on its line — a picture, a video, a bare link.
_MEDIA_LINE = re.compile(r"^(?:\[[^\]]*\]\()?https?://\S+\)?$")
# Cached pages from before links and videos were kept are read again.
_DISK_FORMAT = 9
# A guide's own pictures (its screenshots) carry this class; icons and
# emoticons do not. A picture is often wrapped in a link to its page on Steam,
# and the picture is what is wanted, not the link.
_IMAGE_TAG = re.compile(r"<img [^>]*>", re.IGNORECASE)
_LINKED_IMAGE = re.compile(r"<a [^>]*>\s*(<img [^>]*>)\s*</a>", re.IGNORECASE)
_SRC = re.compile(r'src="(https?://[^"]+)"', re.IGNORECASE)
# A table row is one line, its cells joined by this mark (U+00A6); the Mini App
# draws consecutive such lines as a table.
CELL = " ¦ "
_CELL_END = re.compile(r"</t[dh]>", re.IGNORECASE)
# Steam's own guide tables are divs, a row of cells each.
_DIV_CELL = re.compile(r'<div class="bb_table_t[dh]"[^>]*>(.*?)</div>', re.DOTALL)
_CELL_PICTURE = re.compile(r"<a [^>]*>\s*<img [^>]*>\s*</a>|<img [^>]*>", re.IGNORECASE)
# A column of small pictures says nothing in text; its heading goes with it.
_PICTURE_HEADING = re.compile(r"^(?:icon|image|picture|иконка|картинка)\s*¦\s*", re.IGNORECASE)
# Steam names the site after a link, "[mapgenie.io]"; the link's words are its name.
_LINK_HOST = re.compile(r'<span class="bb_link_host">.*?</span>', re.DOTALL | re.IGNORECASE)
_LIST_ITEM = re.compile(r"<li[^>]*>\s*", re.IGNORECASE)
_BREAK = re.compile(r"<br\s*/?>|</div>|</li>|</p>|</h\d>|</tr>", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Guide:
    file_id: str
    title: str
    lines: tuple[str, ...]


_locks: dict[int, asyncio.Lock] = {}
# The last few guides read, with when their text was fetched: the same week-long
# life as the copy on disk, and a bound, so a process that runs for months neither
# keeps a stale guide nor every guide it ever read.
_MEMORY_GUIDES = 32
_guide_memory: OrderedDict[str, tuple[float, Guide | None]] = OrderedDict()
_cooldown_until = 0.0
_refusals = 0
_community = asyncio.Lock()


def _unwrapped(url: str) -> str:
    """Steam sends outside links through its own filter page; the address it
    guards is what the reader should get."""
    if urlsplit(url).path.rstrip("/") != "/linkfilter":
        return url
    target = parse_qs(urlsplit(url).query).get("u", [""])[0]
    target = html.unescape(target)
    return target if target.startswith(("http://", "https://")) else url


def _anchor(match: re.Match[str]) -> str:
    url = _unwrapped(html.unescape(match.group(1)).strip())
    label = re.sub(r"<[^>]+>", "", match.group(2)).strip()
    if not label:
        return ""
    if html.unescape(label) == url:
        return url
    return f"[{label}]({url})"


def _repaired(text: str) -> str:
    """Some guides reach Steam with their apostrophes already destroyed
    ("you���ve"). Between two letters it was an apostrophe; anywhere
    else it is nothing worth showing."""
    text = re.sub(r"(?<=\w)�+(?=\w)", "’", text)
    return text.replace("�", "")


def _cell(match: re.Match[str]) -> str:
    """A table cell as its text and the joining mark; a cell of only a picture
    is nothing, so it cannot tear its row apart."""
    text = _CELL_PICTURE.sub("", match.group(1))
    return text + CELL if text.strip() else ""


def _image(match: re.Match[str]) -> str:
    tag = match.group(0)
    src = _SRC.search(tag)
    if "sharedFilePreviewImage" not in tag or src is None:
        return ""
    return f"\n{html.unescape(src.group(1))}\n"


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
    body = _DIV_CELL.sub(_cell, body)
    body = _LINKED_IMAGE.sub(r"\1", body)
    body = _IMAGE_TAG.sub(_image, body)
    body = _LINK_HOST.sub("", body)
    body = _ANCHOR.sub(_anchor, body)
    body = _LIST_ITEM.sub("\n- ", body)
    body = _CELL_END.sub(CELL, body)
    body = _BREAK.sub("\n", body)
    text = html.unescape(re.sub(r"<[^>]+>", "", body)).replace("\xa0", " ")
    text = _repaired(text)
    cleaned = (re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n"))
    # A row ends after its last cell, not with the mark; a row of empty cells is nothing.
    rows = (_PICTURE_HEADING.sub("", re.sub(r"(\s*¦)+$", "", line).strip()) for line in cleaned)
    return [row for row in rows if row and row != "¦"]


def make_guide(file_id: str, title: str, lines: list[str]) -> Guide:
    return Guide(file_id, title, tuple(lines))


def tip_from_lines(guide: Guide, ranges: list[tuple[int, int]]) -> str | None:
    """The guide's lines in `ranges` (0-based, inclusive) as one tip: what a model
    pointed at, copied as it is and cut at a line when very long."""
    body: list[str] = []
    size = 0
    for first, last in ranges:
        for line in guide.lines[first : last + 1]:
            if size + len(line) > _BODY_CHARS:
                break
            body.append(line)
            size += len(line)
    text = "\n".join(body).strip()
    return text if has_prose(text) else None


def has_prose(text: str) -> bool:
    """Whether a tip says anything in words. Pictures, videos and bare links
    alone are no advice — a screenshot of the achievement's own tile is not one."""
    words = "\n".join(line for line in text.split("\n") if not _MEDIA_LINE.match(line.strip()))
    return len(words.strip()) >= _MIN_TIP_CHARS


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
    kept = _guide_memory.get(file_id)
    if kept is not None:
        fetched_at, guide = kept
        if time.time() - fetched_at <= _DISK_SECONDS:
            _guide_memory.move_to_end(file_id)
            return True, guide
        del _guide_memory[file_id]
    path = _DISK_DIR / f"{file_id}.json"
    try:
        fetched_at = path.stat().st_mtime
        if time.time() - fetched_at > _DISK_SECONDS:
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
    _keep(file_id, guide, fetched_at)
    return True, guide


def _keep(file_id: str, guide: Guide | None, fetched_at: float) -> None:
    _guide_memory[file_id] = (fetched_at, guide)
    _guide_memory.move_to_end(file_id)
    while len(_guide_memory) > _MEMORY_GUIDES:
        _guide_memory.popitem(last=False)


def _remember(file_id: str, guide: Guide | None) -> None:
    """Keep what was read, unusable guides included (so they are not read
    again), beside the other downloaded pictures and texts under data/."""
    _keep(file_id, guide, time.time())
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


StopWhen = Callable[[Guide], Awaitable[bool]]


async def guides_of(appid: int, api_key: str, stop_when: StopWhen | None = None) -> GuideSet:
    """A game's most popular achievement guides, most popular first. One read
    per app at a time: a published achievement and a visit to the page may
    both ask, and the second waits for the first. Pages already read come
    from the disk cache, so a second read costs no request to the site.
    `stop_when` is asked about each guide as it is read, and the first one it
    accepts ends the reading: the rest are never fetched."""
    async with _locks.setdefault(appid, asyncio.Lock()):
        return await _fetch_guides(appid, api_key, stop_when)


async def _fetch_guides(appid: int, api_key: str, stop_when: StopWhen | None) -> GuideSet:
    global _cooldown_until, _refusals
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
                        continue
                    try:
                        async with _community:
                            known, guide = _recall(file_id)
                            if not known:
                                guide = await _read_guide(
                                    client, file_id, str(f.get("title") or "")
                                )
                                _remember(file_id, guide)
                                _refusals = 0
                                await asyncio.sleep(_GUIDE_GAP_SECONDS)
                    except _RateLimited:
                        # Each refusal in a row doubles the pause: a block that does
                        # not lift is not helped by asking every minute and a half.
                        _cooldown_until = time.monotonic() + min(
                            _COOLDOWN_SECONDS * 2**_refusals, _COOLDOWN_MAX_SECONDS
                        )
                        _refusals += 1
                        log.info("steam guides for %s: rate limited, %s read", appid, len(guides))
                        complete = False
                        continue
                    except _Transient:
                        complete = False
                        continue
                if guide is not None:
                    guides.append(guide)
                    if stop_when is not None and await stop_when(guide):
                        # What was wanted is found: the guides left are not read, and
                        # nothing is left to come back for.
                        return GuideSet(guides, True)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        # The key rides in this request's URL: log the class, never the message.
        log.info("steam guides lookup failed for %s: %s", appid, type(exc).__name__)
        return GuideSet([], False)
    return GuideSet(guides, complete)
