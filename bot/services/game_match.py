"""Which versions are one game (#147) — a weighted model, no database access.

Every pair of versions shows signs (`features`): one achievement list, one
store group or two, one HLTB entry, how alike the cut names are, a sequel's
number, how many achievements' names they share, the studio, the years, a
demo of the game. Each adds its weight (`WEIGHTS`) to the log-odds that the
two are one game; the logistic function makes that a probability. Linked at
`LINK_P`, the operator's to decide from `REVIEW_P`, apart below. **Nothing is
certain** (owner, 2026-10-10): even a shared achievement list is only a very
large weight, and the weights are to be fitted to the operator's decisions.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from bot.services.hltb_match import core, normalize, similarity

# A name tail that says which release of the game this is.
_REMASTER = re.compile(
    r"\b(remaster(?:ed)?|definitive|anniversary|redux|hd|enhanced|director'?s cut)\b",
    re.IGNORECASE,
)
_EDITION = re.compile(
    r"\b(game of the year|goty|complete|deluxe|ultimate|gold|premium|legendary|collector'?s)\b",
    re.IGNORECASE,
)
_DEMO = re.compile(r"\b(demo|trial|prologue|beta)\b", re.IGNORECASE)

NAME_FLOOR = 0.8  # below this, two versions are not compared further
CONTAINED_NAME = 0.85
FAR_YEARS = 5
NEAR_YEARS = 1
ACHIEVEMENTS_MIN = 5  # a list shorter than this says nothing
ACHIEVEMENTS_SAME = 0.6
# Partly one list: the same game made again with some of its achievements —
# a remaster (Gears of War → Ultimate Edition shares 43%).
ACHIEVEMENTS_REMASTER = 0.3
ACHIEVEMENTS_OTHER = 0.15


@dataclass(slots=True)
class Candidate:
    version_id: int
    store: str
    product_id: str
    console: str
    names: tuple[str, ...]
    kind: str | None = None
    developer: str | None = None
    publisher: str | None = None
    year: int | None = None
    store_group: str | None = None
    hltb_ids: frozenset[int] = frozenset()
    achievements: frozenset[str] = frozenset()
    # Its achievement list (`titles`): Smart Delivery's One and Series, and a
    # Play Anywhere PC, are one list — and so one game.
    list_key: tuple[str, str] | None = None
    stand_in: bool = False

    @property
    def cores(self) -> tuple[str, ...]:
        """The cut names without the words that name a release, not the
        game ("Gears of War: Reloaded" is Gears of War)."""
        return tuple(dict.fromkeys(_unmarked(game_core(n)) for n in self.names if n))

    @property
    def fulls(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(normalize(n) for n in self.names if n))


@dataclass(slots=True)
class Verdict:
    state: str  # linked / review / apart
    score: float
    reasons: list[str] = field(default_factory=list)
    # A review's guess at how the later version belongs, when its own list says
    # more than its name: a list of its own is a remaster, not an edition.
    kind: str | None = None


def kind_of(candidate: Candidate) -> str:
    """How a version belongs to its game, from the store's own kind first and
    the name second."""
    if (candidate.kind or "") == "demo" or any(_DEMO.search(n) for n in candidate.names):
        return "demo"
    if any(_REMASTER.search(n) for n in candidate.names):
        return "remaster"
    if any(_EDITION.search(n) for n in candidate.names):
        return "edition"
    return "version"


# What each sign adds to the log-odds that two versions are one game (#147;
# owner, 2026-10-10: every rule is a weight, nothing is certain). The sum goes
# through the logistic function; the weights are meant to be fitted to the
# operator's own decisions once there are enough of them.
WEIGHTS: dict[str, float] = {
    "bias": -3.0,
    "one_list": 12.0,  # the same achievement list (Smart Delivery, Play Anywhere)
    "same_group": 5.0,  # one store filed them under one game of its own
    "groups_differ": -2.0,  # one store filed them under two
    "same_hltb": 5.0,  # one HLTB entry
    "steam_parent": 5.0,  # Steam names one the other's game
    "name": 10.0,  # × (name similarity − 0.8)
    "full_name": 4.4,  # the very same full name, released within a few years
    "franchise": 2.0,  # one name ends the other ("Call of Duty: Modern Warfare 2")
    "subtitle": -1.5,  # one name opens the other, which goes on: mostly another game
    "numbers_differ": -9.0,  # Halo and Halo 2
    "achievements_same": 7.0,  # ≥ 60% of the achievements' names shared
    "achievements_partly": 3.5,  # 30–60%: the game made again
    "achievements_other": -1.5,  # ≤ 15%: two lists of their own
    "developer": 0.7,
    "publisher": 0.3,
    "years_near": 3.5,  # released within a year
    "years_between": -0.5,  # × each year past the first, under five
    "years_far": 0.0,  # five or more: a port, a remaster or a remake — undecided
    "year_unknown": 0.0,  # nothing either way
    "demo_of": 7.0,  # a demo the game's name opens, released within a year
}
LINK_P = 0.85  # at or above: one game
REVIEW_P = 0.15  # at or above (below LINK_P): the operator decides


def features(a: Candidate, b: Candidate) -> dict[str, float]:
    """The signs one pair of versions shows, each 0..1 (or a count of years)."""
    f: dict[str, float] = {"bias": 1.0}
    if a.list_key and a.list_key == b.list_key:
        f["one_list"] = 1.0
    if a.store_group and a.store == b.store and a.store_group == b.store_group:
        f["same_group"] = 1.0
    elif _groups_differ(a, b):
        f["groups_differ"] = 1.0
    if a.hltb_ids & b.hltb_ids:
        f["same_hltb"] = 1.0
    if a.store == b.store == "steam" and (
        a.store_group == b.product_id or b.store_group == a.product_id
    ):
        f["steam_parent"] = 1.0

    name = max((similarity(x, y) for x in a.cores for y in b.cores), default=0.0)
    if any(x == y for x in a.fulls for y in b.fulls):
        name = 1.0
    elif name < CONTAINED_NAME and _contained(a, b):
        name = CONTAINED_NAME
        f["franchise"] = 1.0
    f["name"] = name - NAME_FLOOR

    if "franchise" not in f and name < 1.0 and _subtitled(a, b):
        # "Mass Effect" → "Mass Effect: Andromeda": unless the achievements
        # say otherwise (Gears of War: Reloaded), another game.
        f["subtitle"] = 1.0
    demo = _demo_pair(a, b)
    if demo:
        f["demo_of"] = 1.0
        f.pop("subtitle", None)
    elif name < 1.0 and _numbers(a) != _numbers(b):
        # A demo's own numbers ("1-Shot") are not a sequel's.
        f["numbers_differ"] = 1.0

    overlap = _overlap(a.achievements, b.achievements)
    if overlap is not None:
        if overlap >= ACHIEVEMENTS_SAME:
            f["achievements_same"] = 1.0
        elif overlap >= ACHIEVEMENTS_REMASTER:
            f["achievements_partly"] = 1.0
        elif overlap <= ACHIEVEMENTS_OTHER:
            f["achievements_other"] = 1.0
    if _same(a.developer, b.developer):
        f["developer"] = 1.0
    if _same(a.publisher, b.publisher):
        f["publisher"] = 1.0
    if a.year and b.year:
        gap = abs(a.year - b.year)
        if gap <= NEAR_YEARS:
            f["years_near"] = 1.0
        elif gap < FAR_YEARS:
            f["years_between"] = float(gap - NEAR_YEARS)
        else:
            f["years_far"] = 1.0
        if gap < FAR_YEARS and any(x == y for x in a.fulls for y in b.fulls):
            # The very same name a few years apart: a store's own date is not
            # always the release (Microsoft's "Remastered" is dated 2026).
            f["full_name"] = 1.0
    else:
        f["year_unknown"] = 1.0
    return f


def probability(f: dict[str, float], weights: dict[str, float] | None = None) -> float:
    w = weights or WEIGHTS
    logit = sum(w.get(k, 0.0) * v for k, v in f.items())
    return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, logit))))


def compare(a: Candidate, b: Candidate) -> Verdict:
    """How likely two versions are one game, and what that makes them."""
    f = features(a, b)
    p = probability(f)
    reasons = [f"p {p:.2f}"] + [
        f"{k} {WEIGHTS.get(k, 0.0) * v:+.1f}" for k, v in f.items() if k != "bias"
    ]
    # How the later one belongs when its list says more than its name: a list
    # partly shared, or one of its own years later, is the game made again.
    own_list = "achievements_partly" in f or ("achievements_other" in f and "years_near" not in f)
    kind = "remaster" if own_list and "demo_of" not in f else None
    if p >= LINK_P:
        return Verdict("linked", p, reasons, kind=kind)
    if p >= REVIEW_P:
        return Verdict("review", p, reasons, kind=kind)
    return Verdict("apart", p, reasons)


def _demo_pair(a: Candidate, b: Candidate) -> bool:
    """A demo whose game's name opens it, released within a year of it, and
    not filed by one store under another game of its own."""
    for demo, game in ((a, b), (b, a)):
        if (
            kind_of(demo) == "demo"
            and kind_of(game) != "demo"
            and not _groups_differ(demo, game)
            and _starts(game, demo)
            and demo.year
            and game.year
            and abs(demo.year - game.year) <= NEAR_YEARS
        ):
            return True
    return False


_STOP = {"the", "of", "and", "for", "game", "edition", "a", "an", "to", "in", "on"}


def block_key(candidate: Candidate) -> set[str]:
    """Words a version shares with any version it could be: the telling words
    of its cut names. Only versions sharing one are compared."""
    return {w for c in candidate.cores for w in c.split() if len(w) >= 3 and w not in _STOP}


def _words(name: str) -> list[str]:
    return name.split()


def _contained(a: Candidate, b: Candidate) -> bool:
    """One cut name ends the other, whole, two words at least: a franchise
    said before it ("Call of Duty: Modern Warfare 2"). Not one that starts the
    other — a subtitle after it is another game ("Gears of War: Judgment")."""
    for x in a.cores:
        for y in b.cores:
            short, long_ = sorted((_words(x), _words(y)), key=len)
            if 2 <= len(short) < len(long_) and long_[-len(short) :] == short:
                return True
    return False


def _groups_differ(a: Candidate, b: Candidate) -> bool:
    """One store filed them under different games of its own (Xbox's
    product groups): "Gears of War: E-Day Multiplayer Beta" is E-Day's."""
    return bool(
        a.store == b.store and a.store_group and b.store_group and a.store_group != b.store_group
    )


