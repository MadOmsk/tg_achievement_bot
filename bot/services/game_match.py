"""Which versions are one game (#147, stage 3) — decided from what the stores
and our own achievement lists say, no database access here.

Hard facts first: the same store group (Xbox ProductGroup / CrossGenSet, a
PSN concept), the same HLTB entry, a Steam demo's own game. Then a score: the
name with its edition and platform tails cut (as `hltb_match` cuts them; a
differing number is never the same game), the achievements' names — the
strongest sign, one list's names are the same on every platform — the
developer, the publisher and the release year.

A pair is `linked`, `review` (the operator decides) or apart. **The same name
with release years far apart is always `review`** (owner, 2026-10-09): a port
ten years later (Resident Evil 5 on PS4), a remaster and a remake (Resident
Evil 2) look alike here, and only a person tells them apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bot.services.hltb_match import core, normalize, similarity

# A name tail that says which release of the game this is.
_REMASTER = re.compile(
    r"\b(remaster(?:ed)?|definitive|reloaded|anniversary|redux|hd|enhanced|director'?s cut)\b",
    re.IGNORECASE,
)
_EDITION = re.compile(
    r"\b(game of the year|goty|complete|deluxe|ultimate|gold|premium|legendary|collector'?s)\b",
    re.IGNORECASE,
)
_DEMO = re.compile(r"\b(demo|trial|prologue|beta)\b", re.IGNORECASE)

NAME_FLOOR = 0.8  # below this, two versions are not compared further
CONTAINED_NAME = 0.85
LINK_SCORE = 0.85
REVIEW_SCORE = 0.7
FAR_YEARS = 5
NEAR_YEARS = 1
ACHIEVEMENTS_MIN = 5  # a list shorter than this says nothing
ACHIEVEMENTS_SAME = 0.6
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

    @property
    def cores(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(normalize(core(n)) for n in self.names if n))

    @property
    def fulls(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(normalize(n) for n in self.names if n))


@dataclass(slots=True)
class Verdict:
    state: str  # linked / review / apart
    score: float
    reasons: list[str] = field(default_factory=list)


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


def compare(a: Candidate, b: Candidate) -> Verdict:
    reasons: list[str] = []
    name = max((similarity(x, y) for x in a.cores for y in b.cores), default=0.0)
    if any(x == y for x in a.fulls for y in b.fulls):
        name = 1.0
    elif name < CONTAINED_NAME and _contained(a, b):
        # "Modern Warfare 2" is "Call of Duty: Modern Warfare 2" with less said.
        name = CONTAINED_NAME
    # Halo and Halo 2, Battlefront and Battlefront II: a sequel is never the same game.
    numbers_differ = name < 1.0 and _numbers(a) != _numbers(b)

    # A demo is its game's when the game's name starts the demo's ("RESIDENT
    # EVIL 2" → "RESIDENT EVIL 2 1-Shot Demo"), whatever else the demo says.
    # A demo of a sequel's base name is not its demo ("Resident Evil" →
    # "Resident Evil 4 Chainsaw Demo"), and a demo years from the game is
    # somebody else's ("Gears of War" → "Gears of War: E-Day Beta").
    for demo, game in ((a, b), (b, a)):
        if (
            kind_of(demo) == "demo"
            and kind_of(game) != "demo"
            and _starts(game, demo)
            and demo.year
            and game.year
            and abs(demo.year - game.year) <= NEAR_YEARS
        ):
            return Verdict("linked", 0.9, ["a demo of it"])

    # Hard facts: the stores and HLTB grouping them themselves.
    hard = None
    if a.store_group and a.store == b.store and a.store_group == b.store_group:
        hard = f"same {a.store} group"
    elif a.hltb_ids & b.hltb_ids:
        hard = "same HLTB entry"
    elif a.store == b.store == "steam" and (
        a.store_group == b.product_id or b.store_group == a.product_id
    ):
        hard = "Steam's own parent app"
    if hard and not numbers_differ:
        return Verdict("linked", 1.0, [hard])

    if name < NAME_FLOOR or numbers_differ:
        return Verdict("apart", name, [f"name {name:.2f}"])
    reasons.append(f"name {name:.2f}")
    score = name
    # A name alone links nothing: the achievements or the years must agree too.
    proof = False

    overlap = _overlap(a.achievements, b.achievements)
    if overlap is not None:
        reasons.append(f"achievements {overlap:.0%}")
        if overlap >= ACHIEVEMENTS_SAME:
            score = max(score, 0.95)
            proof = True
        elif overlap <= ACHIEVEMENTS_OTHER:
            # Two lists of their own: a remaster, a remake or another game.
            return Verdict("review", min(score, 1.0), [*reasons, "different achievements"])

    if _same(a.developer, b.developer):
        reasons.append("same developer")
        score += 0.05
    if _same(a.publisher, b.publisher):
        reasons.append("same publisher")
        score += 0.02

    if a.year and b.year:
        gap = abs(a.year - b.year)
        reasons.append(f"years {a.year}/{b.year}")
        if gap >= FAR_YEARS and not proof:
            # A port, a remaster or a remake: a person tells them apart.
            return Verdict("review", min(score, 1.0), [*reasons, "years far apart"])
        if gap > NEAR_YEARS:
            score -= 0.05 * (gap - NEAR_YEARS)
        else:
            proof = True
    else:
        reasons.append("a year unknown")

    score = min(score, 1.0)
    if score >= LINK_SCORE and proof:
        return Verdict("linked", score, reasons)
    if score >= REVIEW_SCORE:
        return Verdict("review", score, reasons)
    return Verdict("apart", score, reasons)


_STOP = {"the", "of", "and", "for", "game", "edition", "a", "an", "to", "in", "on"}


def block_key(candidate: Candidate) -> set[str]:
    """Words a version shares with any version it could be: the telling words
    of its cut names. Only versions sharing one are compared."""
    return {w for c in candidate.cores for w in c.split() if len(w) >= 3 and w not in _STOP}


def _words(name: str) -> list[str]:
    return name.split()


def _contained(a: Candidate, b: Candidate) -> bool:
    """One cut name is the other's, whole, at its end or start, two words at least."""
    for x in a.cores:
        for y in b.cores:
            short, long_ = sorted((_words(x), _words(y)), key=len)
            if (
                len(short) >= 2
                and len(short) < len(long_)
                and (long_[-len(short) :] == short or long_[: len(short)] == short)
            ):
                return True
    return False


def _starts(game: Candidate, demo: Candidate) -> bool:
    """The game's cut name opens the demo's, and what follows is not a number
    — unless the game has one of its own ("RESIDENT EVIL 2 1-Shot Demo")."""
    for g in game.cores:
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


def game_name(members: list[Candidate]) -> str:
    """A game is named by its plainest version: not an edition, a remaster or
    a demo where there is one, the earliest, by its cut name."""
    plain = [m for m in members if kind_of(m) == "version"] or members
    plain.sort(key=lambda m: (m.year or 9999, len(m.names[0] if m.names else "")))
    first = plain[0]
    return core(first.names[0]) if first.names else first.product_id


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
