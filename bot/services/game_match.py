"""How two versions relate (#147) — a weighted model, no database access.

Every pair of versions shows signs (`features`), read from its subject's side
(the later release, the compilation, the VR one): one achievement list, an
Xbox cross-gen set, a store's group, one HLTB entry, how alike the cut names
are, a sequel's number, a remaster's or a remake's word, how many of the
achievements' names they share, the studio, the years. Each class — one game,
or the subject a remaster, a remake, a compilation or the VR version of the
other (owner, 2026-10-11) — adds up its weights (`WEIGHTS`), and a softmax
against "other" makes probabilities. **Nothing is certain** (owner,
2026-10-10): the weights are starting values, to be fitted to the operator's
decisions.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from bot.services.hltb_match import core, normalize, similarity
from bot.services.stores import UNKNOWN_STORE

# A name tail that says which release of the game this is.
_REMASTER = re.compile(
    r"\b(remaster(?:ed)?|definitive|anniversary|redux|hd|enhanced|director'?s cut)\b",
    re.IGNORECASE,
)
_EDITION = re.compile(
    r"\b(game of the year|goty|complete|deluxe|ultimate|gold|premium|legendary|collector'?s"
    r"|special edition)\b",
    re.IGNORECASE,
)
_DEMO = re.compile(
    r"\b(demo|trial|prologue|beta|tech(?:nical)? test|playtest|stress test)\b", re.IGNORECASE
)
# A tool made for a game, not a game (owner, 2026-10-10: "Fallout 4: Creation
# Kit" belongs to Fallout 4). Steam files it as a game.
_TOOL = re.compile(
    r"\b(creation kit|construction set|mod(?:ding)? tools?|(?:level|map) editor|editor"
    r"|sdk|dedicated server|toolkit|tool ?set)\b",
    re.IGNORECASE,
)

# Microsoft's abbreviation of one series (owner, 2026-10-12): its 360 lists
# are "COD: Black Ops II", "COD: MW Bundle". Read as the full name, so they
# meet "Call of Duty: Black Ops II" — one rule, not an alias table.
_COD = re.compile(r"^\s*COD(?=\s*:|\s)")

# Steam's app type for a launcher of one mode of another app ("Call of Duty:
# Black Ops II - Zombies"): a part of that game, not a game.
MODE_KIND = "advertising"

# Not a game at all (owner, 2026-10-12): an extra — a soundtrack, an artbook,
# an app, an Insider build. The store's own type says it first (Xbox's
# Application, Steam's music and video); a name says it where the store files
# it as a game ("DOOM: The Dark Ages Digital Artbook and Soundtrack", "Sea of
# Thieves Insider" — an Insider program's build is named so on every game).
EXTRA_KINDS = frozenset({"app", "music", "video"})
_EXTRA = re.compile(
    r"\b(soundtrack|o\.?s\.?t|original score|art ?book|digital comic|making of)\b"
    r"|\binsider[\s™®]*$",
    re.IGNORECASE,
)

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
    # Xbox's cross-gen set: One and Series of one game.
    cross_gen_set: str | None = None
    hltb_ids: frozenset[int] = frozenset()
    achievements: frozenset[str] = frozenset()
    # Its achievement list (`titles`): Smart Delivery's One and Series, and a
    # Play Anywhere PC, are one list — and so one game.
    list_key: tuple[str, str] | None = None
    stand_in: bool = False
    # Its HLTB entries' types ("compil": HLTB files it as a compilation).
    hltb_types: frozenset[str] = frozenset()

    @property
    def cores(self) -> tuple[str, ...]:
        """The cut names without the words that name a release, not the
        game ("Gears of War: Reloaded" is Gears of War)."""
        cut = (_unmarked(game_core(n)) for n in self.names if n)
        return tuple(dict.fromkeys(c for c in cut if c.strip()))

    @property
    def fulls(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(f for f in (_normal(n) for n in self.names if n) if f))


@dataclass(slots=True)
class Verdict:
    """What the model says about one pair: which is the subject (the later
    release, the compilation, the VR one), the most likely relation, every
    class's probability, and the signs that decided it."""

    subject: int  # version id
    other: int
    relation: str  # same / remaster_of / remake_of / contains / vr_of / other
    p: float  # the probability of `relation`
    probs: dict[str, float]
    state: str  # linked / review / apart
    features: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    @property
    def p_same(self) -> float:
        return self.probs.get("same", 0.0)