def _subtitled(a: Candidate, b: Candidate) -> bool:
    """One cut name opens the other, which goes on with a subtitle."""
    for x in a.cores:
        for y in b.cores:
            short, long_ = sorted((_words(x), _words(y)), key=len)
            if 2 <= len(short) < len(long_) and long_[: len(short)] == short:
                return True
    return False


def _starts(game: Candidate, demo: Candidate) -> bool:
    """The game's cut name opens the demo's, and what follows is not a number
    — unless the game has one of its own ("RESIDENT EVIL 2 1-Shot Demo"). Its
    release words kept: "Gears of War: Reloaded" does not open "Gears of War:
    E-Day Multiplayer Beta"."""
    for g in dict.fromkeys(game_core(n) for n in game.names if n):
        head = _words(g)
        if not head:
            continue
        numbered = any(w.isdigit() for w in head)
        for d in (normalize(n) for n in demo.names):
            words = _words(d)
            if words[: len(head)] != head:
                continue
            rest = words[len(head) :]
            if rest and rest[0].isdigit() and not numbered:
                continue
            return True
    return False


# When a version came out, for ordering only: its year, else its console's era
# (a 360 game is older than anything on One).
CONSOLE_ERA = {"360": 2008, "ps3": 2008, "vita": 2012, "one": 2015, "ps4": 2015}


