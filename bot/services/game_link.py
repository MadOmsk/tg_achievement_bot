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
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bot.services.game_match import (
    LINK_P,
    MODEL,
    RELATIONS,
    VETO_P,
    Candidate,
    Verdict,
    block_key,
    candidate_year,
    compare,
    era,
    game_name,
    kind_of,
    release_name,
)
from bot.services.hltb_match import normalize

if TYPE_CHECKING:
    from bot.db.repo import Repo

log = logging.getLogger(__name__)

# Labels that put two versions in one game; every other label keeps them apart.
JOINING = {"same", "edition", "demo_of", "tool_of"}
# Labels that relate two games in no way: "other", and "another game of its
# series" (owner, 2026-10-11) — the same for building games, kept apart for
# what it tells about the model's mistakes.
NOT_RELATED = {"other", "series"}
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
        async with _LOCK:
            return await self._link_locked(rows, seed_ids)

    async def _link_locked(self, rows: list[dict], seed_ids: list[int]) -> LinkReport:
        report = LinkReport()
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
        group_of = {v: i for i, g in enumerate(groups) for v in g}
        surest: dict[int, float] = {}
        for (a, b), v in verdicts.items():
            if group_of[a] == group_of[b]:
                surest[a] = max(surest.get(a, 0.0), v.p_same)
                surest[b] = max(surest.get(b, 0.0), v.p_same)

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
                await self._repo.rename_game(target, game_name(cluster), None, "auto")
                for version_id, (role, of) in _roles(cluster, labels).items():
                    assignment[version_id] = (target, role, of, surest.get(version_id))
                    game_of[version_id] = target
                report.games[target] = sorted(group)
            await self._repo.write_members(assignment)

            relations = _relations(groups, game_of, verdicts, labels, candidates)
            await self._name_releases(relations, groups, game_of, candidates)
            touched = sorted(set(game_of.values()) | old_games)
            await self._repo.write_relations(
                touched,
                [(g, r, kind, source, p) for (g, r, kind), (source, p) in relations.items()],
            )
            report.relations = list(relations)

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
                [(v.subject, v.other, v.relation, v.p, v.probs, v.features, MODEL) for v in review],
            )
            report.review = [(v.subject, v.other, v.relation, v.p) for v in review]
        await self._repo.drop_empty_games()
        await self._repo.refresh_game_facts(sorted(set(game_of.values())))
        return report

    async def _name_releases(
        self,
        relations: Relations,
        groups: list[set[int]],
        game_of: dict[int, int],
        candidates: dict[int, Candidate],
    ) -> None:
        """A remaster, remake or VR version cut down to its original's name
        ("Gears of War") is called by its own release name ("Gears of War:
        Ultimate Edition")."""
        clusters = {game_of[next(iter(g))]: [candidates[v] for v in g] for g in groups}
        names = await self._repo.game_names(
            list({g for g, _, _ in relations} | {r for _, r, _ in relations})
        )
        for g, r, kind in relations:
            if kind == "contains" or g not in clusters:
                continue
            mine, theirs = names.get(g), names.get(r)
            if not mine or not theirs or mine[1] != "auto":
                continue
            if normalize(mine[0]) == normalize(theirs[0]):
                anchor = _anchor(clusters[g])
                if anchor.names:
                    await self._repo.rename_game(g, release_name(anchor.names[0]), None, "auto")

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


async def load_candidates(repo: Repo, version_ids: list[int]) -> dict[int, Candidate]:
    """These versions as the model reads them, achievements' names loaded —
    for scoring a pair outside a linking run (fitting the weights)."""
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
        # A demo or a tool vetoes nothing: it is far from a port of its game
        # years later (Battlefield V's beta and its Steam release), and that
        # must not keep it out of the game its own pair joins it to.
        if kinds.get(a) in ("demo", "tool") or kinds.get(b) in ("demo", "tool"):
            continue
        if v.p_same < VETO_P and "one_list" not in v.features:
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
    for (a, b), v in sorted(verdicts.items(), key=lambda kv: -kv[1].p_same):
        if v.p_same < LINK_P:
            break
        join(a, b, force=False)
    unique: dict[int, set[int]] = {}
    for g in group.values():
        unique[id(g)] = g
    return list(unique.values())


def _anchor(cluster: list[Candidate]) -> Candidate:
    """The version a game is anchored on: its earliest that is the game
    itself (no demo, no tool), the first one known on a tie."""
    plain = [c for c in cluster if kind_of(c) not in ("demo", "tool")] or cluster
    return min(plain, key=lambda c: (era(c) or 9999, c.version_id))


def _roles(cluster: list[Candidate], labels: list[dict]) -> dict[int, tuple[str, int | None]]:
    """Each version's role in its game, and for a demo or a tool the version
    it is of (owner, 2026-10-09): the one on the same console, else the same
    store, else any — the one whose name opens it first."""
    ids = {c.version_id for c in cluster}
    told = {
        lab["version_id"]: (lab["relation"], lab["other_id"])
        for lab in labels
        if lab["version_id"] in ids and lab["other_id"] in ids
    }
    games = [c for c in cluster if kind_of(c) not in ("demo", "tool")]
    roles: dict[int, tuple[str, int | None]] = {}
    for c in cluster:
        relation, of = told.get(c.version_id, (None, None))
        if relation in ("demo_of", "tool_of"):
            roles[c.version_id] = (str(relation)[: -len("_of")], of)
            continue
        kind = kind_of(c)
        parents = [g for g in games if g.version_id != c.version_id]
        if kind in ("demo", "tool") and parents:

            def fit(v: Candidate, d: Candidate = c) -> tuple[int, int, int, int]:
                return (
                    1 if v.console == d.console else 0,
                    1 if v.store == d.store else 0,
                    1 if _opens(v, d) else 0,
                    -(v.year or 9999),
                )

            roles[c.version_id] = (kind, max(parents, key=fit).version_id)
        else:
            # No "edition" role (owner, 2026-10-11): an edition is a pack the
            # store sells around the same version (`editions`), and a product
            # of its own is the game, or a remaster.
            roles[c.version_id] = ("version", None)
    return roles


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
        """Follow remaster/remake links back to the earliest original."""
        for g, r, kind in edges:
            if g == game and kind in ("remaster_of", "remake_of") and r not in seen:
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
        if ga is None or gb is None or (ga == gb and v.relation == "same"):
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


def _candidate(row: dict) -> Candidate:
    names = tuple(
        dict.fromkeys(
            str(n)
            for n in (row["name"], row["list_name_en"], row["list_name"])
            if n and normalize(str(n))  # "?" (a name lost on production) is none
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
    )