def is_extra(candidate: Candidate) -> bool:
    """Not a game: kept an entry of its own, joined to nothing."""
    return (candidate.kind or "") in EXTRA_KINDS or any(_EXTRA.search(n) for n in candidate.names)


def is_compilation(candidate: Candidate) -> bool:
    """A release that holds several games: its name says so, or its HLTB
    entry is filed as a compilation."""
    return "compil" in candidate.hltb_types or any(_COMPILATION.search(n) for n in candidate.names)


def kind_of(candidate: Candidate) -> str:
    """A version's role inside its game, from the store's own kind first and
    the name second: a mode (a Steam launcher of one mode of another app), a
    demo, a tool, an edition, or the game itself. (A remaster is no role: it
    is a game of its own, 2026-10-11.)"""
    if (candidate.kind or "") == MODE_KIND:
        return "mode"
    if any(_TOOL.search(n) for n in candidate.names):
        return "tool"
    if (candidate.kind or "") == "demo" or any(_DEMO.search(n) for n in candidate.names):
        return "demo"
    if any(_EDITION.search(n) for n in candidate.names):
        return "edition"
    return "version"


# The relations a pair of versions can have (#147; owner, 2026-10-11): one
# game, or two games of which the first (the subject) is a remaster, a remake,
# a compilation or the VR version of the second — or nothing ("other").
CLASSES = ("same", "remaster_of", "remake_of", "contains", "vr_of")
RELATIONS = CLASSES[1:]