def era(m: Candidate) -> int:
    return m.year or CONSOLE_ERA.get(m.console, 0)


def game_name(members: list[Candidate]) -> str:
    """A game is named by its plainest version: not an edition, a remaster or
    a demo where there is one, the earliest, by its cut name."""
    plain = [m for m in members if kind_of(m) == "version"] or members
    plain.sort(key=lambda m: (era(m) or 9999, len(m.names[0] if m.names else "")))
    first = plain[0]
    return core(first.names[0]) if first.names else first.product_id


# Words that name a release of a game, not the game: dropped before names are
# compared ("Gears of War: Reloaded", "… Ultimate Edition" are Gears of War).
_RELEASE_WORDS = {
    "remastered",
    "remaster",
    "definitive",
    "anniversary",
    "redux",
    "hd",
    "enhanced",
    "ultimate",
    "goty",
    "complete",
    "deluxe",
    "gold",
    "premium",
    "legendary",
}


# Platforms a store puts in a product's name ("Resident Evil Village PS4 & PS5").
_PLATFORM_WORDS = {
    "ps4",
    "ps5",
    "ps3",
    "and",
    "xbox",
    "one",
    "series",
    "x",
    "s",
    "pc",
    "windows",
    "10",
}


# Words an edition or a platform tail is made of: the only words a cut may
# take. "Mass Effect: Andromeda Deluxe Edition" keeps "Andromeda" (owner,
# 2026-10-10: after a separator, the phrase with "edition" is the edition;
# a word that is not an edition's own is the game's).
_EDITION_TAIL_WORDS = {
    "edition",
    "cut",
    "bundle",
    "deluxe",
    "ultimate",
    "gold",
    "premium",
    "legendary",
    "complete",
    "definitive",
    "special",
    "standard",
    "digital",
    "collectors",
    "collector",
    "directors",
    "director",
    "anniversary",
    "enhanced",
    "remastered",
    "remaster",
    "hd",
    "game",
    "of",
    "the",
    "year",
    "goty",
    "and",
    "for",
    "windows",
    "10",
    "11",
    "pc",
    "xbox",
    "one",
    "series",
    "x",
    "s",
    "ps3",
    "ps4",
    "ps5",
    "playstation",
    "steam",
    "preview",
    "early",
    "access",
    "trial",
    "demo",
    "beta",
    "upgrade",
    "pack",
}


