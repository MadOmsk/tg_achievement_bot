"""Which HowLongToBeat entry is this game? (#131)

The game page shows HLTB's times and description without anybody picking a
search result, so the pick is made here, once per game, and stored on the
title. Platform names and HLTB's differ in ways a plain search does not
survive — trademark signs, "(Win)", "- Reloaded Edition", "Xbox One
Edition", roman numerals — so a game is searched under a few spellings and
every candidate is scored against every name the game has:

- names are compared normalized (accents, apostrophes, `&`, roman numerals)
  and also *cored* — edition and platform tails cut off — at a small
  discount, so an exact entry for "Shadow Complex Remastered" still beats
  "Shadow Complex";
- a differing number is a different game (Halo 2 is not Halo 3);
- a DLC or mod entry, or one on none of the game's platforms, loses a
  little; popularity only breaks near-ties (two games called "Prey");
- a Steam game is settled by the appid HLTB's own page lists
  (`profile_steam`), when it lists one: a match is certain, a different
  appid rules the candidate out whatever its name.

Nothing is accepted below `ACCEPT_SCORE`, or when a runner-up is too close
to call: showing another game's hours is worse than showing none.
"""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from bot.services.hltb import HltbError, HltbResult

log = logging.getLogger(__name__)

# Tuned on this community's library (1,700 games across the three platforms):
# above it a match was right every time it was checked by hand.
ACCEPT_SCORE = 0.86
# Below ACCEPT_SCORE a candidate still wins when nothing else comes near it.
WEAK_SCORE = 0.74
CLEAR_MARGIN = 0.12
# A score this high ends the search early — later spellings cannot beat it.
SURE_SCORE = 0.97
# Name matched only after cutting an edition/platform tail off either side.
CORE_DISCOUNT = 0.96
MAX_QUERIES = 3
# Steam pages checked for their appid, best candidates first.
MAX_PAGE_CHECKS = 3

_ROMAN = {
    "i": "1",
    "ii": "2",
    "iii": "3",
    "iv": "4",
    "v": "5",
    "vi": "6",
    "vii": "7",
    "viii": "8",
    "ix": "9",
    "x": "10",
    "xi": "11",
    "xii": "12",
    "xiii": "13",
    "xiv": "14",
    "xv": "15",
    "xvi": "16",
}
_APOSTROPHES = re.compile(r"[’‘`´'ʼ]")
_NON_WORD = re.compile(r"[^\w]+")
_MARKS = re.compile(r"[™®©℠]")

# A tail that names the release rather than the game. Cut repeatedly from the
# end, so "Game - Xbox One Edition (Game Preview)" loses all three.
_TAILS = [
    re.compile(r"\s*[\(\[][^\)\]]*[\)\]]\s*$"),
    re.compile(
        r"[\s:\-–—]*\b(?:for\s+)?(?:windows(?:\s*10|\s*11)?|win(?:10|dows)?|pc|xbox(?:\s+one"
        r"|\s+series(?:\s+x\s*[|/]?\s*s)?|\s+360)?|ps[345]|playstation\s*[345]?|steam)\s*$",
        re.IGNORECASE,
    ),
    # After a separator the last part goes, up to three words and the edition:
    # "- Reloaded Edition", ": Full Clip Edition", " - The Pristine Cut",
    # "- Windows 10 Edition" — but not "Batman: Arkham Asylum Game of the
    # Year Edition"'s. A colon glued to a word ("NieR:Automata") is not one.
    re.compile(
        r"\s*(?::\s|\s[-–—]\s)(?:\S+\s+){0,3}(?:edition|cut|bundle)\s*$",
        re.IGNORECASE,
    ),
    # Without one, a single word ("Dead Island Definitive Edition", "Forza
    # Horizon 4 Ultimate Edition") or Game of the Year — any more and the
    # game's own words go too. "Collection" is left alone: it is often the
    # name (The Master Chief Collection).
    re.compile(
        r"\s+(?:game\s+of\s+the\s+year|[^\W\d][\w'’.]*)\s+(?:edition|cut)\s*$", re.IGNORECASE
    ),
    re.compile(r"[\s:\-–—]+the\s+(?:video\s+)?game\s*$", re.IGNORECASE),
    re.compile(
        r"[\s:\-–—]*\b(?:remastered|remaster|hd|goty|game\s+preview|early\s+access"
        r"|game\s+of\s+the\s+year|anniversary|deluxe|enhanced|complete|trial|demo|beta)\s*$",
        re.IGNORECASE,
    ),
]
_SUBTITLE = re.compile(r"\s*(?::|\s[-–—]\s)\s*")