# What each sign adds to each class's log-odds against "other" (whose log-odds
# is 0); a softmax makes them probabilities. Every rule is a weight, nothing is
# certain (owner, 2026-10-10); the weights are starting values, to be fitted to
# the operator's decisions (`match_decisions` keeps each pair's signs).
WEIGHTS: dict[str, dict[str, float]] = {
    "same": {
        "bias": -3.0,
        "one_list": 12.0,  # the same achievement list (Smart Delivery, Play Anywhere)
        # A PC version of an unknown store (an Xbox list on Win32 alone) and
        # a version of the very same name: that game, seen by the Xbox app.
        "unknown_pc_namesake": 12.0,
        "cross_gen_set": 6.0,  # Xbox: one game on One and Series
        "cross_gen_pair": 4.0,  # PS4/PS5, One/Series released together: one game
        "later_list_same_family": -4.0,  # a list of its own on a newer console, later
        "later_list_same_store": -3.0,  # a list of its own in the same store, years later
        "same_name": 2.0,  # the very same name, no release word on either
        "same_name_far": -2.5,  # the very same name, five years and more apart
        "same_name_other_studio": -3.0,  # the very same name, another studio
        "subtitles_differ": -4.0,  # one name, two subtitles: two games
        "same_group": 3.0,  # one store filed them under one game, names alike
        "same_group_other_name": 0.5,  # a store's group can hold a series
        "groups_differ": -2.0,
        "steam_parent": 6.0,  # Steam names one the other's game (a demo, a tool)
        "same_hltb": 2.5,  # one HLTB entry — found by name, so a weak sign
        "name": 10.0,  # × (name similarity − 0.8)
        "full_name": 4.4,  # the very same full name, a few years apart at most
        "franchise": 2.0,  # one name ends the other ("Call of Duty: Modern Warfare 2")
        "subtitle": -1.5,  # one name opens the other, which goes on
        "numbers_differ": -9.0,  # Halo and Halo 2
        "remaster_word": -1.0,
        "remake_word": -2.0,
        "edition_word_near": 1.5,  # GOTY / Complete, close in years
        # A compilation is never one game with a single game (owner, 2026-10-12).
        "compilation_word": -6.0,
        "vr_word": -4.0,
        "list_subset": -2.0,
        # An extra (a soundtrack, an app) and a game are never one game; two
        # extras may be (one soundtrack on two consoles).
        "extra_pair": -20.0,
        "overlap_high": 5.0,  # ≥ 60% of the achievements' names shared
        "overlap_partial": 1.0,
        "overlap_low": -2.0,
        "years_near": 3.5,
        "years_gap": -0.4,  # × each year past the first (at most 9)
        "developer_same": 0.7,
        "developer_differs": -1.0,
        "publisher_same": 0.3,
        "demo_of": 7.0,
        "tool_of": 7.0,
        "mode_of": 7.0,  # a mode's launcher, its game's name opening its own
    },
    "remaster_of": {
        "bias": -5.0,
        "one_list": -6.0,
        "unknown_pc_namesake": -6.0,
        "cross_gen_set": -2.0,
        "cross_gen_pair": -1.0,
        "later_list_same_family": 3.0,  # Ghost of Tsushima DC on PS5 (owner, 2026-10-11)
        "later_list_same_store": 3.0,  # Skyrim → Special Edition on Steam
        "same_name": -4.0,  # same name, no release word: not a remaster
        "same_name_far": -2.0,
        "subtitles_differ": -3.0,
        "same_group": 1.0,
        "steam_parent": -2.0,
        "same_hltb": 1.5,
        "name": 8.0,
        "full_name": 1.0,
        "franchise": 1.0,
        "subtitle": -1.0,
        "numbers_differ": -9.0,
        "remaster_word": 3.0,
        "remake_word": 0.5,
        "edition_word_near": -0.5,
        "vr_word": -4.0,
        "overlap_high": 4.0,
        "overlap_partial": 3.5,  # Gears → Ultimate Edition shares 43%
        "overlap_low": -1.0,
        "years_near": -2.0,
        "years_gap": 0.15,
        "developer_same": 0.2,
        "developer_differs": -0.5,
        "publisher_same": 0.8,
        "demo_of": -5.0,
        "tool_of": -5.0,
        "mode_of": -5.0,
        "extra_pair": -20.0,  # an extra relates to nothing but as "another of the series"
        "extra_both": -20.0,
    },
    "remake_of": {
        "bias": -6.0,
        "one_list": -6.0,
        "unknown_pc_namesake": -6.0,
        "cross_gen_set": -2.0,
        "cross_gen_pair": -2.0,
        "later_list_same_family": 1.0,
        "same_name_far": 3.0,  # the same name years later: a remake, or another game
        "same_name_other_studio": -1.0,
        "subtitles_differ": -1.0,
        "groups_differ": 0.5,
        "steam_parent": -2.0,
        "same_hltb": -1.0,
        "name": 8.0,
        "full_name": 2.0,
        "subtitle": 0.5,
        "numbers_differ": -6.0,
        "remaster_word": -1.0,
        "remake_word": 4.0,
        "edition_word_near": -1.0,
        "compilation_word": -1.0,
        "vr_word": -4.0,
        "list_subset": -1.0,
        "overlap_high": -1.0,
        "overlap_partial": 1.5,
        "overlap_low": 1.0,
        "years_near": -4.0,
        "years_gap": 0.3,
        # The same studio remaking its game (RE4) against another studio's
        # game of the same name (Battlefront II, NFS: Most Wanted).
        "developer_same": 1.0,
        "developer_differs": -1.5,
        "publisher_same": 1.2,
        "demo_of": -5.0,
        "tool_of": -5.0,
        "mode_of": -5.0,
        "extra_pair": -20.0,  # an extra relates to nothing but as "another of the series"
        "extra_both": -20.0,
    },
    "contains": {
        "bias": -6.0,
        "one_list": -6.0,
        "unknown_pc_namesake": -6.0,
        "cross_gen_set": -2.0,
        "cross_gen_pair": -2.0,
        "steam_parent": -2.0,
        "same_hltb": -1.0,
        "franchise": 1.0,
        "compilation_word": 3.0,
        "list_subset": 4.0,  # the part's list sits inside the compilation's
        "overlap_high": -1.0,
        "overlap_partial": 2.0,
        "overlap_low": -1.0,
        "years_gap": 0.1,
        "developer_same": 0.5,
        "publisher_same": 1.0,
        "demo_of": -5.0,
        "tool_of": -5.0,
        "mode_of": -5.0,
        "extra_pair": -20.0,  # an extra relates to nothing but as "another of the series"
        "extra_both": -20.0,
    },
    "vr_of": {  # owner, 2026-10-11: a VR version is its own relation
        "bias": -6.0,
        "one_list": -6.0,
        "unknown_pc_namesake": -6.0,
        "vr_word": 8.0,
        "name": 8.0,
        "numbers_differ": -9.0,
        "overlap_high": 1.0,
        "overlap_partial": 1.0,
        "developer_same": 0.5,
        "publisher_same": 0.5,
        "demo_of": -5.0,
        "tool_of": -5.0,
        "mode_of": -5.0,
        "extra_pair": -20.0,  # an extra relates to nothing but as "another of the series"
        "extra_both": -20.0,
    },
}
MODEL = "multiclass-1"  # stored beside every decision: which weights saw it
LINK_P = 0.85  # at or above: linked (one game, or the relation)
REVIEW_P = 0.15  # at or above (below LINK_P): the operator decides
CLOSE_CALL = 0.2  # two classes this close: the operator decides
VETO_P = 0.05  # below this "same", two clusters never join (unless one list)

