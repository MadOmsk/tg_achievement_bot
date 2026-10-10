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
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bot.services.game_match import (
    ACHIEVEMENTS_MIN,
    ACHIEVEMENTS_SAME,
    FAR_YEARS,
    Candidate,
    block_key,
    compare,
    era,
    game_name,
    kind_of,
)
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
            elif row["store"] == "steam":
                # A Steam app nobody here has: its schema's names (stage 4).
                names = (
                    await self._repo.payload(f"steam_schema:{row['product_id']}", "steam_schema")
                    or []
                )
            else:
                names = []
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

        touched: set[int] = set(game_of.values())
        groups: dict[int, list[Candidate]] = {}
        for c in around:
            groups.setdefault(find(c.version_id), []).append(c)

        for members in groups.values():
            target = self._target(members, game_of, pinned)
            if target is None:
                year = min((m.year for m in members if m.year), default=None)
                target = await self._repo.create_game(game_name(members), year)
            else:
                # The matcher's own name follows what the game turned out to
                # hold; a name the operator gave stays.
                await self._repo.rename_game(target, game_name(members), None, "auto")
            kinds = _kinds(members)
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
                    vid, target, kind=kinds[vid], state="linked", source="auto", score=1.0
                )
                await self._repo.drop_auto_links(vid, target, "linked")
                game_of[vid] = target
                report.games.setdefault(target, []).append(vid)
            await self._link_demos(members, pinned)
            touched.add(target)

        # The review list: a doubtful pair across two games, filed on the later
        # version. The matcher's earlier review rows around here are redrawn.
        for c in around:
            if c.version_id not in pinned:
                await self._repo.drop_auto_links(c.version_id, None, "review")
        # One review row per version: against the game it is most like. It is
        # filed on the side less is known about (no year, a stand-in, the later).
        best: dict[int, tuple[float, int, list[str], str | None]] = {}
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
            if verdict.score > best.get(subject.version_id, (-1.0, 0, [], None))[0]:
                best[subject.version_id] = (verdict.score, game, verdict.reasons, verdict.kind)
        for version_id, (score, game, reasons, hint) in best.items():
            await self._repo.set_link(
                version_id,
                game,
                kind=hint or kind_of(candidates[version_id]),
                state="review",
                source="auto",
                score=score,
                reasons=reasons,
            )
            report.review.append((version_id, game, reasons))
        await self._repo.drop_empty_games()
        await self._repo.refresh_game_facts(sorted(touched | set(game_of.values())))
        return report

    async def _link_demos(self, members: list[Candidate], pinned: set[int]) -> None:
        """A demo, and a tool (a Creation Kit), belongs to one version (owner,
        2026-10-09, 2026-10-10): the one of its game on the same console,
        else on the same store, else any — the version whose name opens its
        name first."""
        games = [m for m in members if kind_of(m) not in ("demo", "tool")]
        for demo in (m for m in members if kind_of(m) in ("demo", "tool")):
            if not games or demo.version_id in pinned:
                continue

            def fit(v: Candidate, demo: Candidate = demo) -> tuple[int, int, int, int]:
                return (
                    1 if v.console == demo.console else 0,
                    1 if v.store == demo.store else 0,
                    1 if _opens(v, demo) else 0,
                    -(v.year or 9999),
                )

            parent = max(games, key=fit)
            link = "tool_of" if kind_of(demo) == "tool" else "demo_of"
            await self._repo.set_version_link(demo.version_id, parent.version_id, link, "auto")

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
        return (1 if c.year else 0, 0 if c.stand_in else 1, -(c.year or 0))

    return (a, b) if known(a) <= known(b) else (b, a)


def _kinds(members: list[Candidate]) -> dict[int, str]:
    """How each version belongs to its game. The name says it first; but an
    'edition' with an achievement list of its own, later than the game's
    first list, is a remaster (Gears of War → Ultimate Edition)."""
    kinds = {m.version_id: kind_of(m) for m in members}
    listed = [m for m in members if len(m.achievements) >= ACHIEVEMENTS_MIN and _era(m)]
    base = min(
        (m for m in listed if kinds[m.version_id] not in ("demo", "tool")),
        key=_era,
        default=None,
    )
    if base is None:
        return kinds
    for m in listed:
        if m is base or kinds[m.version_id] not in ("version", "edition"):
            continue
        if m.list_key == base.list_key or _era(m) <= _era(base):
            continue
        if _era(m) - _era(base) >= FAR_YEARS and set(m.cores).isdisjoint(base.cores):
            # Years later, under a name of its own, with a list of its own:
            # the game made again (Gears of War → Gears of War: Reloaded).
            kinds[m.version_id] = "remaster"
            continue
        shared = len(m.achievements & base.achievements) / min(
            len(m.achievements), len(base.achievements)
        )
        if shared < ACHIEVEMENTS_SAME:
            kinds[m.version_id] = "remaster"
    # One release under one name is one kind on every store: "Ultimate Edition
    # for Windows 10" is the remaster its console namesakes are.
    by_release: dict[str, set[str]] = {}
    for m in members:
        for name in m.names:
            by_release.setdefault(_release_name(name), set()).add(kinds[m.version_id])
    for m in members:
        if kinds[m.version_id] in ("version", "edition") and any(
            "remaster" in by_release.get(_release_name(n), set()) for n in m.names
        ):
            kinds[m.version_id] = "remaster"
    return kinds


_PLATFORM_TAIL = re.compile(
    r"[\s:\-–—]*\b(?:for\s+)?(?:windows(?:\s*10|\s*11)?|pc"
    r"|xbox(?:\s+one|\s+series(?:\s+x\s*s)?)?|ps[345]|playstation\s*[345]?)\s*$",
    re.IGNORECASE,
)


def _release_name(name: str) -> str:
    """A version's name without the platform it names."""
    return normalize(_PLATFORM_TAIL.sub("", name).strip())


_era = era


def _opens(game: Candidate, demo: Candidate) -> bool:
    words = [normalize(n).split() for n in demo.names]
    return any(c and any(w[: len(c.split())] == c.split() for w in words) for c in game.cores)


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
        list_key=(row["platform"], row["title_id"])
        if row["platform"] and row["title_id"]
        else None,
        stand_in=bool(row["stand_in"]),
    )