# How a platform (ours) is spelled in HLTB's profile_platforms.
_HLTB_PLATFORMS = {
    "XboxSeries": {"Xbox Series X/S"},
    "XboxOne": {"Xbox One"},
    "Xbox360": {"Xbox 360"},
    "PC": {"PC"},
    "PS5": {"PlayStation 5"},
    "PS4": {"PlayStation 4"},
    "PS3": {"PlayStation 3"},
    "PSVITA": {"PlayStation Vita"},
    "PSVita": {"PlayStation Vita"},
}
_FAMILY_PLATFORMS = {
    "xbox_modern": {"Xbox One", "Xbox Series X/S", "PC"},
    "xbox_360": {"Xbox 360"},
    "steam": {"PC"},
    "psn": {"PlayStation 3", "PlayStation 4", "PlayStation 5", "PlayStation Vita"},
}
# Only what HLTB marks as not a game of its own; other types are games.
_TYPE_FACTOR = {"dlc": 0.9, "expansion": 0.9, "mod": 0.8, "hack": 0.75}
_OFF_PLATFORM = 0.9
# Released after somebody here was already earning its achievements: most
# likely a remake of the game played. Not a veto — HLTB dates an early-access
# game by its full release (Baldur's Gate 3: played 2020, released 2023) —
# but enough to lose to an entry of the same name that was out in time.
_TOO_NEW = 0.04
# Names a platform gives a game it could not name.
_PLACEHOLDERS = {"", "?", "unknown", "unknown title"}


@dataclass(slots=True, frozen=True)
class GameIdentity:
    """What we know of a game: every name it goes by, most trusted first."""

    names: tuple[str, ...]
    platform: str  # xbox_modern / xbox_360 / steam / psn
    platforms: tuple[str, ...] = ()  # titles.platforms, our spelling
    steam_appid: int | None = None
    # The year of the earliest achievement anybody here earned in it: the
    # game was out by then. Our platforms give no release year of their own.
    first_played_year: int | None = None


@dataclass(slots=True, frozen=True)
class HltbMatch:
    hltb_id: int
    name: str
    score: float  # 1.0 = certain (a Steam appid agreed)


@dataclass(slots=True)
class _Scored:
    result: HltbResult
    score: float


SearchFn = Callable[[str], Awaitable[list[HltbResult]]]
# The appids an HLTB page lists for the game: None when the page could not be
# read, an empty set when it lists none.
SteamIdsFn = Callable[[HltbResult], Awaitable[set[int] | None]]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _MARKS.sub(" ", text.lower())
    text = _APOSTROPHES.sub("", text).replace("&", " and ")
    tokens = [_ROMAN.get(tok, tok) for tok in _NON_WORD.sub(" ", text).split()]
    if len(tokens) > 1 and tokens[0] == "the":
        tokens = tokens[1:]
    return " ".join(tokens)


def core(text: str) -> str:
    """The name with its edition and platform tails cut off."""
    text = _MARKS.sub("", text).strip()
    while True:
        for tail in _TAILS:
            cut = tail.sub("", text).strip()
            if cut and cut != text:
                text = cut
                break
        else:
            return text


def usable_name(name: str | None) -> bool:
    """Whether a name is worth searching HLTB (English only) for."""
    if not name or name.strip().lower() in _PLACEHOLDERS:
        return False
    letters = [ch for ch in name if ch.isalpha()]
    if not letters:
        return False
    latin = sum(1 for ch in letters if ch.isascii())
    return latin / len(letters) >= 0.7


def queries(identity: GameIdentity) -> list[str]:
    """Search spellings, best first, at most MAX_QUERIES. HLTB's search wants
    every word it is given, so a shorter spelling finds what a longer misses."""
    out: list[str] = []

    def add(text: str) -> None:
        text = " ".join(_NON_WORD.sub(" ", _MARKS.sub(" ", text)).split())
        if len(text) >= 2 and text.lower() not in (q.lower() for q in out):
            out.append(text)

    names = [n for n in identity.names if usable_name(n)]
    for name in names:
        add(core(name))
    for name in names:
        add(name)
    for name in names:
        head = _SUBTITLE.split(core(name), maxsplit=1)[0]
        if len(head) >= 4:
            add(head)
    return out[:MAX_QUERIES]


def _numbers(norm: str) -> set[str]:
    return {tok for tok in norm.split() if tok.isdigit()}


def similarity(ours: str, theirs: str) -> float:
    """0..1 for two normalized names; a differing number costs a lot."""
    if not ours or not theirs:
        return 0.0
    if ours == theirs:
        return 1.0
    seq = SequenceMatcher(None, ours, theirs).ratio()
    ta, tb = set(ours.split()), set(theirs.split())
    jaccard = len(ta & tb) / len(ta | tb)
    score = (seq + jaccard) / 2
    if _numbers(ours) != _numbers(theirs):
        score *= 0.6
    return score


def _their_names(result: HltbResult) -> list[str]:
    names = [result.name]
    if result.alias:
        # HLTB separates several aliases with commas.
        names.extend(part for part in result.alias.split(",") if part.strip())
    return names