_REMAKE = re.compile(r"\b(remake|reimagined|reignited|n sane|rehydrated|part i)\b", re.I)
_COMPILATION = re.compile(r"\b(collection|trilogy|anthology|legendary edition)\b|\s\+\s", re.I)
_VR = re.compile(r"\bvr\b", re.I)
_FAMILIES = {
    "360": "xbox",
    "one": "xbox",
    "series": "xbox",
    "pc": "xbox",
    "ps3": "psn",
    "ps4": "psn",
    "ps5": "psn",
    "vita": "psn",
    "steam": "steam",
}
_GENERATION = {"360": 1, "ps3": 1, "vita": 1, "one": 2, "ps4": 2, "series": 3, "ps5": 3}
_CROSS_GEN = ({"ps4", "ps5"}, {"one", "series"})


def subject_of(a: Candidate, b: Candidate) -> tuple[Candidate, Candidate]:
    """(subject, other): the VR one, else the compilation, else the later one,
    else the one with the larger list — the side a relation points from."""
    for test in (
        lambda c: any(_VR.search(n) for n in c.names),
        is_compilation,
    ):
        if test(a) != test(b):
            return (a, b) if test(a) else (b, a)
    if era(a) != era(b):
        return (a, b) if era(a) > era(b) else (b, a)
    return (a, b) if len(a.achievements) >= len(b.achievements) else (b, a)


