"""Putting versions into games, and games into relations (#147; owner,
2026-10-11). `services/game_match.py` decides about pairs; this builds games.

Around the seed versions, every version that could be one of them (a telling
word of the name, a store's group or cross-gen set, an HLTB entry, a list) and
every version of the games those are already in are scored pair by pair. The
operator's labels (`match_decisions`) come first: "same" (a demo, a tool)
always joins, anything else never does. Then pairs join from the surest down,
but **never across a veto** — a pair the model is sure is not one game, or a
label saying so — so A~B and B~C no longer drag A and C together. Each group
keeps the game anchored on one of its versions, or gets a new one; the games
it came from are merged into it. Between groups, a sure remaster, remake,
compilation or VR version becomes a relation to the **earliest** original;
doubtful pairs go to the review list. All of it is rewritten for the versions
around the seeds, in one transaction.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bot.services.game_match import (
    DIFFER_SIGNS,
    JOIN_CLASSES,
    LINK_P,
    RELATIONS,
    VETO_P,
    Candidate,
    Verdict,
    block_key,
    candidate_year,
    compare,
    era,
    game_name,
    is_compilation,
    is_enhanced,
    is_extra,
    kind_of,
    model_name,
    plain_text,
    use_weights,
)
from bot.services.game_series import SeriesBuilder
from bot.services.hltb_match import normalize

if TYPE_CHECKING:
    from bot.db.repo import Repo

log = logging.getLogger(__name__)

# Labels that put two versions in one game; every other label keeps them apart.
# (An enhanced edition joins its game here, and may leave it after for a
# game of its own: `_split_enhanced`.)
JOINING = {
    "same",
    "edition",
    "enhanced_of",
    "demo_of",
    "tool_of",
    "mode_of",
    "extra_of",
    "pass_of",
}
# The roles that are a part of a game rather than the game: each names the
# version it is of, and vetoes nothing. An extra (a soundtrack, an artbook;
# owner, 2026-10-14) is one; an extra of no game is its own entry.
PARTS = ("demo", "tool", "mode", "extra", "pass")
# Labels that relate two games in no way: "other", and "another game of its
# series" (owner, 2026-10-11) — the same for building games, kept apart for
# what it tells about the model's mistakes.
NOT_RELATED = {"other", "series"}
# An enhanced edition split into a game of its own (`_split_enhanced`).
ENHANCED = "enhanced_of"
# A word in more versions' names than this tells nothing ("war", "star").
COMMON_WORD = 60
# One linker at a time in a process: two collections of one game's lists at
# once must not each build their own game.
_LOCK = asyncio.Lock()

Relations = dict[tuple[int, int, str], tuple[str, float | None]]


@dataclass(slots=True)
class LinkReport:
    games: dict[int, list[int]] = field(default_factory=dict)  # game → its versions
    relations: list[tuple[int, int, str]] = field(default_factory=list)
    review: list[tuple[int, int, str, float]] = field(default_factory=list)


class GameLinker:
    def __init__(self, repo: Repo) -> None:
        self._repo = repo

    async def link_title(self, platform: str, title_id: str) -> LinkReport:
        rows = await self._repo.match_rows()
        seeds = [
            int(r["version_id"])
            for r in rows
            if (r["platform"], r["title_id"]) == (platform, title_id)
        ]
        return await self._link(rows, seeds)

    async def link_versions(self, version_ids: list[int]) -> LinkReport:
        return await self._link(await self._repo.match_rows(), version_ids)

    async def link_all(self) -> LinkReport:
        rows = await self._repo.match_rows()
        return await self._link(rows, [int(r["version_id"]) for r in rows])

    async def _link(self, rows: list[dict], seed_ids: list[int]) -> LinkReport:
        async with _LOCK, self._repo.catalog_link_lock():
            return await self._link_locked(rows, seed_ids)

    async def _link_locked(self, rows: list[dict], seed_ids: list[int]) -> LinkReport:
        report = LinkReport()
        await load_weights(self._repo)
        candidates = {int(r["version_id"]): _candidate(r) for r in rows}
        seeds = [candidates[v] for v in seed_ids if v in candidates]
        if not seeds:
            return report
        index = _Index(list(candidates.values()))
        around = index.around(seeds)
        # Every version of the games these are in: a game is rebuilt whole.
        now_in = await self._repo.memberships(list(around))
        more = await self._repo.versions_of_games(list({m["game_id"] for m in now_in.values()}))
        around |= {v for v in more if v in candidates}
        now_in = await self._repo.memberships(list(around))
        members = [candidates[v] for v in around]
        await self._load_achievements(members, rows)
        labels = [
            lab
            for lab in await self._repo.decisions_among(list(around))
            if lab["version_id"] in around and lab["other_id"] in around
        ]

        pairs = index.pairs(members)
        verdicts: dict[tuple[int, int], Verdict] = await asyncio.to_thread(
            lambda: {(a, b): compare(candidates[a], candidates[b]) for a, b in pairs}
        )
        groups = _cluster(members, verdicts, labels)
        groups, enhanced = _split_enhanced(groups, candidates, labels, verdicts)
        group_of = {v: i for i, g in enumerate(groups) for v in g}
        surest: dict[int, float] = {}
        for (a, b), v in verdicts.items():
            if group_of[a] == group_of[b]:
                surest[a] = max(surest.get(a, 0.0), v.p_join)
                surest[b] = max(surest.get(b, 0.0), v.p_join)

        anchors = await self._repo.games_anchored_in(list(around))
        old_games = {int(m["game_id"]) for m in now_in.values()}
        assignment: dict[int, tuple[int, str, int | None, float | None]] = {}
        game_of: dict[int, int] = {}
        async with self._repo.transaction():
            for group in groups:
                cluster = [candidates[v] for v in group]
                games_here = sorted({anchors[v] for v in group if v in anchors})
                anchor = _anchor(cluster)
                if games_here:
                    target = games_here[0]
                    for other in games_here[1:]:
                        await self._repo.merge_game_into(other, target)
                else:
                    target = await self._repo.create_game(
                        game_name(cluster), anchor.year, anchor.version_id
                    )
                for version_id, (role, of) in _roles(cluster, labels, verdicts).items():
                    assignment[version_id] = (target, role, of, surest.get(version_id))
                    game_of[version_id] = target
                report.games[target] = sorted(group)
            await self._repo.write_members(assignment)

            relations = _relations(groups, game_of, verdicts, labels, candidates)
            for e, base in enhanced:
                g, r = game_of[next(iter(groups[e]))], game_of[next(iter(groups[base]))]
                relations[(g, r, ENHANCED)] = ("auto", None)
            # Named once the relations are known: a remaster, a remake, a VR
            # version, an enhanced edition or a compilation is called by its
            # own release.
            subjects = {g for g, _r, kind in relations if kind in (*RELATIONS, ENHANCED)}
            for group in groups:
                target = game_of[next(iter(group))]
                cluster = [candidates[v] for v in group]
                await self._repo.rename_game(
                    target, game_name(cluster, release=target in subjects), None, "auto"
                )
            touched = sorted(set(game_of.values()) | old_games)
            await self._repo.write_relations(
                touched,
                [(g, r, kind, source, p) for (g, r, kind), (source, p) in relations.items()],
            )
            report.relations = list(relations)
            await self._repo.set_game_kinds(_game_kinds(groups, game_of, candidates, relations))

            labelled = {frozenset((lab["version_id"], lab["other_id"])) for lab in labels}
            # Two games the operator already said something about are not
            # asked about again through another pair of their versions.
            decided = {
                frozenset((game_of[lab["version_id"]], game_of[lab["other_id"]]))
                for lab in labels
                if lab["version_id"] in game_of and lab["other_id"] in game_of
            }
            review = _review(verdicts, game_of, relations, labelled, decided)
            await self._repo.write_review(
                list(around),
                [
                    (v.subject, v.other, v.relation, v.p, v.probs, v.features, model_name())
                    for v in review
                ],
            )
            report.review = [(v.subject, v.other, v.relation, v.p) for v in review]
        await self._repo.drop_empty_games()
        await self._repo.refresh_game_facts(sorted(set(game_of.values())))
        # The game's HLTB entry, known for one release, for its others too.
        await spread_hltb(self._repo, sorted(set(game_of.values())))
        try:
            # Series follow the games: a rebuild may merge, split or relate
            # them. Proposed again whole (a few thousand games: cheap); a
            # failure leaves the last proposals and never fails the linking.
            await SeriesBuilder(self._repo).rebuild()
        except Exception:
            log.exception("proposing the series failed")
        return report

    async def _load_achievements(self, members: list[Candidate], rows: list[dict]) -> None:
        by_id = {int(r["version_id"]): r for r in rows}
        names = await self._repo.achievement_names_of(
            [c.list_key for c in members if c.list_key]  # type: ignore[misc]
        )
        for c in members:
            row = by_id[c.version_id]
            if c.list_key:
                found = names.get(c.list_key, [])
            elif row["store"] == "steam":
                # A Steam app nobody here has: its schema's names.
                found = (
                    await self._repo.payload(f"steam_schema:{row['product_id']}", "steam_schema")
                    or []
                )
            else:
                found = []
            c.achievements = frozenset(normalize(n) for n in found if n)


async def load_weights(repo: Repo) -> None:
    """Score with the fit the database holds as active, else the hand weights."""
    active = await repo.active_match_weights()
    use_weights(active[1] if active else None, active[0] if active else None)


async def load_candidates(repo: Repo, version_ids: list[int]) -> dict[int, Candidate]:
    """These versions as the model reads them, achievements' names loaded —
    for scoring a pair outside a linking run (fitting the weights), with the
    weights the linker would use."""
    await load_weights(repo)
    rows = await repo.match_rows()
    wanted = set(version_ids)
    candidates = {int(r["version_id"]): _candidate(r) for r in rows if r["version_id"] in wanted}
    await GameLinker(repo)._load_achievements(list(candidates.values()), rows)
    return candidates


class _Index:
    """Which versions could be which: a telling word of the cut name (one
    no more common than `COMMON_WORD`), a store's group or cross-gen set, an
    HLTB entry, an achievement list."""

    def __init__(self, candidates: list[Candidate]) -> None:
        self._by_key: dict[tuple, set[int]] = defaultdict(set)
        self._keys: dict[int, set[tuple]] = {}
        for c in candidates:
            keys: set[tuple] = {("w", w) for w in block_key(c)}
            if c.store_group:
                keys.add(("g", c.store, c.store_group))
            if c.cross_gen_set:
                keys.add(("x", c.cross_gen_set))
            keys |= {("h", h) for h in c.hltb_ids}
            if c.list_key:
                keys.add(("l", c.list_key))
            self._keys[c.version_id] = keys
            for k in keys:
                self._by_key[k].add(c.version_id)
        self._common = {
            k for k, vs in self._by_key.items() if k[0] == "w" and len(vs) > COMMON_WORD
        }

    def _telling(self, version_id: int) -> set[tuple]:
        return self._keys.get(version_id, set()) - self._common

    def around(self, seeds: list[Candidate]) -> set[int]:
        found = {s.version_id for s in seeds}
        for s in seeds:
            for k in self._telling(s.version_id):
                found |= self._by_key[k]
        return found

    def pairs(self, members: list[Candidate]) -> set[tuple[int, int]]:
        ids = {m.version_id for m in members}
        found: set[tuple[int, int]] = set()
        for m in members:
            for k in self._telling(m.version_id):
                for other in self._by_key[k] & ids:
                    if other != m.version_id:
                        found.add((min(m.version_id, other), max(m.version_id, other)))
        return found


def _cluster(
    members: list[Candidate],
    verdicts: dict[tuple[int, int], Verdict],
    labels: list[dict],
) -> list[set[int]]:
    """Groups of one game: the operator's joins first, then the model's from
    the surest down, never across a label or a veto."""
    group = {m.version_id: {m.version_id} for m in members}
    forbidden: dict[int, set[int]] = defaultdict(set)
    for lab in labels:
        if lab["relation"] not in JOINING:
            forbidden[lab["version_id"]].add(lab["other_id"])
            forbidden[lab["other_id"]].add(lab["version_id"])
    kinds = {m.version_id: kind_of(m) for m in members}
    for (a, b), v in verdicts.items():
        # A demo, a tool or a mode vetoes nothing: it is far from a port of
        # its game years later (Battlefield V's beta and its Steam release),
        # and that must not keep it out of the game its own pair joins it to.
        if kinds.get(a) in PARTS or kinds.get(b) in PARTS:
            continue
        # A version whose name was never learned knows too little to keep
        # two versions apart (the training audit, 2026-10-24: its wrong
        # year split Fall Guys and Among Us); it may still join.
        if "name_unknown" in v.features:
            continue
        if v.p_join < VETO_P and "one_list" not in v.features and _differ(v):
            forbidden[a].add(b)
            forbidden[b].add(a)

    def join(a: int, b: int, *, force: bool) -> None:
        ga, gb = group[a], group[b]
        if ga is gb:
            return
        if not force and any(forbidden[x] & gb for x in ga):
            return
        if len(ga) < len(gb):
            ga, gb = gb, ga
        ga |= gb
        for x in gb:
            group[x] = ga

    for lab in labels:
        if lab["relation"] in JOINING:
            join(lab["version_id"], lab["other_id"], force=True)
    for (a, b), v in sorted(verdicts.items(), key=lambda kv: -kv[1].p_join):
        if v.p_join < LINK_P:
            break
        join(a, b, force=False)
    unique: dict[int, set[int]] = {}
    for g in group.values():
        unique[id(g)] = g
    return list(unique.values())


def _split_enhanced(
    groups: list[set[int]],
    candidates: dict[int, Candidate],
    labels: list[dict],
    verdicts: dict[tuple[int, int], Verdict] | None = None,
) -> tuple[list[set[int]], list[tuple[int, int]]]:
    """An enhanced edition sold under a product of its own beside the plain
    game is a game of its own (owner, 2026-10-25): where one store sells
    both — the plain game and the GOTY, the Definitive, the Director's Cut —
    the group's enhanced versions leave it for a game of their own, related
    `enhanced_of` to it. Where no store sells both (Steam sells only the
    Complete Edition), the enhanced edition is the game there, and stays.
    Returns the groups and `(enhanced group, its game's group)` pairs."""
    said = {lab["version_id"] for lab in labels if lab["relation"] == "enhanced_of"}
    labelled = {frozenset((lab["version_id"], lab["other_id"])) for lab in labels}
    said |= set(_model_enhanced(verdicts or {}, labelled))
    # A version labelled a part (an add-on named "Special Edition Upgrade")
    # is no edition, whatever its name says.
    parts = {
        lab["version_id"]
        for lab in labels
        if lab["relation"] in ("demo_of", "tool_of", "mode_of", "extra_of", "pass_of")
    }
    out: list[set[int]] = []
    pairs: list[tuple[int, int]] = []
    for group in groups:
        cluster = [candidates[v] for v in group]
        enhanced = {
            c.version_id
            for c in cluster
            if c.version_id in said or (kind_of(c) == "edition" and c.version_id not in parts)
        }
        plain = [
            c for c in cluster if c.version_id not in enhanced | parts and kind_of(c) not in PARTS
        ]
        both = {c.store for c in plain} & {candidates[v].store for v in enhanced}
        if not enhanced or not plain or not (both - {"unknown"}):
            out.append(group)
            continue
        out.append(group - enhanced)
        out.append(set(enhanced))
        pairs.append((len(out) - 1, len(out) - 2))
    return out, pairs


def _model_enhanced(
    verdicts: dict[tuple[int, int], Verdict], labelled: set[frozenset[int]]
) -> dict[int, int]:
    """The model's sure enhanced editions, each with the version it enhances
    (the surest): what no label says otherwise of."""
    found: dict[int, tuple[int, float]] = {}
    for v in verdicts.values():
        if v.state != "linked" or v.relation != ENHANCED:
            continue
        if frozenset((v.subject, v.other)) in labelled:
            continue
        if v.subject not in found or found[v.subject][1] < v.p:
            found[v.subject] = (v.other, v.p)
    return {e: of for e, (of, _p) in found.items()}


def _differ(v: Verdict) -> bool:
    """A sign the two versions are not one game: one of `DIFFER_SIGNS`, or
    the model's likeliest answer is a relation of its own — a remaster, a
    remake, a compilation, a VR version is another game (owner,
    2026-10-24: BioShock Remastered is not BioShock)."""
    if not DIFFER_SIGNS.isdisjoint(v.features):
        return True
    return max(v.probs, key=v.probs.__getitem__, default="other") in RELATIONS


def _anchor(cluster: list[Candidate]) -> Candidate:
    """The version a game is anchored on: its earliest that is the game
    itself (no demo, no tool, no mode), the first one known on a tie."""
    plain = [c for c in cluster if kind_of(c) not in PARTS] or cluster
    return min(plain, key=lambda c: (era(c) or 9999, c.version_id))


def _roles(
    cluster: list[Candidate],
    labels: list[dict],
    verdicts: dict[tuple[int, int], Verdict] | None = None,
) -> dict[int, tuple[str, int | None]]:
    """Each version's role in its game, and for a demo, a tool or a mode the
    version it is of (owner, 2026-10-09): the one on the same console, else the same
    store, else any — the one whose name opens it first."""
    ids = {c.version_id for c in cluster}
    told = {
        lab["version_id"]: (lab["relation"], lab["other_id"])
        for lab in labels
        if lab["version_id"] in ids and lab["other_id"] in ids
    }
    labelled = {frozenset((lab["version_id"], lab["other_id"])) for lab in labels}
    for e, of in _model_enhanced(verdicts or {}, labelled).items():
        if e in ids and of in ids and e not in told:
            told[e] = (ENHANCED, of)
    games = [c for c in cluster if kind_of(c) not in PARTS]
    roles: dict[int, tuple[str, int | None]] = {}
    for c in cluster:
        relation, of = told.get(c.version_id, (None, None))
        if relation in ("demo_of", "tool_of", "mode_of", "extra_of", "pass_of", "enhanced_of"):
            roles[c.version_id] = (str(relation)[: -len("_of")], of)
            continue
        kind = kind_of(c)
        parents = [g for g in games if g.version_id != c.version_id]
        if kind in PARTS and parents:

            def fit(v: Candidate, d: Candidate = c) -> tuple[int, int, int, int]:
                return (
                    1 if v.console == d.console else 0,
                    1 if v.store == d.store else 0,
                    1 if _opens(v, d) else 0,
                    -(v.year or 9999),
                )

            roles[c.version_id] = (kind, max(parents, key=fit).version_id)
        elif kind == "edition" and (plain := [g for g in parents if not is_enhanced(g)]):
            # An enhanced edition (owner, 2026-10-24: they are many): a
            # product of its own that is the game made more of — GOTY,
            # Definitive, a Director's Cut — kept in the game and marked, of
            # the plain version it enhances (the earliest). A remaster is not
            # one: it is a game of its own.
            roles[c.version_id] = (
                "enhanced",
                min(plain, key=lambda g: (era(g) or 9999, g.version_id)).version_id,
            )
        else:
            roles[c.version_id] = ("version", None)
    # A PC version of no known store only says "it is on PC" (owner,
    # 2026-10-12): once the game has a PC version in a known store (xbox pc,
    # Steam; later EGS, GOG) it is covered — kept in its game, so it still
    # draws its namesake in, but shown nowhere.
    if any(_known_pc(c) for c in cluster):
        for c in cluster:
            if c.store == "unknown" and roles[c.version_id] == ("version", None):
                roles[c.version_id] = ("covered", None)
    return roles


def _known_pc(c: Candidate) -> bool:
    """A PC version in a store we know: Steam's own, or a PC product of a
    store other than "unknown"."""
    return c.console == "steam" or (c.console == "pc" and c.store not in ("unknown", "list"))


def _relations(
    groups: list[set[int]],
    game_of: dict[int, int],
    verdicts: dict[tuple[int, int], Verdict],
    labels: list[dict],
    candidates: dict[int, Candidate],
) -> Relations:
    """Relations between games: the operator's labels, then the model's sure
    ones; a remaster, remake or VR version points at the **earliest** original
    (owner, 2026-10-11: no chains), a compilation at each of its parts."""
    edges: Relations = {}
    for v in verdicts.values():
        if v.state != "linked" or v.relation not in RELATIONS:
            continue
        g, r = game_of.get(v.subject), game_of.get(v.other)
        if g is None or r is None or g == r:
            continue
        key = (g, r, v.relation)
        if key not in edges or (edges[key][1] or 0.0) < v.p:
            edges[key] = ("auto", v.p)
    for lab in labels:
        # "Not one game, and not related" between any two of their versions:
        # nothing the model found between these two games stands.
        g, r = game_of.get(lab["version_id"]), game_of.get(lab["other_id"])
        if lab["relation"] in NOT_RELATED and g is not None and r is not None and g != r:
            for kind in RELATIONS:
                edges.pop((g, r, kind), None)
                edges.pop((r, g, kind), None)
    for lab in labels:
        if lab["relation"] not in RELATIONS:
            continue
        g, r = game_of.get(lab["version_id"]), game_of.get(lab["other_id"])
        if g is None or r is None or g == r:
            continue
        # The operator's word stands over the model's on this pair of games.
        for kind in RELATIONS:
            edges.pop((g, r, kind), None)
            edges.pop((r, g, kind), None)
        edges[(g, r, lab["relation"])] = ("manual", None)

    # A game that contains two or more is a compilation: its "remaster of" a
    # part is containing it (Mass Effect Legendary Edition → ME1, ME2, ME3).
    contains: dict[int, set[int]] = defaultdict(set)
    for g, r, kind in edges:
        if kind == "contains":
            contains[g].add(r)
    for g, r, kind in list(edges):
        if kind == "remaster_of" and len(contains[g]) >= 2 and edges[(g, r, kind)][0] == "auto":
            edges[(g, r, "contains")] = edges.pop((g, r, kind))

    game_era: dict[int, int] = {}
    for group in groups:
        g = game_of.get(next(iter(group)))
        if g is not None:
            game_era[g] = min(era(candidates[v]) or 9999 for v in group)

    def root(game: int, seen: set[int]) -> int:
        """Follow remaster links back to the earliest original. A remake is
        an original of its own (owner, 2026-10-12): a remaster of it points
        at it — Gears of War: Reloaded at Ultimate Edition, a remake of
        Gears of War."""
        for g, r, kind in edges:
            if g == game and kind == "remaster_of" and r not in seen:
                return root(r, seen | {r})
        return game

    result: Relations = {}
    for kind in ("remaster_of", "remake_of", "vr_of"):
        by_subject: dict[int, list[tuple[int, tuple[str, float | None]]]] = defaultdict(list)
        for (g, r, k), value in edges.items():
            if k == kind:
                by_subject[g].append((r, value))
        for g, targets in by_subject.items():
            pick = [t for t in targets if t[1][0] == "manual"] or targets
            r, value = min(pick, key=lambda t: (game_era.get(t[0], 9999), t[0]))
            original = r if kind == "vr_of" else root(r, {g, r})
            if original != g:
                result[(g, original, kind)] = value
    for (g, r, k), value in edges.items():
        if k == "contains":
            result[(g, r, k)] = value
    # One relation per pair of games (Brothers was both a remaster and a
    # remake): the operator's, else the surest.
    best: dict[frozenset[int], tuple[int, int, str]] = {}
    for key, (source, p) in result.items():
        pair = frozenset(key[:2])
        rank = (source == "manual", p or 0.0)
        kept = best.get(pair)
        if kept is None or rank > (result[kept][0] == "manual", result[kept][1] or 0.0):
            best[pair] = key
    return {key: result[key] for key in best.values()}


def _game_kinds(
    groups: list[set[int]],
    game_of: dict[int, int],
    candidates: dict[int, Candidate],
    relations: Relations,
) -> dict[int, str]:
    """What each game is (owner, 2026-10-12): an extra when every version of
    it that is the game itself is one (a soundtrack, an app); a compilation
    when one of them says so (its name, its HLTB entry) or it holds two games
    or more; else a game."""
    holds: dict[int, int] = defaultdict(int)
    for g, _r, kind in relations:
        if kind == "contains":
            holds[g] += 1
    kinds: dict[int, str] = {}
    for group in groups:
        game = game_of.get(next(iter(group)))
        if game is None:
            continue
        cluster = [candidates[v] for v in group]
        plain = [c for c in cluster if kind_of(c) not in PARTS] or cluster
        if all(is_extra(c) for c in plain):
            kinds[game] = "extra"
        elif holds[game] >= 2 or any(is_compilation(c) for c in plain):
            kinds[game] = "compilation"
        else:
            kinds[game] = "game"
    return kinds


def _review(
    verdicts: dict[tuple[int, int], Verdict],
    game_of: dict[int, int],
    relations: Relations,
    labelled: set[frozenset[int]],
    decided: set[frozenset[int]],
) -> list[Verdict]:
    """The doubtful pairs: one per pair of games (the surest), none the
    operator already answered, none whose games already relate."""
    related = {frozenset((g, r)) for g, r, _ in relations}
    best: dict[frozenset[int], Verdict] = {}
    for (a, b), v in verdicts.items():
        if v.state != "review" or frozenset((a, b)) in labelled:
            continue
        ga, gb = game_of.get(a), game_of.get(b)
        if ga is None or gb is None or (ga == gb and v.relation in JOIN_CLASSES):
            continue
        key = frozenset((ga, gb))
        if ga != gb and (key in related or key in decided):
            continue
        if key not in best or best[key].p < v.p:
            best[key] = v
    return sorted(best.values(), key=lambda v: -v.p)


def _opens(game: Candidate, demo: Candidate) -> bool:
    words = [normalize(n).split() for n in demo.names]
    return any(c and any(w[: len(c.split())] == c.split() for w in words) for c in game.cores)


# Words a store adds to a genre's name that say nothing of it.
GENRE_NOISE = frozenset({"and", "games", "game", "other"})


def _genres(raw: object) -> frozenset[str]:
    """A version's genres as words ("Action & adventure" is action and
    adventure), so two stores' words for one genre meet."""
    try:
        found = json.loads(str(raw or "[]"))
    except ValueError:
        return frozenset()
    if not isinstance(found, list):
        return frozenset()
    return frozenset(w for g in found for w in normalize(str(g)).split() if w not in GENRE_NOISE)


