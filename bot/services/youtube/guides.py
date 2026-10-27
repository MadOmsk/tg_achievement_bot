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

Other big guide channels (read 2026-10-12, PowerPyx, HarryNinetyFour,
Maka91Productions, 100% Guides, PS5Trophies) name an achievement in their
*titles*, with a guide phrase after it and no 🏆:

- "Mortal Shell 2 - Bag Holder Trophy / Achievement Guide" — the name stands
  before the phrase, in the part after the game;
- "The Blood of Dawnwalker - All Tower Locations (Bird's-Eye View Trophy
  Guide)" — in parentheses;
- "Silent Hill F — Go Away! - Trophy Guide" — the part before a bare phrase;
- "Mortal Shell 2 Heavy Metal Trophy Guide" — no separator at all: the game
  and the name are one run of words, told apart only by knowing the game
  (a *joined* mark: `= game name`), and "Control Resonant All Dog & Toy
  Locations (Dog's Best Friend Trophy Guide)" a *loose* one (`~name`, the
  game is the words it starts with).

Each is still matched only by an exact name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bot.services.hltb_match import core, normalize

# The channels read, by YouTube channel id (the biggest that guide achievements
# by name, owner, 2026-10-12; sizes then): TrophyTom first, as it always was.
CHANNELS = {
    "UCFXmIUDNofRpYSG7lku0i_Q": "TrophyTom",  # 197k
    "UCWBA1-H9A5IldSb3tNwQmtQ": "PowerPyx",  # 1.24M
    "UCX2tHrgdOPDtQRidMS946Fw": "PS5Trophies",  # 1.11M
    "UCRL1kBjkg-F5KY7vZUZgTeA": "HarryNinetyFour",  # 809k
    "UCZojkqUeuaZyAQc8KaBNrJw": "Maka91Productions",  # 465k
    "UCRvx1nQZ-YXvxc6IOB8mKPg": "100% Guides",  # 230k
    "UCjXhYVGTDHsx2LWKIvtjSEA": "Carrot Helper",  # 113k, whole-game 100% walkthroughs
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

# What a title carries that is not a name: *1000G IN 1.5 HOURS*, #Xbox, [4K].
_DECOR = re.compile(r"\*[^*]*\*|#\w+|\[[^\]]*\]")
_WORD = r"(?:trophy|trophies|achievements?)"
# "Trophy Guide", "Trophy / Achievement Guide", "Trophy Guide / Achievement
# Guide", "Achievement/Trophy Guide", "Trophy Guide & Roadmap".
_GUIDE = (
    rf"{_WORD}(?:\s*[/&]\s*{_WORD})?\s+guide"
    rf"(?:\s*[/&]\s*{_WORD}(?:\s+guide)?)?(?:\s*&\s*roadmap)?"
)
_GUIDE_END = re.compile(rf"^(?P<name>.*?)[\s\-–—:|]*{_GUIDE}[\s.!)]*$", re.IGNORECASE)
# Inside parentheses a bare "Guide" is enough: "(Freeze Frame Guide)".
_BARE_GUIDE_END = re.compile(r"^(?P<name>.*?)[\s\-–—:|]*\bguide[\s.!)]*$", re.IGNORECASE)
_PAREN = re.compile(r"\(([^()]*)\)\s*$")

# Marks that are not a plain name: the whole title without its phrase, to be
# told from "game name" by the game (joined), and a name whose game is the
# words the title starts with (loose).
JOINED = "= "
LOOSE = "~"


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


def _guided(part: str) -> tuple[str, bool] | None:
    """What stands before a guide phrase that ends `part`, and whether it was
    in parentheses; "" for a bare phrase; None when `part` has no phrase."""
    found = _PAREN.search(part)
    if found:
        inner = found.group(1).strip()
        match = _GUIDE_END.match(inner) or _BARE_GUIDE_END.match(inner)
        if match:
            return match.group("name").strip(), True
    match = _GUIDE_END.match(part.strip())
    return (match.group("name").strip(), False) if match else None


def title_mark(title: str) -> Mark | None:
    """The one achievement a title names, as a mark at the video's start; None
    for a whole-game video and for titles that name nothing."""
    if _TROPHY_MARK in title:
        head = title.split(_TROPHY_MARK, 1)[0]
        parts = _SEPARATOR.split(head.strip())
        if len(parts) > 1:
            label, part = _label(parts[-1])
            if label:
                return Mark(label, 0, part)
        return None
    parts = [p.strip() for p in _SEPARATOR.split(_DECOR.sub(" ", title)) if p.strip()]
    if not parts:
        return None
    guided = _guided(parts[-1])
    if guided is None:
        return None
    name, in_paren = guided
    if not name:
        # "Game - Silent Hill F — Go Away! - Trophy Guide": the part before it.
        if len(parts) < 3:
            return None
        name, in_paren = parts[-2], False
    label, part = _label(name)
    if not label:
        return None
    if len(parts) > 1:
        return Mark(label, 0, part)
    # No separator: the game and the name are not told apart by the title alone.
    if in_paren:
        return Mark(LOOSE + label, 0, part)
    return Mark(JOINED + label, 0, part)


def marks_of(title: str, description: str) -> list[Mark]:
    """Every moment the video names: its whole length for a one-achievement
    title, and each line of its description's timeline."""
    marks: dict[tuple[str, int], Mark] = {}
    named = title_mark(title)
    if named is not None:
        marks[(named.label, 0)] = named
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
