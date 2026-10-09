"""Putting versions into games (#147, stage 3): `services/game_match.py`
decides, this reads and writes.

Run around one achievement list after it is collected: its versions and the
versions that could be them (sharing the first word of a cut name, a store
group or an HLTB entry) are compared, linked pairs make one game, doubtful
ones go to the review list. Only the matcher's own (`auto`) rows are ever
rewritten: a manual link stays, and a manual rejection keeps the version out
of that game for good.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bot.services.game_match import Candidate, block_key, compare, game_name, kind_of
from bot.services.hltb_match import normalize

if TYPE_CHECKING:
    from bot.db.repo import Repo

log = logging.getLogger(__name__)


@dataclass(slots=True)
class LinkReport:
    games: dict[int, list[int]] = field(default_factory=dict)  # game → its versions
    review: list[tuple[int, int, list[str]]] = field(default_factory=list)  # version, game, why


class GameLinker:
    def __init__(self, repo: Repo) -> None:
        self._repo = repo

    async def link_title(self, platform: str, title_id: str) -> LinkReport:
        rows = await self._repo.match_rows()
        seeds = [r for r in rows if r["platform"] == platform and r["title_id"] == title_id]
        return await self._link(rows, seeds)

    async def link_versions(self, version_ids: list[int]) -> LinkReport:
        rows = await self._repo.match_rows()
        wanted = set(version_ids)
        return await self._link(rows, [r for r in rows if r["version_id"] in wanted])

    async def _link(self, rows: list[dict], seeds: list[dict]) -> LinkReport:
        report = LinkReport()
        if not seeds:
            return report
        candidates = {r["version_id"]: _candidate(r) for r in rows}
        around = self._around([candidates[s["version_id"]] for s in seeds], candidates)
        for candidate in around:
            row = next(r for r in rows if r["version_id"] == candidate.version_id)
            if row["platform"] and row["title_id"]:
                names = await self._repo.achievement_names(row["platform"], row["title_id"])
                candidate.achievements = frozenset(normalize(n) for n in names if n)

        links = await self._repo.links_of([c.version_id for c in around])
        manual = {
            (link["version_id"], link["game_id"]): link
            for link in links
            if link["source"] == "manual"
        }
        rejected = {key for key, link in manual.items() if link["state"] == "rejected"}
        game_of: dict[int, int] = {}
        for link in links:
            if link["state"] == "linked" and (
                link["source"] == "manual" or link["version_id"] not in game_of
            ):
                game_of[link["version_id"]] = link["game_id"]
        pinned = {vid for (vid, _gid), link in manual.items() if link["state"] == "linked"}

        # Linked pairs make groups; doubtful pairs are kept for the review list.
        parent = {c.version_id: c.version_id for c in around}

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        verdicts = {}
        for i, a in enumerate(around):
            for b in around[i + 1 :]:
                verdict = compare(a, b)
                verdicts[(a.version_id, b.version_id)] = verdict
                if verdict.state == "linked":
                    parent[find(a.version_id)] = find(b.version_id)

        groups: dict[int, list[Candidate]] = {}
        for c in around:
            groups.setdefault(find(c.version_id), []).append(c)

        for members in groups.values():
            target = self._target(members, game_of, pinned)
            if target is None:
                year = min((m.year for m in members if m.year), default=None)
                target = await self._repo.create_game(game_name(members), year)
            for member in members:
                vid = member.version_id
                if vid in pinned:
                    continue
                if (vid, target) in rejected:
                    # Decided by hand: not this game. It keeps (or gets) one of its own.
                    own = game_of.get(vid)
                    if own is None or own == target:
                        own = await self._repo.create_game(game_name([member]), member.year)
                    await self._repo.set_link(
                        vid, own, kind=kind_of(member), state="linked", source="auto"
                    )
                    game_of[vid] = own
                    continue
                await self._repo.set_link(
                    vid, target, kind=kind_of(member), state="linked", source="auto", score=1.0
                )
                await self._repo.drop_auto_links(vid, target, "linked")
                game_of[vid] = target
                report.games.setdefault(target, []).append(vid)

        # The review list: a doubtful pair across two games, filed on the later
        # version. The matcher's earlier review rows around here are redrawn.
        for c in around:
            if c.version_id not in pinned:
                await self._repo.drop_auto_links(c.version_id, None, "review")
        # One review row per version: against the game it is most like. It is
        # filed on the side less is known about (no year, a stand-in, the later).
        best: dict[int, tuple[float, int, list[str]]] = {}
        for (x, y), verdict in verdicts.items():
            if verdict.state != "review" or game_of.get(x) == game_of.get(y):
                continue
            subject, other = _weaker(candidates[x], candidates[y])
            game = game_of.get(other.version_id)
            if (
                game is None
                or subject.version_id in pinned
                or (subject.version_id, game) in rejected
            ):
                continue
            if verdict.score > best.get(subject.version_id, (-1.0, 0, []))[0]:
                best[subject.version_id] = (verdict.score, game, verdict.reasons)
        for version_id, (score, game, reasons) in best.items():
            await self._repo.set_link(
                version_id,
                game,
                kind=kind_of(candidates[version_id]),
                state="review",
                source="auto",
                score=score,
                reasons=reasons,
            )
            report.review.append((version_id, game, reasons))
        await self._repo.drop_empty_games()
        return report

    @staticmethod
    def _around(seeds: list[Candidate], candidates: dict[int, Candidate]) -> list[Candidate]:
        """The seeds and every version that could be one of them."""
        keys = set().union(*(block_key(s) for s in seeds))
        groups = {(s.store, s.store_group) for s in seeds if s.store_group}
        hltb = frozenset().union(*(s.hltb_ids for s in seeds))
        found = {s.version_id: s for s in seeds}
        for c in candidates.values():
            if c.version_id in found:
                continue
            if block_key(c) & keys or (c.store, c.store_group) in groups or c.hltb_ids & hltb:
                found[c.version_id] = c
        return list(found.values())

    @staticmethod
    def _target(members: list[Candidate], game_of: dict[int, int], pinned: set[int]) -> int | None:
        """The game a group joins: one a member is manually in, else the
        oldest game any member already is in, else none (a new one)."""
        manual = [game_of[m.version_id] for m in members if m.version_id in pinned]
        if manual:
            return manual[0]
        known = [game_of[m.version_id] for m in members if m.version_id in game_of]
        return min(known) if known else None


def _weaker(a: Candidate, b: Candidate) -> tuple[Candidate, Candidate]:
    """(the version a review is filed on, the other): the one without a year,
    else a stand-in for a list no store described, else the later one."""

    def known(c: Candidate) -> tuple[int, int, int]:
        return (1 if c.year else 0, 0 if c.store == "list" else 1, -(c.year or 0))

    return (a, b) if known(a) <= known(b) else (b, a)


def _candidate(row: dict) -> Candidate:
    names = tuple(
        dict.fromkeys(
            str(n)
            for n in (row["name"], row["list_name_en"], row["list_name"])
            if n and str(n).strip()
        )
    )
    year = row["release_date"][:4] if row["release_date"] else None
    return Candidate(
        version_id=int(row["version_id"]),
        store=row["store"],
        product_id=str(row["product_id"]),
        console=row["console"],
        names=names,
        kind=row["kind"],
        developer=row["developer"],
        publisher=row["publisher"],
        year=int(year) if year and year.isdigit() else None,
        store_group=row["store_group"],
        hltb_ids=frozenset(
            int(h) for h in str(row["hltb_ids"] or "").split(",") if h.strip().isdigit()
        ),
    )
