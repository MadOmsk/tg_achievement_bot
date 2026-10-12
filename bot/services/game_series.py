"""Game series (#147; owner, 2026-10-12): which games are of one series.

A series is an entity of its own and a game may be in several — a crossover
(Street Fighter X Tekken) is in both, and **never merges the two**. What the
linker proposes is stored as `auto`, with a probability and how the game got
there; the operator's (`manual`) and the advisers' (`advisers`) answers are
never overwritten (`db/repo/_series.py`).

The evidence, strongest first:

- a remaster, a remake or a VR version is in its original's series, and a
  compilation in each of its parts' (`game_relations`);
- the labels "another game of the series" (`match_decisions.relation =
  'series'`), the operator's and the advisers';
- a common franchise prefix — the name before ":", " - " or a number ("Halo 3",
  "Halo: Reach" → Halo) — only as a weak suggestion, and never alone across
  different developers and publishers.

Grouping (`propose`): a game and its remasters, remakes and VR versions are
one unit; units join along evidence whose franchise names agree (one is the
other's word prefix). Evidence whose names disagree joins two groups only when
it is not a crossover: a game whose name holds the other group's franchise
(Street Fighter X **Tekken**), or that has evidence into two groups or more (a
compilation of several series), is added to the other group as one more
member instead; a lone game whose only evidence leads into one group joins it
(Crisis Core into Final Fantasy); otherwise strong evidence (a label, a
compilation) joins the two, weak evidence does nothing.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bot.services.advice import ADVISER_SOURCES
from bot.services.game_match import _aliased, _same, _unmarked, game_core, release_name
from bot.services.hltb_match import normalize

if TYPE_CHECKING:
    from bot.db.repo import Repo

FAMILY_P = 0.95  # a remaster, a remake, a VR version of a game of the series
CONTAINS_P = 0.9  # a compilation holding a game of the series
OPERATOR_P = 0.97  # the operator's "another game of the series"
ADVISERS_P = 0.9  # the advisers' "another game of the series"
PREFIX_P = 0.5  # a common franchise prefix, the same studio or publisher
STRONG_P = 0.9  # evidence this sure joins two groups whose names disagree
SURE_P = 0.85  # below: a membership the advisers may be asked about

_RELATION_WORDS = {
    "remaster_of": ("a remaster of", "remastered as"),
    "remake_of": ("a remake of", "remade as"),
    "vr_of": ("the VR version of", "has a VR version"),
    "contains": ("a compilation holding", "held by the compilation"),
}
FAMILY = frozenset({"remaster_of", "remake_of", "vr_of"})
# A franchise name ends before a subtitle or a number.
_SUBTITLE = re.compile(r"\s*(?::\s|\s[-–—]\s|:(?=\s*$))")
_MARKS = re.compile(r"[™®©℠]")
_PLATFORMS = {"ps3", "ps4", "ps5", "playstation", "xbox", "pc", "windows", "kinect", "vr"}


@dataclass(slots=True)
class SeriesGame:
    game_id: int
    name: str
    year: int | None = None
    developer: str | None = None
    publisher: str | None = None
    kind: str = "game"


@dataclass(slots=True)
class Evidence:
    """Why two games may be of one series: `p` how sure, `reason` worded
    from each side (`a`'s, then `b`'s)."""

    a: int
    b: int
    p: float
    reason_a: str
    reason_b: str
    # family (a remaster, a remake, a VR version) / contains / label / prefix
    kind: str = "label"

    @property
    def family(self) -> bool:
        return self.kind == "family"


@dataclass(slots=True)
class Proposal:
    """A proposed series: its own games (`core`) and every member's
    probability and reason, crossovers' included."""

    name: str
    core: list[int]
    members: dict[int, tuple[float, str]] = field(default_factory=dict)


def franchise_key(name: str) -> str:
    """The franchise a name opens with, normalized: before a subtitle or a
    number ("Halo 3", "Halo: Reach" → "halo"; "The Elder Scrolls V: Skyrim" →
    "elder scrolls"); the whole core when it has neither."""
    text = release_name(_aliased(_MARKS.sub("", name)))
    head = _SUBTITLE.split(text, maxsplit=1)[0] or text
    words = game_core(head).split()
    for i, word in enumerate(words):
        # "Sonic Frontiers PS4 & PS5": a platform in the name ends it too.
        if i and (word.isdigit() or word in _PLATFORMS):
            words = words[:i]
            break
    return " ".join(words)