def name_score(identity: GameIdentity, result: HltbResult) -> float:
    best = 0.0
    for ours in identity.names:
        if not usable_name(ours):
            continue
        ours_full, ours_core = normalize(ours), normalize(core(ours))
        for theirs in _their_names(result):
            theirs_full, theirs_core = normalize(theirs), normalize(core(theirs))
            best = max(
                best,
                similarity(ours_full, theirs_full),
                similarity(ours_core, theirs_full) * CORE_DISCOUNT,
                similarity(ours_full, theirs_core) * CORE_DISCOUNT,
                similarity(ours_core, theirs_core) * CORE_DISCOUNT,
            )
    return best


def _our_hltb_platforms(identity: GameIdentity) -> set[str]:
    found: set[str] = set()
    for name in identity.platforms:
        found |= _HLTB_PLATFORMS.get(name, set())
    return found or _FAMILY_PLATFORMS.get(identity.platform, set())


def score(identity: GameIdentity, result: HltbResult) -> float:
    value = name_score(identity, result)
    # An exact name is that entry whatever HLTB files it as (a Telltale
    # episode is a "dlc" there).
    if value < 1.0:
        value *= _TYPE_FACTOR.get((result.game_type or "").lower(), 1.0)
    ours = _our_hltb_platforms(identity)
    # HLTB's platform lists are incomplete for older entries: an empty one
    # says nothing, a list without any of ours says a little.
    if ours and result.platforms and not ours & set(result.platforms):
        value *= _OFF_PLATFORM
    year, played = result.release_year, identity.first_played_year
    if year and played:
        if year > played:
            value -= _TOO_NEW
        else:
            # Of two entries both out in time, the newer one is what people
            # were playing then (Doom 2016, not 1993): at most +0.02.
            value += 0.02 * max(0.0, 1 - (played - year) / 20)
    # A near-tie goes to the entry more people logged: at most +0.006.
    value += 0.0012 * min(5.0, math.log10((result.popularity or 0) + 1))
    return min(value, 1.0)


def rank(identity: GameIdentity, candidates: Sequence[HltbResult]) -> list[_Scored]:
    seen: dict[int, _Scored] = {}
    for result in candidates:
        if result.hltb_id not in seen:
            seen[result.hltb_id] = _Scored(result, score(identity, result))
    return sorted(seen.values(), key=lambda s: s.score, reverse=True)


def decide(ranked: Sequence[_Scored]) -> _Scored | None:
    """The winner by name alone, or None when it is not clear enough."""
    if not ranked:
        return None
    best = ranked[0]
    runner_up = ranked[1].score if len(ranked) > 1 else 0.0
    if best.score >= ACCEPT_SCORE and best.score - runner_up >= 0.005:
        return best
    if best.score >= ACCEPT_SCORE and best.score >= 0.999:
        # Two entries both named exactly this: popularity already split them.
        return best
    if best.score >= WEAK_SCORE and best.score - runner_up >= CLEAR_MARGIN:
        return best
    return None


async def find(
    identity: GameIdentity,
    search: SearchFn,
    steam_ids: SteamIdsFn | None = None,
) -> HltbMatch | None:
    """The HLTB entry for this game, or None when there is none to be sure of.

    Raises HltbError only when HLTB could not be asked at all — a game not
    found is None, and the caller records the two differently.
    """
    candidates: list[HltbResult] = []
    asked = answered = 0
    for query in queries(identity):
        asked += 1
        try:
            candidates.extend(await search(query))
            answered += 1
        except HltbError as exc:
            log.info("HLTB search for %r failed: %s", query, exc)
            continue
        ranked = rank(identity, candidates)
        if ranked and ranked[0].score >= SURE_SCORE and identity.steam_appid is None:
            break
    if asked and not answered:
        raise HltbError(f"HLTB could not be searched for {identity.names[0]!r}")

    ranked = rank(identity, candidates)
    if identity.steam_appid is not None and steam_ids is not None:
        ranked, confirmed = await _check_steam(identity.steam_appid, ranked, steam_ids)
        if confirmed is not None:
            return HltbMatch(confirmed.hltb_id, confirmed.name, 1.0)
    winner = decide(ranked)
    if winner is None:
        return None
    return HltbMatch(winner.result.hltb_id, winner.result.name, round(winner.score, 3))


async def _check_steam(
    appid: int, ranked: list[_Scored], steam_ids: SteamIdsFn
) -> tuple[list[_Scored], HltbResult | None]:
    """The candidate whose HLTB page lists this appid, if one of the best few
    does; otherwise the ranking without those whose page lists another."""
    ruled_out: set[int] = set()
    for scored in ranked[:MAX_PAGE_CHECKS]:
        if scored.score < 0.5:
            break
        ids = await steam_ids(scored.result)
        if ids is None:
            continue
        if appid in ids:
            return ranked, scored.result
        if ids:
            ruled_out.add(scored.result.hltb_id)
    return [s for s in ranked if s.result.hltb_id not in ruled_out], None