def features(a: Candidate, b: Candidate, *, ordered: bool = False) -> dict[str, float]:
    """The signs one pair shows, read from the subject's side (see
    `subject_of`; `ordered`: `a` is the subject, as an operator's label
    "a is a remaster of b" says): each 0..1, the name a similarity, the years
    a count."""
    s, o = (a, b) if ordered else subject_of(a, b)
    f: dict[str, float] = {"bias": 1.0}
    if s.list_key and s.list_key == o.list_key:
        f["one_list"] = 1.0
    if s.cross_gen_set and s.store == o.store and s.cross_gen_set == o.cross_gen_set:
        f["cross_gen_set"] = 1.0
    if _unknown_pc_namesake(s, o):
        f["unknown_pc_namesake"] = 1.0
    gap = abs(s.year - o.year) if s.year and o.year else None
    # Released together (the same year): one game even with two lists; a
    # year later on the newer console it is a remaster (owner, 2026-10-11).
    # Only under one name: two games of one pack (Return to Arkham's Asylum
    # on One, its City on Series) are released together too.
    if (
        {s.console, o.console} in _CROSS_GEN
        and gap == 0
        and any(x == y for x in s.cores for y in o.cores)
    ):
        f["cross_gen_pair"] = 1.0
    if (
        s.list_key
        and o.list_key
        and s.list_key != o.list_key
        and _FAMILIES.get(s.console) == _FAMILIES.get(o.console)
        and _GENERATION.get(s.console, 0) > _GENERATION.get(o.console, 0)
        and (gap is None or gap >= NEAR_YEARS)
        and "cross_gen_pair" not in f
    ):
        f["later_list_same_family"] = 1.0
    same_group = bool(s.store_group and s.store == o.store and s.store_group == o.store_group)
    if s.hltb_ids & o.hltb_ids:
        f["same_hltb"] = 1.0
    if s.store == o.store == "steam" and (
        s.store_group == o.product_id or o.store_group == s.product_id
    ):
        f["steam_parent"] = 1.0

    name = max((similarity(x, y) for x in s.cores for y in o.cores), default=0.0)
    if any(x == y for x in s.fulls for y in o.fulls):
        name = 1.0
        if gap is None or gap < FAR_YEARS:
            f["full_name"] = 1.0
    elif name < CONTAINED_NAME and _contained(s, o):
        name = CONTAINED_NAME
        f["franchise"] = 1.0
    f["name"] = name - NAME_FLOOR
    if same_group:
        f["same_group" if name >= NAME_FLOOR else "same_group_other_name"] = 1.0
    elif _groups_differ(s, o):
        f["groups_differ"] = 1.0
    if "franchise" not in f and name < 1.0 and _subtitled(s, o):
        f["subtitle"] = 1.0
    if _subtitles_differ(s, o):
        # "FF7 Rebirth" and "FF7 Revelation", "Gears of War: Judgment" and
        # "…: E-Day": one name goes on two ways — two games.
        f["subtitles_differ"] = 1.0
    if (
        s.store == o.store
        and s.console == o.console
        and s.list_key
        and o.list_key
        and s.list_key != o.list_key
        and gap is not None
        and gap >= 2
    ):
        f["later_list_same_store"] = 1.0

    if _mode_pair(s, o):
        f["mode_of"] = 1.0
        f.pop("subtitle", None)
    elif _demo_pair(s, o):
        f["demo_of"] = 1.0
        f.pop("subtitle", None)
    elif _tool_pair(s, o):
        f["tool_of"] = 1.0
        f.pop("subtitle", None)
    elif name < 1.0 and _numbers(s) != _numbers(o):
        f["numbers_differ"] = 1.0

    def says(pattern: re.Pattern[str], c: Candidate) -> bool:
        return any(pattern.search(n) for n in c.names)

    if says(_REMASTER, s) and not says(_REMASTER, o):
        f["remaster_word"] = 1.0
    if says(_REMAKE, s) and not says(_REMAKE, o):
        f["remake_word"] = 1.0
    if says(_EDITION, s) and gap is not None and gap <= NEAR_YEARS:
        f["edition_word_near"] = 1.0
    if is_compilation(s) and not is_compilation(o):
        f["compilation_word"] = 1.0
    if is_extra(s) != is_extra(o):
        f["extra_pair"] = 1.0
    elif is_extra(s):
        f["extra_both"] = 1.0
    if says(_VR, s) and not says(_VR, o):
        f["vr_word"] = 1.0

    if len(s.achievements) >= ACHIEVEMENTS_MIN and len(o.achievements) >= ACHIEVEMENTS_MIN:
        shared = len(s.achievements & o.achievements)
        if len(s.achievements) >= 1.8 * len(o.achievements) and shared >= 0.5 * len(o.achievements):
            f["list_subset"] = 1.0
        overlap = shared / min(len(s.achievements), len(o.achievements))
        if overlap >= ACHIEVEMENTS_SAME and "list_subset" not in f:
            f["overlap_high"] = 1.0
        elif overlap >= ACHIEVEMENTS_REMASTER:
            f["overlap_partial"] = 1.0
        elif overlap <= ACHIEVEMENTS_OTHER:
            f["overlap_low"] = 1.0

    if s.developer and o.developer:
        f["developer_same" if _same(s.developer, o.developer) else "developer_differs"] = 1.0
    if _same(s.publisher, o.publisher):
        f["publisher_same"] = 1.0
    if same_name(s, o):
        # One name, no release word: a port, not a remaster (RE5, Terraria;
        # owner, 2026-10-11).
        f["same_name"] = 1.0
        # The very same name, no release word on either (owner, 2026-10-11):
        # years apart or by another studio it may be a remake as well as
        # another game — the operator looks at every such pair.
        if gap is not None and gap >= FAR_YEARS:
            f["same_name_far"] = 1.0
        if "developer_differs" in f:
            f["same_name_other_studio"] = 1.0
    if gap is None:
        f["year_unknown"] = 1.0
    elif gap <= NEAR_YEARS:
        f["years_near"] = 1.0
    else:
        f["years_gap"] = float(min(gap - NEAR_YEARS, 9))
    if "demo_of" in f or "tool_of" in f or "mode_of" in f:
        # Its game's name opens it (that is what made it one): the rest of
        # its name says nothing more, nor, for a tool or a mode, its years.
        f["name"] = 0.0
        if "tool_of" in f or "mode_of" in f:
            f.pop("years_gap", None)
        if "mode_of" in f:
            # A mode's list is a part of its game's one list (Zombies' 50 of
            # Black Ops II's 90 on 360): a part, not a compilation's.
            f.pop("list_subset", None)
    return f


def probabilities(
    f: dict[str, float], weights: dict[str, dict[str, float]] | None = None
) -> dict[str, float]:
    """Each class's probability (and "other"'s): a softmax over the log-odds."""
    w = weights or WEIGHTS
    logits = {c: sum(w[c].get(k, 0.0) * v for k, v in f.items()) for c in CLASSES}
    logits["other"] = 0.0
    top = max(logits.values())
    exp = {c: math.exp(max(-40.0, x - top)) for c, x in logits.items()}
    total = sum(exp.values())
    return {c: v / total for c, v in exp.items()}