def compatible(a: str, b: str) -> bool:
    """One franchise name is the other's word prefix ("gears" and "gears of
    war")."""
    if not a or not b:
        return False
    wa, wb = a.split(), b.split()
    short, long_ = sorted((wa, wb), key=len)
    return long_[: len(short)] == short


def _holds(name_words: list[str], key: str) -> bool:
    """The other group's franchise is said inside this name (Street Fighter X
    Tekken holds "tekken")."""
    words = key.split()
    if not words or len(key) < 3:
        return False
    n = len(words)
    return any(name_words[i : i + n] == words for i in range(len(name_words) - n + 1))


def _core_words(game: SeriesGame) -> list[str]:
    return _unmarked(game_core(_aliased(game.name))).split()


def evidence(
    games: dict[int, SeriesGame],
    relations: list[tuple[int, int, str]],
    labels: list[tuple[int, int, str]],
) -> list[Evidence]:
    """Every sign that two games are of one series: relations
    `(game, related, kind)`, labels `(game, other, decided_by)`, and the
    franchise prefixes the names share."""
    found: list[Evidence] = []

    def named(game_id: int) -> str:
        return f"«{games[game_id].name}»"

    for g, r, kind in relations:
        if g not in games or r not in games or g == r or kind not in _RELATION_WORDS:
            continue
        mine, theirs = _RELATION_WORDS[kind]
        found.append(
            Evidence(
                g,
                r,
                FAMILY_P if kind in FAMILY else CONTAINS_P,
                f"{mine} {named(r)}",
                f"{theirs} {named(g)}",
                kind="family" if kind in FAMILY else "contains",
            )
        )
    for a, b, by in labels:
        if a not in games or b not in games or a == b:
            continue
        who, p = ("advisers", ADVISERS_P) if by in ADVISER_SOURCES else ("operator", OPERATOR_P)
        found.append(
            Evidence(
                a,
                b,
                p,
                f"{who}: another of the series with {named(b)}",
                f"{who}: another of the series with {named(a)}",
            )
        )
    found += _prefix_evidence(games)
    return found


def _prefix_evidence(games: dict[int, SeriesGame]) -> list[Evidence]:
    """A shared franchise prefix, by the same studio or publisher: a weak
    suggestion (owner, 2026-10-12)."""
    keys = {g: franchise_key(game.name) for g, game in games.items()}
    buckets: dict[str, list[int]] = defaultdict(list)
    for g, key in keys.items():
        if key and len(key) >= 3:
            buckets[key.split()[0]].append(g)
    found: list[Evidence] = []
    for members in buckets.values():
        members.sort()
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                if not compatible(keys[a], keys[b]):
                    continue
                ga, gb = games[a], games[b]
                if _same(ga.developer, gb.developer):
                    company = "studio"
                elif _same(ga.publisher, gb.publisher):
                    company = "publisher"
                else:
                    continue
                if _core_words(games[a]) == _core_words(games[b]):
                    # One name twice is one game the matcher left split, or
                    # namesakes: no series either way.
                    continue
                shared = min(keys[a], keys[b], key=len)
                found.append(
                    Evidence(
                        a,
                        b,
                        PREFIX_P,
                        f"name «{shared}» and {company} shared with «{gb.name}»",
                        f"name «{shared}» and {company} shared with «{ga.name}»",
                        kind="prefix",
                    )
                )
    return found


