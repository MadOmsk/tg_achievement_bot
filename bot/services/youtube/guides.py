"""Video guides for achievements, read from guide channels on YouTube (owner,
2026-10-06). No database access: what a video says, and how a name compares.

TrophyTom's videos (checked on his channel, 2026-10-06) say which achievement
they are about in three ways, each matched only by an exact name:

- a video for one achievement: "House Flipper Remastered - Beach please 🏆
  Trophy / Achievement Guide" — the name stands right before the 🏆;
- a chapter whose description's timeline marks it: "02:42 – ACHIEVEMENT –
  Chainsaw Go Brrrrrrrrr", "06:09 – TROPHY – I Am Heavy Weapons Guy – PART 1";
- a whole game in one video, the timeline its achievements' bare names:
  "00:07 – Bountilogical Studies PhD".

Every timeline line is kept; the collectibles and chapters among them match
no achievement's name and so never show.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bot.services.hltb_match import core, normalize

# The channels read, by YouTube channel id.
CHANNELS = {
    "UCFXmIUDNofRpYSG7lku0i_Q": "TrophyTom",
}

_SEPARATOR = re.compile(r"\s+[-–—]\s+")
_TROPHY_MARK = "🏆"
_TIMELINE = re.compile(r"^\s*(\d{1,2}(?::\d{2}){1,2})\s*[-–—]\s*(.+?)\s*$")
_KIND = re.compile(
    r"^(?:achievements?|trophy|trophies)(?:\s*/\s*(?:achievements?|trophy|trophies))?\s*[-–—:]\s*",
    re.IGNORECASE,
)
_PART = re.compile(r"\s*[-–—]\s*part\s*(\d+)\s*$", re.IGNORECASE)
_NOTE = re.compile(
    r"\s*(?:[-–—]\s*(?:un)?missable|\((?:un)?missable\)|\(optional\))\s*$", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class Mark:
    label: str
    start_seconds: int
    part: int = 0


def key_of(text: str) -> str:
    """A name compared with another: case, accents, punctuation and a leading
    "the" do not count (HLTB's matcher's rule)."""
    return normalize(text).replace("_", " ").strip()


def title_key(title: str) -> str:
    """A video's title in parts between " - ", each a key, joined by " | "."""
    parts = [key_of(part) for part in _SEPARATOR.split(title.replace(_TROPHY_MARK, " - "))]
    return " | ".join(part for part in parts if part)


def game_keys(*names: str | None) -> list[str]:
    """The keys a game's videos start with: each of its names, and each cut of
    its edition or platform tail ("- Windows 10", "Enhanced Edition")."""
    keys: list[str] = []
    for name in names:
        if not name:
            continue
        for variant in (name, core(name)):
            key = title_key(variant)
            if key and key not in keys:
                keys.append(key)
    return keys


def _seconds(stamp: str) -> int:
    total = 0
    for piece in stamp.split(":"):
        total = total * 60 + int(piece)
    return total


def _label(text: str) -> tuple[str, int]:
    text = _KIND.sub("", text.strip())
    part = 0
    found = _PART.search(text)
    if found:
        part = int(found.group(1))
        text = text[: found.start()]
    text = _NOTE.sub("", text)
    return key_of(text), part


def marks_of(title: str, description: str) -> list[Mark]:
    """Every moment the video names: its whole length for a one-achievement
    title, and each line of its description's timeline."""
    marks: dict[tuple[str, int], Mark] = {}
    if _TROPHY_MARK in title:
        head = title.split(_TROPHY_MARK, 1)[0]
        parts = _SEPARATOR.split(head.strip())
        if len(parts) > 1:
            label, part = _label(parts[-1])
            if label:
                marks[(label, 0)] = Mark(label, 0, part)
    for line in description.splitlines():
        found = _TIMELINE.match(line)
        if not found:
            continue
        label, part = _label(found.group(2))
        if not label:
            continue
        start = _seconds(found.group(1))
        marks.setdefault((label, start), Mark(label, start, part))
    return list(marks.values())


def video_url(video_id: str, start_seconds: int = 0) -> str:
    url = f"https://www.youtube.com/watch?v={video_id}"
    return f"{url}&t={start_seconds}s" if start_seconds else url