def compare(a: Candidate, b: Candidate) -> Verdict:
    """How two versions relate, and how sure the model is."""
    s, o = subject_of(a, b)
    f = features(a, b)
    probs = probabilities(f)
    ranked = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
    (relation, p), (_second, p2) = ranked[0], ranked[1]
    best_link = max(((c, probs[c]) for c in CLASSES), key=lambda kv: kv[1])
    # The same name years apart or by another studio is the operator's —
    # unless one is the PC game the Xbox app saw (its year is a guess).
    namesake = (
        "same_name_far" in f or "same_name_other_studio" in f
    ) and "unknown_pc_namesake" not in f
    if relation != "other" and p >= LINK_P and p - p2 >= CLOSE_CALL and not namesake:
        state = "linked"
    elif best_link[1] >= REVIEW_P or namesake:
        # One name, far apart: the operator decides, however sure the model.
        state = "review"
        relation, p = best_link
    else:
        state = "apart"
    w = WEIGHTS.get(relation, {})
    reasons = [f"{relation} {p:.2f}"] + [
        f"{k} {w.get(k, 0.0) * v:+.1f}"
        for k, v in sorted(f.items(), key=lambda kv: -abs(w.get(kv[0], 0.0) * kv[1]))
        if k != "bias" and w.get(k, 0.0)
    ]
    return Verdict(s.version_id, o.version_id, relation, p, probs, state, f, reasons)


def is_unknown_pc(candidate: Candidate) -> bool:
    """A PC version whose store is not known (see `stores.UNKNOWN_STORE`)."""
    return candidate.store == UNKNOWN_STORE


def _unknown_pc_namesake(a: Candidate, b: Candidate) -> bool:
    """One is a PC version of an unknown store, the other a known version of
    the very same release name (owner, 2026-10-12): the Xbox app saw that
    game played on PC — Heavy Rain's Steam app, never an Xbox game."""
    if is_unknown_pc(a) == is_unknown_pc(b):
        return False

    def names(c: Candidate) -> set[str]:
        return {normalize(release_name(_aliased(n))) for n in c.names if normalize(n)}

    return bool(names(a) & names(b))


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


def _mode_pair(a: Candidate, b: Candidate) -> bool:
    """A mode's launcher whose game's name opens it ("Call of Duty: Black
    Ops II" → "… - Zombies"), not filed by one store under another game.
    Years say nothing: Steam gives such an app no date of its own."""
    for mode, game in ((a, b), (b, a)):
        if (
            kind_of(mode) == "mode"
            and kind_of(game) not in ("mode", "tool", "demo")
            and not _groups_differ(mode, game)
            and _starts(game, mode)
        ):
            return True
    return False