def propose(games: dict[int, SeriesGame], found: list[Evidence]) -> list[Proposal]:
    """Series from the evidence: groups of two games or more, each with its
    crossovers added (see the module's doc)."""
    keys = {g: franchise_key(game.name) for g, game in games.items()}
    words = {g: _core_words(game) for g, game in games.items()}
    parent = {g: g for g in games}
    members: dict[int, set[int]] = {g: {g} for g in games}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if len(members[ra]) < len(members[rb]):
            ra, rb = rb, ra
        parent[rb] = ra
        members[ra] |= members.pop(rb)

    for e in found:
        if e.family:
            union(e.a, e.b)
    loose: list[Evidence] = []
    for e in sorted(found, key=lambda e: -e.p):
        if e.family:
            continue
        if compatible(keys[e.a], keys[e.b]):
            union(e.a, e.b)
        else:
            loose.append(e)

    neighbours: dict[int, set[int]] = defaultdict(set)
    for e in found:
        if not e.family:
            neighbours[e.a].add(e.b)
            neighbours[e.b].add(e.a)
    # (crossover game, a game of the group it is added to, the evidence)
    extras: list[tuple[int, int, Evidence]] = []
    for e in loose:
        ra, rb = find(e.a), find(e.b)
        if ra == rb:
            continue
        ka = _series_key([games[g] for g in members[ra]])
        kb = _series_key([games[g] for g in members[rb]])
        # A game already of a series whose name holds the other's franchise
        # (Street Fighter X Tekken, in Street Fighter's): a crossover, one
        # more member of the other. A lone one (Shadow of the Tomb Raider)
        # simply joins below.
        crossing = [
            (x, y)
            for x, rx, y, other_key in ((e.a, ra, e.b, kb), (e.b, rb, e.a, ka))
            if len(members[rx]) >= 2
            and _holds(words[x], other_key)
            and not compatible(keys[x], other_key)
        ]
        if crossing:
            extras += [(x, y, e) for x, y in crossing]
            continue
        lone = [
            (x, rx, ry)
            for x, rx, ry in ((e.a, ra, rb), (e.b, rb, ra))
            if len(members[rx]) == 1 and {find(n) for n in neighbours[x]} == {ry}
        ]
        if lone:
            union(e.a, e.b)
            continue
        # A compilation holding games of several series (Rare Replay) is
        # one more member of each, never what joins them.
        hubs = [
            (x, y)
            for x, rx, y in ((e.a, ra, e.b), (e.b, rb, e.a))
            if e.kind == "contains" and len({find(n) for n in neighbours[x]} - {rx}) >= 2
        ]
        if hubs:
            extras += [(x, y, e) for x, y in hubs]
            continue
        if e.p >= STRONG_P:
            union(e.a, e.b)

    groups: dict[int, list[int]] = {}
    for g in games:
        groups.setdefault(find(g), []).append(g)
    best: dict[int, dict[int, tuple[float, str]]] = defaultdict(dict)

    def keep(root: int, game: int, p: float, reason: str) -> None:
        if game not in best[root] or best[root][game][0] < p:
            best[root][game] = (p, reason)

    for e in found:
        ra, rb = find(e.a), find(e.b)
        if ra == rb:
            keep(ra, e.a, e.p, e.reason_a)
            keep(ra, e.b, e.p, e.reason_b)
    for crossover, inside, e in extras:
        root = find(inside)
        if find(crossover) != root:
            keep(root, crossover, e.p, e.reason_a if crossover == e.a else e.reason_b)

    proposals = []
    for root, core in groups.items():
        if len(core) < 2:
            continue
        core.sort(key=lambda g: (games[g].year or 9999, g))
        proposal = Proposal(series_name([games[g] for g in core]), core)
        for g in core:
            proposal.members[g] = best[root].get(g, (PREFIX_P, "grouped with the series"))
        for g, value in best[root].items():
            proposal.members.setdefault(g, value)
        proposals.append(proposal)
    return proposals


def _series_key(group: list[SeriesGame]) -> str:
    """`_franchise_of(group)`, lengthened to the words every game's core
    name goes on with alike ("Cities: Skylines", not "Cities")."""
    key = _franchise_of(group)
    cores = []
    for g in group:
        words = _core_words(g)
        cut = next((i for i, w in enumerate(words) if i and w.isdigit()), len(words))
        cores.append(words[:cut])
    common: list[str] = []
    for column in zip(*cores, strict=False):
        if len(set(column)) != 1:
            break
        common.append(column[0])
    if len(common) > len(key.split()) and common[: len(key.split())] == key.split():
        return " ".join(common)
    return key