def _candidate(row: dict) -> Candidate:
    # A stand-in whose name was never learned is named by its id
    # ("1881441063"): no name at all, for the matcher (the training audit,
    # 2026-10-24: compared as a name it cost "same" some 8 log-odds).
    ids = {str(row["product_id"]), str(row.get("title_id") or "")}
    names = tuple(
        dict.fromkeys(
            str(n)
            for n in (row["name"], row["list_name_en"], row["list_name"])
            if n
            and normalize(str(n))  # "?" (a name lost on production) is none
            and str(n).strip() not in ids
        )
    )
    return Candidate(
        version_id=int(row["version_id"]),
        store=row["store"],
        product_id=str(row["product_id"]),
        console=row["console"],
        names=names,
        kind=row["kind"],
        developer=row["developer"],
        publisher=row["publisher"],
        year=candidate_year(row),
        store_group=row["store_group"],
        cross_gen_set=row.get("cross_gen_set"),
        hltb_ids=frozenset(
            int(h) for h in str(row["hltb_ids"] or "").split(",") if h.strip().isdigit()
        ),
        list_key=(row["platform"], row["title_id"])
        if row["platform"] and row["title_id"]
        else None,
        stand_in=bool(row["stand_in"]),
        hltb_types=frozenset(
            t.strip() for t in str(row.get("hltb_types") or "").split(",") if t.strip()
        ),
        genres=_genres(row.get("genres")),
        blurb=plain_text(row.get("description_en")),
        hltb_blurb=plain_text(row.get("hltb_summary")),
    )