def _tool_pair(a: Candidate, b: Candidate) -> bool:
    """A tool whose game's name opens it ("Fallout 4" → "Fallout 4: Creation
    Kit"), not filed by one store under another game of its own. Years say
    nothing: a kit comes out when it comes out."""
    for tool, game in ((a, b), (b, a)):
        if (
            kind_of(tool) == "tool"
            and kind_of(game) not in ("tool", "demo")
            and not _groups_differ(tool, game)
            and _starts(game, tool)
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
    other — a subtitle after it is another game ("Gears of War: Judgment") —
    and not a LEGO game's ("LEGO Marvel's Avengers" is not "Marvel's
    Avengers")."""
    for x in a.cores:
        for y in b.cores:
            short, long_ = sorted((_words(x), _words(y)), key=len)
            if 2 <= len(short) < len(long_) and long_[-len(short) :] == short:
                if "lego" not in long_[: len(long_) - len(short)]:
                    return True
    return False


def _groups_differ(a: Candidate, b: Candidate) -> bool:
    """One store filed them under different games of its own (Xbox's
    product groups): "Gears of War: E-Day Multiplayer Beta" is E-Day's."""
    return bool(
        a.store == b.store and a.store_group and b.store_group and a.store_group != b.store_group
    )


def same_name(a: Candidate, b: Candidate) -> bool:
    """The very same cut name, and neither says it is a remaster, a remake,
    an edition or a compilation ("Resident Evil 4" and "Resident Evil 4
    (2005)", "Call of Duty: Modern Warfare" 2007 and 2019)."""
    if not any(x == y for x in a.cores for y in b.cores):
        return False
    marked = (_REMASTER, _REMAKE, _EDITION, _COMPILATION, _VR, _DEMO, _TOOL)
    return not any(pat.search(n) for c in (a, b) for n in c.names for pat in marked)


def _subtitles_differ(a: Candidate, b: Candidate) -> bool:
    """Both cut names go on past a shared head of two words or more, each its
    own way."""
    for x in a.cores:
        for y in b.cores:
            wx, wy = _words(x), _words(y)
            head = 0
            while head < min(len(wx), len(wy)) and wx[head] == wy[head]:
                head += 1
            if head >= 2 and head < len(wx) and head < len(wy):
                return True
    return False


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
        for d in (_normal(n) for n in demo.names):
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


# A year a store puts in a name: "STAR WARS Battlefront II (Classic, 2005)".
_YEAR_IN_NAME = re.compile(r"\((?:[^()]*\D)?((?:19|20)\d\d)\)")


def version_year(
    name: str | None, release_date: str | None, hltb_year: int | None = None
) -> int | None:
    """When a version first came out, as early as anything says: the year
    its name gives, its HLTB entry's, its store's date (a store's date is
    often a re-release: Steam's classic Battlefront II says 2009)."""
    years = []
    if name and (m := _YEAR_IN_NAME.search(name)) is not None:
        years.append(int(m.group(1)))
    if hltb_year:
        years.append(int(hltb_year))
    if release_date and release_date[:4].isdigit():
        years.append(int(release_date[:4]))
    return min(years) if years else None


def candidate_year(row: dict) -> int | None:
    """The one year of a version, for the matcher and the game's facts
    alike: its name's and its store's; its HLTB entry's only for a stand-in
    no store describes (an HLTB entry is found by name — a weak sign)."""
    hltb = row.get("hltb_year") if row.get("stand_in") else None
    return version_year(row.get("name"), row.get("release_date"), hltb)


@dataclass(slots=True)
class GameFacts:
    year: int | None
    developer: str | None
    publisher: str | None
    # The latest version's year, and whether another version names another
    # studio or publisher.
    last_year: int | None = None
    more_developers: bool = False
    more_publishers: bool = False


# Words a company's name carries or drops from store to store.
_COMPANY_TAIL = {
    "inc",
    "ltd",
    "llc",
    "sa",
    "s",
    "a",
    "gmbh",
    "co",
    "corp",
    "corporation",
    "ab",
    "plc",
    "bv",
    "srl",
    "oy",
    "kk",
    "limited",
    "entertainment",
}


def company_key(name: str) -> str:
    """A company as one name whatever a store writes: "CD PROJEKT S.A.",
    "CD Projekt" and "CD PROJEKT RED, Warner Bros." (its first) start alike;
    "BioWare™" is BioWare."""
    first = re.split(r"[,/&]| and ", name)[0]
    words = re.sub(r"[^\w\s]", " ", first.replace("™", "").replace("®", "")).casefold().split()
    while len(words) > 1 and words[-1] in _COMPANY_TAIL:
        words.pop()
    return " ".join(words)


def game_facts(versions: list[dict]) -> GameFacts:
    """A game's year is the earliest of its versions'; its developer and
    publisher are the earliest version's that names one (owner, 2026-10-10:
    a remaster's studio is not the game's). Demos and compilations say
    nothing about the game (Halo: MCC is not when Halo 2 came out). Each
    version: name, release_date, hltb_year, developer, publisher, kind."""
    own = [
        v for v in versions if v.get("kind") not in ("demo", "compilation", "tool", "mode")
    ] or versions
    dated = sorted(
        ((candidate_year(v) or 9999, i, v) for i, v in enumerate(own)),
        key=lambda t: (t[0], t[1]),
    )
    years = [y for y, _, _ in dated if y != 9999]
    developer = next((str(v["developer"]) for _, _, v in dated if v.get("developer")), None)
    publisher = next((str(v["publisher"]) for _, _, v in dated if v.get("publisher")), None)

    def more(field: str, first: str | None) -> bool:
        return first is not None and any(
            v.get(field) and company_key(str(v[field])) != company_key(first) for v in own
        )

    return GameFacts(
        min(years) if years else None,
        developer,
        publisher,
        last_year=max(years) if years else None,
        more_developers=more("developer", developer),
        more_publishers=more("publisher", publisher),
    )


def _first_name(candidate: Candidate) -> str | None:
    """The name a version is called by: its first that says something."""
    return next((n for n in candidate.names if normalize(n)), None)


def game_name(members: list[Candidate], *, release: bool = False) -> str:
    """A game's name. It keeps the words that tell it apart (owner,
    2026-10-12): **the full release name** (platform tails cut) when every
    version of it carries the same release tail ("CONTROL Ultimate Edition"
    and "Control Ultimate Edition - Xbox Series X|S" are "CONTROL Ultimate
    Edition", not "Control"), when it is a compilation, or when it is a
    remaster, remake, VR version or compilation of another game (`release`,
    the linker knows that). Only a game whose versions differ in their tails
    (Control and its Ultimate Edition) is called by their common core — the
    plainest version's, the earliest. Its parts (demos, tools, modes) say
    nothing about its name."""
    games = [m for m in members if kind_of(m) not in ("demo", "tool", "mode")] or members
    plain = [m for m in games if kind_of(m) == "version"] or games
    plain.sort(key=lambda m: (era(m) or 9999, len(m.names[0] if m.names else "")))
    first = plain[0]
    if not first.names:
        return first.product_id
    name = _aliased(_first_name(first) or first.names[0])
    tails = {release_tail(n) for n in (_first_name(m) for m in games) if n}
    if release or (len(tails) == 1 and tails != {()}):
        return release_name(name)
    if any(_COMPILATION.search(n) for n in first.names):
        # A compilation's own words are its name ("Mass Effect Legendary
        # Edition" is not "Mass Effect").
        return release_name(name)
    cut = core(name)
    if normalize(cut) != game_core(name):
        # The cut took words of the game's own ("The Elder Scrolls V" of
        # "…: Skyrim Special Edition"): the release name instead.
        return release_name(name)
    return cut


# Words of a release tail that tell no release from another: "Standard
# Edition" is the game, "Early Access" a state of it, "The Game" no
# release, and a demo or a beta is a part of the game, not a release of it
# (a game known only by its demo is that game).
_QUIET_TAIL = {
    "edition",
    "standard",
    "digital",
    "the",
    "and",
    "for",
    "early",
    "access",
    "game",
    "video",
    "demo",
    "trial",
    "beta",
    "open",
    "closed",
    "tech",
    "technical",
    "test",
    "playtest",
}
_PLATFORM_TAIL_WORDS = {
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
}


def release_tail(name: str) -> tuple[str, ...]:
    """The words a version's name adds to its game's core to say which
    release it is ("ultimate", "remastered", "goty", "directors cut"), as a
    key two names compare by; () when it names the game alone."""
    full = normalize(release_name(_aliased(name))).split()
    kept = game_core(name).split()
    if full[: len(kept)] != kept:
        return ()
    rest = " ".join(full[len(kept) :]).replace("game of the year", "goty")
    return tuple(w for w in rest.split() if w not in _QUIET_TAIL | _PLATFORM_TAIL_WORDS)


_PLATFORM_TAIL = re.compile(
    r"[\s:\-–—]*\b(?:for\s+)?(?:windows(?:\s*10|\s*11)?|pc"
    r"|xbox(?:\s+one|\s+series(?:\s+x\s*\|?\s*s)?)?|ps[345](?:\s*(?:&|and|/)\s*ps[345])?"
    r"|playstation\s*[345]?)"
    # "Minecraft: Windows 10 Edition", "… Xbox One Edition": a platform's
    # edition is the platform, not a release.
    r"(?:\s+edition)?\s*$",
    re.IGNORECASE,
)


def release_name(name: str) -> str:
    """A version's name as the release it names, edition words kept, only
    trademarks, a qualifying parenthesis and a platform tail cut: what a
    remaster or a compilation is called ("Gears of War: Ultimate Edition")."""
    text = re.sub(r"[™®©℠]", "", name)
    text = _PARENTHESIS.sub("", text).strip() or text
    return _PLATFORM_TAIL.sub("", text).strip() or text


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
    name = _aliased(name)
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


def _aliased(name: str) -> str:
    """ "COD: Black Ops II" as "Call of Duty: Black Ops II" (see `_COD`)."""
    return _COD.sub("Call of Duty", name, count=1)


def _normal(name: str) -> str:
    return normalize(_aliased(name))


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
        # Four digits too: Battlefield 1942 is not 2042. A year a store adds
        # in parentheses ("(2005)") is gone with the parenthesis already.
        found |= {tok for tok in name.split() if tok.isdigit() and len(tok) <= 4}
    return found


def _same(a: str | None, b: str | None) -> bool:
    """One company however a store writes it: "CD PROJEKT S.A." and "CD
    Projekt", "BioWare™" and "BioWare"."""
    if not a or not b:
        return False
    x, y = company_key(a), company_key(b)
    return bool(x and y) and (x == y or x.startswith(y + " ") or y.startswith(x + " "))