def _franchise_of(group: list[SeriesGame]) -> str:
    """The franchise a group is named by: the one more than half of its
    games share ("Gears of War", though Gears 5 says "Gears"), else the
    longest prefix all of them share ("Sonic"), else the earliest game's."""
    keys = [franchise_key(g.name) for g in group]
    count = Counter(k for k in keys if k)
    shared = [k for k, n in count.items() if n >= 2 and 2 * n > len(group)]
    if shared:
        return max(shared, key=lambda k: (count[k], len(k.split())))
    split = [k.split() for k in keys if k]
    if split:
        common: list[str] = []
        for column in zip(*split, strict=False):
            if len(set(column)) != 1:
                break
            common.append(column[0])
        if common and any(len(w) >= 3 for w in common):
            return " ".join(common)
    earliest = min(group, key=lambda g: (g.year or 9999, g.game_id))
    return franchise_key(earliest.name) or normalize(earliest.name)


def series_name(group: list[SeriesGame]) -> str:
    """A series' name (owner, 2026-10-12): its franchise (`_series_key`) as
    its games write it."""
    key = _series_key(group)
    ordered = sorted(group, key=lambda g: (g.year or 9999, g.game_id))
    written = [w for w in (_as_written(key, g.name) for g in ordered) if w]
    if not written:
        return key.title()
    # As most of its games write it ("Resident Evil", not one list's
    # "resident evil"), the earliest on a tie.
    count = Counter(written)
    return max(written, key=lambda w: count[w])


def _as_written(key: str, name: str) -> str | None:
    """The words of `name` that spell `key`, as the store wrote them ("The
    Elder Scrolls" for "elder scrolls" in "The Elder Scrolls V: Skyrim")."""
    wanted = key.split()
    taken: list[str] = []
    got: list[str] = []
    for token in _MARKS.sub("", name).split():
        norm = normalize(token).split()
        if not norm:
            if got:
                taken.append(token)
            continue
        if not got and norm == ["the"] and wanted[:1] != ["the"]:
            taken.append(token)
            continue
        if got + norm != wanted[: len(got) + len(norm)]:
            return None
        got += norm
        taken.append(token)
        if got == wanted:
            return " ".join(taken).rstrip(":-–—,;. ") or None
    return None


@dataclass(slots=True)
class SeriesQuestion:
    """One uncertain membership, for the advisers: is this game of this
    series? With the series' other games to judge by."""

    game_id: int
    game_name: str
    year: int | None
    developer: str | None
    publisher: str | None
    series_id: int
    series_name: str
    p: float
    reason: str
    others: list[tuple[int, str, int | None]]


class SeriesBuilder:
    """Proposes the series from the games, their relations and the labels,
    and writes them over the previous proposals (`auto` rows only)."""

    def __init__(self, repo: Repo) -> None:
        self._repo = repo

    async def rebuild(self) -> int:
        """Every series proposed again; returns how many there are."""
        data = await self._repo.series_inputs()
        games = {
            int(r["game_id"]): SeriesGame(
                int(r["game_id"]),
                str(r["name"]),
                r["year"],
                r["developer"],
                r["publisher"],
                str(r["kind"] or "game"),
            )
            for r in data["games"]
        }
        relations = [(int(g), int(r), str(k)) for g, r, k in data["relations"]]
        labels = [(int(a), int(b), str(by)) for a, b, by in data["labels"]]
        proposals = propose(games, evidence(games, relations, labels))
        return await self._repo.write_series([(p.name, p.core, p.members) for p in proposals])


async def series_questions(
    repo: Repo, *, below_p: float = SURE_P, limit: int = 50
) -> list[SeriesQuestion]:
    """The memberships the linker is least sure of and nobody answered — a
    "game ↔ series" pair for the advisers to judge (the review pipeline asks
    them; this is only the data)."""
    rows = await repo.uncertain_series_memberships(below_p, limit)
    return [
        SeriesQuestion(
            game_id=int(r["game_id"]),
            game_name=str(r["game_name"]),
            year=r["year"],
            developer=r["developer"],
            publisher=r["publisher"],
            series_id=int(r["series_id"]),
            series_name=str(r["series_name"]),
            p=float(r["p"] or 0.0),
            reason=str(r["reason"] or ""),
            others=[(int(g), str(n), y) for g, n, y in r["others"]],
        )
        for r in rows
    ]


async def answer_series_question(
    repo: Repo, game_id: int, series_id: int, in_series: bool, decided_by: str
) -> None:
    """The advisers' answer to a `series_questions` pair: kept as theirs
    (`advisers`), never over the operator's."""
    await repo.set_series_member(
        game_id, series_id, in_series, source="advisers", decided_by=decided_by
    )