_PARENTHESIS = re.compile(r"(\s*[\(\[][^\)\]]*[\)\]])+\s*$")


def game_core(name: str) -> str:
    """The name without its edition and platform tail (as `hltb_match.core`
    cuts it), normalized — but a cut that would take a word of the game's
    own takes only the edition's words at the end."""
    # A parenthesis at the end qualifies the release ("(Classic, 2005)", "(PC)").
    name = _PARENTHESIS.sub("", name).strip() or name
    full = normalize(name)
    kept = normalize(core(name))
    full_words, kept_words = full.split(), kept.split()
    if full_words[: len(kept_words)] != kept_words:
        return kept
    removed = full_words[len(kept_words) :]
    if all(w in _EDITION_TAIL_WORDS for w in removed):
        return kept
    words = list(full_words)
    while len(words) > 1 and words[-1] in _EDITION_TAIL_WORDS:
        words.pop()
    return " ".join(words)


def name_key(name: str) -> str:
    """A name as the matcher compares it, platforms said in it dropped too: what
    a store search's hits are measured by."""
    words = _unmarked(game_core(name)).split()
    kept = [w for w in words if w not in _PLATFORM_WORDS] or words
    return " ".join(kept)


def _unmarked(name: str) -> str:
    words = [w for w in name.split() if w not in _RELEASE_WORDS]
    return " ".join(words) or name


def _overlap(a: frozenset[str], b: frozenset[str]) -> float | None:
    if len(a) < ACHIEVEMENTS_MIN or len(b) < ACHIEVEMENTS_MIN:
        return None
    return len(a & b) / min(len(a), len(b))


def _numbers(candidate: Candidate) -> set[str]:
    found: set[str] = set()
    for name in candidate.cores:
        found |= {tok for tok in name.split() if tok.isdigit() and len(tok) < 4}
    return found


def _same(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    x, y = normalize(a), normalize(b)
    return bool(x and y) and (x == y or x in y or y in x)