async def spread_hltb(repo: Repo, game_ids: list[int] | None = None) -> int:
    """A game's HowLongToBeat entry, known for one of its releases, for its
    other releases too (owner, 2026-10-16: the PC version is surely linked and
    the entry lists the other platforms — the PS4 and PS5 versions are that
    entry). Its releases are one work, so one entry times them all; a release
    takes it only when HLTB lists its platform, it has no link of its own (nor
    a refusal), and it is not a demo, a tool, a mode or an extra. A game whose
    releases are linked to more than one game entry is left alone: which one
    is the game's is not ours to guess. The number of links made."""
    from bot.db.repo._sql import SPREAD_HLTB_SCORE
    from bot.services.game_match import is_part
    from bot.services.hltb_match import NOT_A_GAME
    from bot.services.hltb_platforms import hltb_platform

    by_game: dict[int, list[dict]] = {}
    for row in await repo.hltb_spread_rows(game_ids):
        by_game.setdefault(int(row["game_id"]), []).append(row)
    made = 0
    for rows in by_game.values():
        linked = [
            r
            for r in rows
            if r["hltb_id"] is not None
            and r["source"] != "rejected"
            and (r["game_type"] or "game") not in NOT_A_GAME
        ]
        entries = {int(r["hltb_id"]) for r in linked}
        if len(entries) != 1:
            continue
        hltb_id = entries.pop()
        platforms = set(str(linked[0]["entry_platforms"] or "").split("|")) - {""}
        seen: set[int] = set()
        for r in rows:
            vid = int(r["version_id"])
            if vid in seen:
                continue
            seen.add(vid)
            if any(int(x["version_id"]) == vid and x["hltb_id"] is not None for x in rows):
                continue  # linked already, or refused
            if is_part(r["kind"], r["role"], [str(n) for n in (r["name"], r["name_ru"]) if n]):
                continue
            platform = hltb_platform(r["console"])
            if platform is None or (platforms and platform not in platforms):
                continue
            await repo.link_version_hltb(vid, hltb_id, score=SPREAD_HLTB_SCORE)
            made += 1
    return made


async def link_and_spread(repo: Repo, version_ids: list[int]) -> LinkReport:
    """These versions relinked with their neighbourhood, and HLTB spread over
    the games they are in now — the linker's own step, which the octopus calls
    once per round of a game's assembly (#215), never inside a collection."""
    report = await GameLinker(repo).link_versions(version_ids)
    if report.games:
        # Only these games: `None` would mean every game.
        await spread_hltb(repo, sorted(report.games))
    return report
