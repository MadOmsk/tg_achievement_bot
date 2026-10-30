"""The advisers' review of the games matcher (#147; owner, 2026-10-12).

The model scores the candidate pairs and decides alone where it is sure; the
pairs it is not sure of — and a seeded sample of those it is (`--audit`) —
go to two advisers, Claude and Gemini, who answer them on their own. Where
both agree the label is written (`decided_by` `model+claude+gemini` when the
model said the same, else `claude+gemini`); where they do not, nothing is
written and the pair is the operator's. The rule is
`bot/services/advice.py`'s; this script moves questions and answers between
the database, the advice folder and the advisers.

Steps:
    export      the questions → `questions.json` and prompt batches for each
                adviser (read-only on the database)
    import      an adviser's replies (JSON) → `claude.json` / `gemini.json`
    status      where every pair stands (read-only)
    apply       the agreed answers → labels, through the viewer's own path
                (`repo.save_decision`, then `GameLinker.link_versions`); with
                the viewer stopped: the linker's lock holds in one process
    conflicts   the disputed pairs for the operator, as the viewer's
                `--proposals` file (and its `--gemini` folder)

Kinds of question (pair ids):
    g:<game>:<game>               two games (the review list's game ↔ game)
    v:<version>:<game>            a version against a game (version ↔ game)
    h:<platform>:<title id>:<hltb id>   an HLTB match in the grey zone
    d:<dlc>:<hltb id>             an HLTB DLC our DLC could be, not linked
                                  because the match was ambiguous

Usage:
    .venv/Scripts/python.exe -X utf8 -m scripts.advise_pairs [--schema dev] export
    … import --adviser claude data/advice/replies/claude_*.json
    … import --adviser gemini data/advice/replies/gemini_*.txt
    … status
    … apply --dry-run
    … apply
    … conflicts --out data/advice/proposals.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bot.config import get_settings
from bot.db import tools
from bot.db.postgres import Connection
from bot.db.repo import Database, Repo
from bot.services.advice import (
    ADVISER_SOURCES,
    ADVISERS,
    AUDIT_FRACTION,
    AUDIT_SEED,
    BOTH,
    PAIR_TYPES,
    AdviceStore,
    Answer,
    audit_picked,
    batches,
    decide,
    dlc_pair_id,
    games_pair_id,
    gemini_line,
    hltb_pair_id,
    label_of,
    parse_answers,
    prompt,
    proposal_answer,
    validate,
    versions_pair_id,
)
from bot.services.game_match import MODEL, RELATIONS
from bot.services.hltb_match import ACCEPT_SCORE, CLEAR_MARGIN, match_dlc_entries
from bot.util import utcnow_iso

logging.basicConfig(level="WARNING")

# An HLTB match is in the grey zone below this score (owner, 2026-10-12): a
# match under `ACCEPT_SCORE` won only because nothing came near it (the
# runner-up is not kept), and one within half a `CLEAR_MARGIN` above it may
# have had a runner-up close behind. 1.0 is an exact name or the Steam app
# HLTB's own page names.
HLTB_GREY_BELOW = round(ACCEPT_SCORE + CLEAR_MARGIN / 2, 3)
# A game's releases listed in a question, at most.
RELEASES_SHOWN = 8


# ---------------------------------------------------------------- the database


async def open_read_only(schema: str | None = None) -> Database:
    """The database opened read-only: no bring-up, no migration, nothing
    written (export, status and conflicts run beside the viewer)."""
    database = await tools.open_database(schema=schema)
    await database.conn.execute("SET default_transaction_read_only = on")
    return database


async def _rows(conn: Connection, sql: str, params: tuple = ()) -> list[dict]:
    cursor = await conn.execute(sql, params)
    return [dict(r) for r in await cursor.fetchall()]


@dataclass
class Facts:
    """What the questions are described from and checked against, read once."""

    versions: dict[int, dict] = field(default_factory=dict)
    game_of: dict[int, int] = field(default_factory=dict)
    role_of: dict[int, str] = field(default_factory=dict)
    games: dict[int, dict] = field(default_factory=dict)
    members: dict[int, list[int]] = field(default_factory=lambda: defaultdict(list))
    achievements: dict[tuple[str, str], int] = field(default_factory=dict)
    hltb_of: dict[int, list[tuple[int, str]]] = field(default_factory=lambda: defaultdict(list))
    hltb: dict[int, dict] = field(default_factory=dict)
    labels: list[dict] = field(default_factory=list)

    def current_game(self, game_id: int) -> int:
        """A game merged into another stands for that one."""
        seen = {game_id}
        while (row := self.games.get(game_id)) and row.get("merged_into"):
            game_id = int(row["merged_into"])
            if game_id in seen:
                break
            seen.add(game_id)
        return game_id

    def anchor(self, game_id: int) -> int | None:
        row = self.games.get(game_id) or {}
        if row.get("anchor_version_id"):
            return int(row["anchor_version_id"])
        found = self.members.get(game_id)
        return min(found) if found else None

    def label(self, a: int, b: int) -> dict | None:
        for lab in self.labels:
            if {lab["version_id"], lab["other_id"]} == {a, b}:
                return lab
        return None

    def labels_between_games(self, ga: int, gb: int) -> list[dict]:
        return [
            lab
            for lab in self.labels
            if {self.game_of.get(lab["version_id"]), self.game_of.get(lab["other_id"])} == {ga, gb}
        ]

    def labels_version_game(self, version_id: int, game_id: int) -> list[dict]:
        """Labels between a version and any version of a game."""
        found = set(self.members.get(game_id, []))
        return [
            lab
            for lab in self.labels
            if (lab["version_id"] == version_id and lab["other_id"] in found)
            or (lab["other_id"] == version_id and lab["version_id"] in found)
        ]

    def list_versions(self, platform: str, title_id: str) -> list[int]:
        return [
            v
            for v, row in self.versions.items()
            if row["platform"] == platform and str(row["title_id"]) == str(title_id)
        ]

    # ------------------------------------------------------------ descriptions

    def _year(self, v: dict) -> str:
        return (v.get("release_date") or "?")[:4]

    def _studio(self, row: dict) -> str:
        return " / ".join(str(x) for x in (row.get("developer"), row.get("publisher")) if x)

    def _count(self, v: dict) -> int:
        return self.achievements.get((v.get("platform") or "", str(v.get("title_id") or "")), 0)

    def hltb_text(self, hltb_id: int) -> str:
        h = self.hltb.get(hltb_id)
        if h is None:
            return f"HLTB entry {hltb_id} (not read)"
        bits = [h.get("game_type") or "?", str(h.get("release_year") or "?")]
        if studio := self._studio(h):
            bits.append(studio)
        platforms = str(h["platforms"]).split(", ") if h.get("platforms") else []
        if platforms:
            bits.append("on " + ", ".join(platforms[:6]))
        if h.get("steam_appid"):
            bits.append(f"Steam app {h['steam_appid']}")
        text = f'"{h["name"]}" ({"; ".join(bits)})'
        parent = self.hltb.get(h.get("parent_hltb_id") or -1)
        if parent:
            text += f'; a DLC of "{parent["name"]}"'
        return text

    def version_text(self, version_id: int, *, hltb: bool = True) -> str:
        v = self.versions[version_id]
        bits = [f"{v['store']} {v['console']}", self._year(v)]
        if v.get("kind") and v["kind"] != "game":
            bits.append(f"store kind {v['kind']}")
        if studio := self._studio(v):
            bits.append(studio)
        if n := self._count(v):
            bits.append(f"{n} achievements")
        if v.get("stand_in"):
            bits.append("no store page, only our achievement list")
        text = f'"{v["name"] or "?"}" ({"; ".join(bits)})'
        entries = [n for h, _ in self.hltb_of.get(version_id, []) if (n := self._hltb_name(h))]
        if hltb and entries:
            text += f'; on HLTB "{entries[0]}"'
        return text

    def _hltb_name(self, hltb_id: int) -> str | None:
        row = self.hltb.get(hltb_id)
        return str(row["name"]) if row else None

    def game_text(self, game_id: int, *, without: int | None = None) -> str:
        g = self.games.get(game_id) or {}
        years = str(g.get("year") or "?")
        if g.get("year") and g.get("last_year") and g["last_year"] > g["year"]:
            years += f"-{g['last_year']}"
        head = f'"{g.get("name") or game_id}" ({years}'
        head += f"; {studio})" if (studio := self._studio(g)) else ")"
        ids = sorted(
            (v for v in self.members.get(game_id, []) if v != without),
            key=lambda v: (self.versions[v].get("release_date") or "9999", v),
        )
        parts = []
        for v in ids[:RELEASES_SHOWN]:
            row = self.versions[v]
            role = self.role_of.get(v, "version")
            part = f"{row['console']} {self._year(row)}"
            part += f" {role}" if role != "version" else ""
            part += f' {row["store"]} "{row["name"] or "?"}"'
            if n := self._count(row):
                part += f" ({n} ach.)"
            parts.append(part)
        if len(ids) > RELEASES_SHOWN:
            parts.append(f"and {len(ids) - RELEASES_SHOWN} more")
        text = head + "; releases: " + ("; ".join(parts) or "none")
        if without is not None and without in self.members.get(game_id, []):
            text += " (FIRST is filed in this game now)"
        hltb = dict.fromkeys(h for v in ids for h, _ in self.hltb_of.get(v, []) if h in self.hltb)
        if hltb:
            text += "; HLTB: " + "; ".join(self.hltb_text(h) for h in list(hltb)[:2])
        return text

    def list_text(self, platform: str, title_id: str, name: str | None) -> str:
        ids = self.list_versions(platform, title_id)
        games = dict.fromkeys(self.game_of[v] for v in ids if v in self.game_of)
        text = f'achievement list "{name or title_id}" ({platform})'
        if ids:
            # Not the entry it is linked to now: that is the question.
            text += "; its releases: " + "; ".join(
                self.version_text(v, hltb=False) for v in ids[:4]
            )
        for g in list(games)[:1]:
            text += f'; in our game "{self.games.get(g, {}).get("name") or g}"'
        return text


async def load_facts(conn: Connection) -> Facts:
    f = Facts()
    for r in await _rows(
        conn,
        "SELECT version_id, store, product_id, console, platform, title_id, name, kind,"
        " developer, publisher, release_date, stand_in FROM versions",
    ):
        f.versions[int(r["version_id"])] = r
    for r in await _rows(
        conn, "SELECT version_id, game_id, role FROM versions WHERE game_id IS NOT NULL"
    ):
        f.game_of[int(r["version_id"])] = int(r["game_id"])
        f.role_of[int(r["version_id"])] = str(r["role"])
        f.members[int(r["game_id"])].append(int(r["version_id"]))
    for r in await _rows(conn, "SELECT * FROM games"):
        f.games[int(r["game_id"])] = r
    for r in await _rows(
        conn, "SELECT platform, title_id, COUNT(*) AS n FROM title_achievements GROUP BY 1, 2"
    ):
        f.achievements[(str(r["platform"]), str(r["title_id"]))] = int(r["n"])
    for r in await _rows(conn, "SELECT version_id, hltb_id, source FROM version_hltb"):
        f.hltb_of[int(r["version_id"])].append((int(r["hltb_id"]), str(r["source"])))
    for r in await _rows(
        conn,
        "SELECT hltb_id, name, game_type, parent_hltb_id, steam_appid, developer, publisher,"
        " release_year, (SELECT string_agg(p.platform, ', ' ORDER BY p.platform)"
        " FROM hltb_entry_platforms p WHERE p.hltb_id = hltb_entries.hltb_id)"
        " AS platforms FROM hltb_entries",
    ):
        f.hltb[int(r["hltb_id"])] = r
    f.labels = await _rows(
        conn, "SELECT version_id, other_id, relation, decided_by FROM match_decisions"
    )
    return f


def _operator(labels: list[dict]) -> bool:
    return any((lab.get("decided_by") or "") not in ADVISER_SOURCES for lab in labels)


# ---------------------------------------------------------------- export


def _model(relation: str, p: float | None) -> dict[str, Any]:
    """The model's answer in the advisers' words: its subject is FIRST."""
    if relation == "other":
        relation = "not_related"
    return {
        "relation": relation,
        "direction": "first" if relation in RELATIONS else None,
        "p": round(p, 3) if p is not None else None,
    }


def _games_question(
    facts: Facts, ga: int, gb: int, relation: str, p: float | None, audit: bool
) -> dict[str, Any]:
    a, b = facts.games.get(ga, {}), facts.games.get(gb, {})
    return {
        "pair_id": games_pair_id(ga, gb),
        "type": "games",
        "audit": audit,
        "model": _model(relation, p),
        "game_a": ga,
        "game_b": gb,
        "name_a": a.get("name"),
        "year_a": a.get("year"),
        "name_b": b.get("name"),
        "year_b": b.get("year"),
        "first": facts.game_text(ga),
        "second": facts.game_text(gb),
    }


def _versions_question(
    facts: Facts, subject: int, other: int, relation: str, p: float | None, audit: bool
) -> dict[str, Any]:
    game = facts.game_of[other]
    return {
        "pair_id": versions_pair_id(subject, game),
        "type": "versions",
        "audit": audit,
        "model": _model(relation, p),
        "version_id": subject,
        "other_id": other,
        "game_id": game,
        "first": facts.version_text(subject),
        "second": facts.game_text(game, without=subject),
    }


def _pair_question(
    facts: Facts, subject: int, other: int, relation: str, p: float | None, audit: bool
) -> dict[str, Any] | None:
    """A pair of versions as the viewer's /review splits it: about two games
    when its versions are in two games and the model sees a relation, else
    about one version and a game."""
    if subject not in facts.game_of or other not in facts.game_of:
        return None
    ga, gb = facts.game_of[subject], facts.game_of[other]
    if ga != gb and relation in RELATIONS:
        if facts.labels_between_games(ga, gb):
            return None
        return _games_question(facts, ga, gb, relation, p, audit)
    if ga != gb and relation == "other" and audit:
        if facts.labels_between_games(ga, gb):
            return None
        return _games_question(facts, ga, gb, relation, p, audit)
    if facts.labels_version_game(subject, gb) or facts.label(subject, other):
        return None
    return _versions_question(facts, subject, other, relation, p, audit)


async def advised_pairs(
    conn: Connection, facts: Facts, types: set[str]
) -> dict[str, dict[str, Any]]:
    """The pairs the model is not sure of: its review list (`match_pairs`, as
    the linker last wrote it), HLTB matches in the grey zone, and HLTB DLC
    left unlinked as ambiguous."""
    found: dict[str, dict[str, Any]] = {}
    if types & {"games", "versions"}:
        for r in await _rows(
            conn,
            "SELECT version_id, other_id, relation, p FROM match_pairs ORDER BY p DESC",
        ):
            q = _pair_question(
                facts, int(r["version_id"]), int(r["other_id"]), r["relation"], r["p"], False
            )
            if q and q["type"] in types and q["pair_id"] not in found:
                found[q["pair_id"]] = q
    if "hltb" in types:
        for q in await _hltb_questions(conn, facts, audit=False):
            found.setdefault(q["pair_id"], q)
    if "dlc" in types:
        for q in await _dlc_questions(conn, facts):
            found.setdefault(q["pair_id"], q)
    return found


async def _hltb_questions(conn: Connection, facts: Facts, *, audit: bool) -> list[dict[str, Any]]:
    """HLTB matches in the grey zone (`audit=False`), or the sure ones."""
    where = "b.score >= ?" if audit else "b.score < ?"
    found = []
    # A list's automatic match (the operator's and the refused are not asked
    # again): the surest link of any of its versions.
    for r in await _rows(
        conn,
        "SELECT t.platform, t.title_id, COALESCE(t.name_en, t.name) AS name, b.hltb_id,"
        " b.score AS hltb_match_score FROM achievement_list_connectors t JOIN ("
        "  SELECT v.platform, v.title_id, vh.hltb_id, MAX(vh.score) AS score"
        "  FROM versions v JOIN version_hltb vh ON vh.version_id = v.version_id"
        "  WHERE vh.source = 'auto' GROUP BY v.platform, v.title_id, vh.hltb_id) b"
        f" ON b.platform = t.platform AND b.title_id = t.title_id WHERE {where}",
        (HLTB_GREY_BELOW,),
    ):
        ids = facts.list_versions(r["platform"], str(r["title_id"]))
        if not ids:
            continue
        if any(src == "manual" for v in ids for _, src in facts.hltb_of.get(v, [])):
            continue  # the operator set this list's entry by hand
        hltb_id = int(r["hltb_id"])
        found.append(
            {
                "pair_id": hltb_pair_id(r["platform"], str(r["title_id"]), hltb_id),
                "type": "hltb",
                "audit": audit,
                "model": {"relation": "same", "direction": None, "p": r["hltb_match_score"]},
                "platform": r["platform"],
                "title_id": str(r["title_id"]),
                "hltb_id": hltb_id,
                "first": facts.list_text(r["platform"], str(r["title_id"]), r["name"]),
                "second": facts.hltb_text(hltb_id),
            }
        )
    return found


async def _dlc_rows(conn: Connection) -> dict[int, list[dict]]:
    """Our DLC under each HLTB entry with DLC of its own (as
    `repo.dlcs_under_hltb`), read at once."""
    by_entry: dict[int, list[dict]] = defaultdict(list)
    for r in await _rows(
        conn,
        "SELECT vh.hltb_id, d.dlc_id, v.store, d.store_id, d.name, d.kind, d.release_date,"
        " v.name AS version_name, v.console, v.version_id"
        " FROM version_hltb vh JOIN versions v ON v.version_id = vh.version_id"
        " JOIN dlcs d ON d.version_id = v.version_id"
        " WHERE vh.hltb_id IN (SELECT DISTINCT parent_hltb_id FROM hltb_entries"
        "  WHERE parent_hltb_id IS NOT NULL) ORDER BY d.dlc_id",
    ):
        by_entry[int(r["hltb_id"])].append(r)
    return by_entry


def _dlc_text(d: dict) -> str:
    bits = [d.get("kind") or "dlc", (d.get("release_date") or "?")[:4]]
    return (
        f'"{d["name"] or "?"}" ({"; ".join(bits)}); an add-on of "{d["version_name"]}"'
        f" ({d['store']} {d['console']})"
    )


async def _dlc_questions(conn: Connection, facts: Facts) -> list[dict[str, Any]]:
    """Our DLC that one or more of an HLTB game's DLC entries would match on
    its own, which `hltb_match.match_dlc_entries` left unlinked because the
    match is ambiguous (a name two entries share, one entry on two products
    of one store)."""
    children: dict[int, list[tuple[int, str, int | None]]] = defaultdict(list)
    for h in facts.hltb.values():
        if h.get("parent_hltb_id") and (h.get("game_type") or "dlc") in ("dlc", "expansion"):
            children[int(h["parent_hltb_id"])].append(
                (int(h["hltb_id"]), str(h["name"] or ""), h.get("steam_appid"))
            )
    linked = {
        int(r["dlc_id"])
        for r in await _rows(conn, "SELECT dlc_id FROM dlc_hltb WHERE source <> 'rejected'")
    }
    found = []
    for entry, dlcs in (await _dlc_rows(conn)).items():
        kids = children.get(entry)
        if not kids:
            continue
        names = [str(facts.hltb.get(entry, {}).get("name") or "")]
        names += list(dict.fromkeys(str(d["version_name"]) for d in dlcs if d["version_name"]))
        ours = [(int(d["dlc_id"]), str(d["store"]), d["store_id"], d["name"]) for d in dlcs]
        sure = match_dlc_entries(kids, ours, names)
        for d, dlc in zip(dlcs, ours, strict=True):
            if dlc[0] in sure or dlc[0] in linked:
                continue
            for kid in kids:
                if match_dlc_entries([kid], [dlc], names):
                    found.append(
                        {
                            "pair_id": dlc_pair_id(dlc[0], kid[0]),
                            "type": "dlc",
                            "audit": False,
                            "model": {"relation": "unsure", "direction": None, "p": None},
                            "dlc_id": dlc[0],
                            "hltb_id": kid[0],
                            "first": _dlc_text(d),
                            "second": facts.hltb_text(kid[0]),
                        }
                    )
    return found


async def audit_pairs(
    repo: Repo,
    conn: Connection,
    facts: Facts,
    types: set[str],
    fraction: float,
    seed: int,
    advised: set[str],
) -> dict[str, dict[str, Any]]:
    """A seeded sample of the pairs the model is sure of: every candidate
    pair scored again (`compare`), those linked or kept apart while their
    names are alike; one question per pair id; `audit_picked` decides. Two
    versions of one achievement list are one game by what they are, not by
    the model: they are left out. Sure HLTB matches and automatic DLC links
    are sampled the same way."""
    from bot.services.game_link import _Index, load_candidates
    from bot.services.game_match import compare

    found: dict[str, dict[str, Any]] = {}
    if types & {"games", "versions"}:
        rows = await repo.match_rows()
        candidates = await load_candidates(repo, [int(r["version_id"]) for r in rows])
        index = _Index(list(candidates.values()))
        pairs = sorted(index.pairs(list(candidates.values())))
        print(f"  scoring {len(pairs)} candidate pairs again…", file=sys.stderr)
        verdicts = [compare(candidates[a], candidates[b]) for a, b in pairs]
        verdicts.sort(key=lambda v: -v.p)
        for v in verdicts:
            if v.state == "review" or "one_list" in v.features:
                continue
            if v.state == "apart" and v.features.get("name", -1.0) < 0:
                continue  # not even alike: nothing to doubt
            q = _pair_question(facts, v.subject, v.other, v.relation, v.p, True)
            if q is None or q["type"] not in types or q["pair_id"] in advised:
                continue
            if q["pair_id"] in found or not audit_picked(q["pair_id"], fraction, seed):
                continue
            found[q["pair_id"]] = q
    if "hltb" in types:
        for q in await _hltb_questions(conn, facts, audit=True):
            if q["pair_id"] not in advised and audit_picked(q["pair_id"], fraction, seed):
                found.setdefault(q["pair_id"], q)
    if "dlc" in types:
        dlcs = {int(d["dlc_id"]): d for ds in (await _dlc_rows(conn)).values() for d in ds}
        for r in await _rows(conn, "SELECT dlc_id, hltb_id FROM dlc_hltb WHERE source = 'auto'"):
            d = dlcs.get(int(r["dlc_id"]))
            pid = dlc_pair_id(int(r["dlc_id"]), int(r["hltb_id"]))
            if d is None or pid in advised or not audit_picked(pid, fraction, seed):
                continue
            found[pid] = {
                "pair_id": pid,
                "type": "dlc",
                "audit": True,
                "model": {"relation": "same", "direction": None, "p": None},
                "dlc_id": int(r["dlc_id"]),
                "hltb_id": int(r["hltb_id"]),
                "first": _dlc_text(d),
                "second": facts.hltb_text(int(r["hltb_id"])),
            }
    return found


def write_batches(
    store: AdviceStore, questions: dict[str, dict[str, Any]], current: list[str], out: Path
) -> dict[str, int]:
    """Each adviser's prompt batches for the pairs it has not answered yet:
    `<out>/<adviser>/batch_NN.txt`, and `<out>/batches.json` naming their
    pairs. Old batch files are replaced."""
    applied = store.applied()
    written: dict[str, int] = {}
    index: dict[str, list[dict[str, Any]]] = {}
    for adviser in ADVISERS:
        answered = store.answers(adviser)
        todo = [p for p in current if p not in answered and p not in applied]
        folder = out / adviser
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("batch_*.txt"):
            old.unlink()
        index[adviser] = []
        for n, chunk in enumerate(batches(todo), 1):
            name = f"batch_{n:02d}.txt"
            text = prompt([questions[p] for p in chunk], adviser)
            (folder / name).write_text(text, encoding="utf-8", newline="\n")
            index[adviser].append({"file": f"{adviser}/{name}", "pair_ids": chunk})
        written[adviser] = len(index[adviser])
    (out / "batches.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    return written


async def export(args: argparse.Namespace) -> None:
    types = set(args.types.split(",")) & set(PAIR_TYPES)
    store = _store(args)
    database = await open_read_only(args.schema)
    try:
        conn = database.conn
        facts = await load_facts(conn)
        advised = await advised_pairs(conn, facts, types)
        audit: dict[str, dict[str, Any]] = {}
        if args.audit > 0:
            audit = await audit_pairs(
                Repo(database), conn, facts, types, args.audit, args.seed, set(advised)
            )
    finally:
        await database.close()
    now = utcnow_iso()
    pairs = {**audit, **advised}
    for q in pairs.values():
        q["exported_at"] = now
    current = list(advised) + list(audit)
    store.save_questions(pairs, current, now)
    out = Path(args.out) if args.out else store.directory / "batches"
    written = write_batches(store, store.questions(), current, out)
    counts = Counter((q["type"], q["audit"]) for q in pairs.values())
    print(f"questions → {store.directory / 'questions.json'}")
    for t in PAIR_TYPES:
        if t in types:
            print(f"  {t:9} advised {counts[(t, False)]:5}   audit {counts[(t, True)]:5}")
    print(f"  total     {len(pairs)} (audit {args.audit:g}, seed {args.seed})")
    for adviser, n in written.items():
        print(f"batches for {adviser}: {n} → {out / adviser}")


# ---------------------------------------------------------------- import


def import_answers(store: AdviceStore, adviser: str, files: list[Path]) -> tuple[int, list[str]]:
    questions = store.questions()
    answers = store.answers(adviser)
    stored, refused = 0, []
    for path in files:
        for item in parse_answers(path.read_text(encoding="utf-8")):
            result = validate(item, questions)
            if isinstance(result, str):
                refused.append(f"{path.name}: {result}")
                continue
            answers[str(item.get("pair_id") or item.get("id")).strip()] = result
            stored += 1
    store.save_answers(adviser, answers)
    return stored, refused


def import_command(args: argparse.Namespace) -> None:
    store = _store(args)
    files = [Path(f) for f in args.files]
    stored, refused = import_answers(store, args.adviser, files)
    print(f"{args.adviser}: {stored} answers stored → {store.directory / (args.adviser + '.json')}")
    for line in refused:
        print(f"  refused {line}")


# ---------------------------------------------------------------- the rule, pair by pair


def operator_answered(facts: Facts, q: dict[str, Any]) -> bool:
    """Whether the operator already answered this pair (a label, or an HLTB
    entry set by hand)."""
    if q["type"] == "games":
        ga, gb = facts.current_game(q["game_a"]), facts.current_game(q["game_b"])
        return _operator(facts.labels_between_games(ga, gb))
    if q["type"] == "versions":
        game = facts.game_of.get(q["other_id"], q["game_id"])
        found = facts.labels_version_game(q["version_id"], game)
        if (lab := facts.label(q["version_id"], q["other_id"])) is not None:
            found.append(lab)
        return _operator(found)
    if q["type"] == "hltb":
        ids = facts.list_versions(q["platform"], q["title_id"])
        return any(src == "manual" for v in ids for _, src in facts.hltb_of.get(v, []))
    return False


def states(
    store: AdviceStore, facts: Facts | None
) -> list[tuple[dict[str, Any], str, Answer | None, str | None, str]]:
    """Every question with where it stands: (question, state, the agreed
    answer, who decided, why it is disputed)."""
    claude, gemini, applied = store.answers("claude"), store.answers("gemini"), store.applied()
    found = []
    for pid, q in store.questions().items():
        outcome = decide(Answer.of(q.get("model")), claude.get(pid), gemini.get(pid))
        state = outcome.state
        if pid in applied:
            state = str(applied[pid].get("state") or "applied")
        elif facts is not None and operator_answered(facts, q):
            state = "operator"
        elif state == "agreed":
            state = "agreed_3" if outcome.decided_by == "model+claude+gemini" else "agreed_2"
        found.append((q, state, outcome.answer, outcome.decided_by, outcome.reason))
    return found


async def status(args: argparse.Namespace) -> None:
    store = _store(args)
    database = await open_read_only(args.schema)
    try:
        facts = await load_facts(database.conn)
    finally:
        await database.close()
    table: dict[str, Counter] = defaultdict(Counter)
    audit: Counter = Counter()
    current = set(store.last_export())
    for q, state, _a, _by, _why in states(store, facts):
        table[q["type"]][state] += 1
        if q.get("audit"):
            audit[(q["type"], state)] += 1
    order = (
        "waiting_both",
        "waiting_claude",
        "waiting_gemini",
        "agreed_3",
        "agreed_2",
        "conflict",
        "operator",
        "applied",
        "recorded",
        "gone",
    )
    print(f"{len(store.questions())} questions, {len(current)} in the last export")
    print(f"{'':9} " + " ".join(f"{s:>14}" for s in order))
    for t in PAIR_TYPES:
        if table.get(t):
            print(f"{t:9} " + " ".join(f"{table[t][s]:>14}" for s in order))
    if audit:
        print("of which audit: " + ", ".join(f"{t} {s} {n}" for (t, s), n in sorted(audit.items())))
    print(
        "agreed_3: model, Claude and Gemini · agreed_2: Claude and Gemini, not the model"
        " (both written by apply) · conflict: the operator's (conflicts) · recorded: agreed,"
        " kept in the store (no way to write it yet)"
    )


# ---------------------------------------------------------------- apply


async def _write_label(
    repo: Repo, facts: Facts, x: int, y: int, relation: str, by: str, dry_run: bool
) -> str:
    """One label, as the viewer writes one (`catalog_viewer._label`, the
    relinking done once at the end); never over the operator's."""
    existing = facts.label(x, y)
    if existing is not None and (existing.get("decided_by") or "") not in ADVISER_SOURCES:
        return "operator"
    if (
        existing is not None
        and (existing["version_id"], existing["other_id"], existing["relation"]) == (x, y, relation)
        and existing.get("decided_by") == by
    ):
        return "applied"
    if not dry_run:
        features, model = await repo.pair_features(x, y)
        await repo.save_decision(
            x, y, relation, features=features, model=model or MODEL, decided_by=by
        )
    facts.labels = [lab for lab in facts.labels if {lab["version_id"], lab["other_id"]} != {x, y}]
    facts.labels.append({"version_id": x, "other_id": y, "relation": relation, "decided_by": by})
    return "applied"


async def apply_one(
    repo: Repo, facts: Facts, q: dict[str, Any], answer: Answer, by: str, dry_run: bool
) -> dict[str, Any]:
    """What one agreed answer writes: `{state, decided_by, label | hltb, reason}`."""
    done: dict[str, Any] = {"decided_by": by, "answer": answer.relation, "at": utcnow_iso()}
    if q["type"] in ("games", "versions"):
        labelled = label_of(answer)
        if labelled is None:
            return {**done, "state": "gone", "reason": "no label for this answer"}
        relation, flip = labelled
        if q["type"] == "games":
            ga, gb = facts.current_game(q["game_a"]), facts.current_game(q["game_b"])
            if ga == gb:
                return {**done, "state": "gone", "reason": "one game now"}
            if _operator(facts.labels_between_games(ga, gb)):
                return {**done, "state": "operator"}
            x, y = facts.anchor(ga), facts.anchor(gb)
        else:
            x, y = q["version_id"], q["other_id"]
            if x not in facts.versions or y not in facts.versions:
                return {**done, "state": "gone", "reason": "a version is gone"}
            if operator_answered(facts, q):
                return {**done, "state": "operator"}
        if x is None or y is None:
            return {**done, "state": "gone", "reason": "a game has no version"}
        if flip:
            x, y = y, x
        state = await _write_label(repo, facts, x, y, relation, by, dry_run)
        return {**done, "state": state, "label": [x, y, relation]}
    if q["type"] == "hltb":
        if operator_answered(facts, q):
            return {**done, "state": "operator"}
        ids = facts.list_versions(q["platform"], q["title_id"])
        if answer.relation != "same":
            # Not this entry: a refusal on each version of the list, which no
            # check or collection makes into a link again.
            if not dry_run:
                for v in ids:
                    await repo.unlink_version_hltb(v, q["hltb_id"])
            return {**done, "state": "applied", "hltb": [ids, q["hltb_id"], "rejected"]}
        if not dry_run:
            for v in ids:
                # The operator's own kind of link: kept through every check.
                await repo.link_version_hltb(v, q["hltb_id"], "manual")
        return {**done, "state": "applied", "hltb": [ids, q["hltb_id"], "manual"]}
    # dlc: the answer is a hand-made link, or a refusal the matcher keeps.
    if not dry_run:
        if answer.relation == "same":
            await repo.link_dlc_hltb(q["dlc_id"], q["hltb_id"])
        else:
            await repo.reject_dlc_hltb(q["dlc_id"], q["hltb_id"])
    kind = "manual" if answer.relation == "same" else "rejected"
    return {**done, "state": "applied", "dlc": [q["dlc_id"], q["hltb_id"], kind]}


async def apply(args: argparse.Namespace) -> None:
    from bot.services.game_link import GameLinker

    store = _store(args)
    database = await (
        open_read_only(args.schema) if args.dry_run else tools.open_database(schema=args.schema)
    )
    applied = store.applied()
    written: Counter = Counter()
    touched: set[int] = set()
    try:
        repo = Repo(database)
        facts = await load_facts(database.conn)
        claude, gemini = store.answers("claude"), store.answers("gemini")
        for pid, q in store.questions().items():
            outcome = decide(Answer.of(q.get("model")), claude.get(pid), gemini.get(pid))
            if outcome.state != "agreed" or outcome.answer is None or outcome.decided_by is None:
                continue
            before = applied.get(pid)
            # "recorded" was an answer there was no way to write yet.
            if (
                before
                and before.get("answer") == outcome.answer.relation
                and before.get("state") != "recorded"
            ):
                continue
            done = await apply_one(repo, facts, q, outcome.answer, outcome.decided_by, args.dry_run)
            written[(q["type"], done["state"])] += 1
            if done.get("label") and done["state"] == "applied":
                touched |= set(done["label"][:2])
            what = (
                done.get("label") or done.get("hltb") or done.get("dlc") or done.get("reason") or ""
            )
            print(f"  {pid}: {done['state']} {outcome.decided_by} {outcome.answer.relation} {what}")
            applied[pid] = done
        if touched and not args.dry_run:
            report = await GameLinker(repo).link_versions(sorted(touched))
            print(f"relinked around {len(touched)} versions: {len(report.games)} games")
    finally:
        await database.close()
    if not args.dry_run:
        store.save_applied(applied)
    print(("would write: " if args.dry_run else "written: ") + str(dict(written) or "nothing"))


# ---------------------------------------------------------------- conflicts


async def conflicts(args: argparse.Namespace) -> None:
    """The disputed pairs for the operator. Two games: the viewer's
    `--proposals` file (Claude's answer as the proposal) and its `--gemini`
    folder; everything else in `<out>_other.json` (version pairs are on the
    viewer's /review as well)."""
    store = _store(args)
    database = await open_read_only(args.schema)
    try:
        facts = await load_facts(database.conn)
    finally:
        await database.close()
    claude, gemini = store.answers("claude"), store.answers("gemini")
    proposals, lines, other = [], [], []
    applied = store.applied()
    for q, state, _answer, _by, reason in states(store, facts):
        # Under the rule that the model, Claude and Gemini must all agree
        # (owner, 2026-10-15) a pair the advisers decided against the model
        # is the operator's again, as a conflict is.
        overruled = (applied.get(q["pair_id"]) or {}).get("decided_by") == BOTH
        if state != "conflict" and not overruled:
            continue
        pid = q["pair_id"]
        c, g = claude[pid], gemini[pid]
        if q["type"] == "games":
            ga, gb = facts.current_game(q["game_a"]), facts.current_game(q["game_b"])
            if ga == gb:
                continue
            model = q["model"]["relation"]
            model = "other" if model == "not_related" else model
            proposals.append(
                {
                    "pair_id": pid,
                    "game_a": ga,
                    "name_a": facts.games.get(ga, {}).get("name"),
                    "year_a": facts.games.get(ga, {}).get("year"),
                    "game_b": gb,
                    "name_b": facts.games.get(gb, {}).get("name"),
                    "year_b": facts.games.get(gb, {}).get("year"),
                    "model": model,
                    "p": q["model"].get("p") or 0.0,
                    "answer": proposal_answer(c, model),
                    "confidence": c.confidence,
                    "why": f"{c.why} [{reason}]".strip(),
                    "audit": q.get("audit", False),
                }
            )
            if (line := gemini_line(len(proposals), g)) is not None:
                lines.append(line)
        else:
            other.append(
                {
                    "pair_id": pid,
                    "type": q["type"],
                    "audit": q.get("audit", False),
                    "reason": reason,
                    "first": q["first"],
                    "second": q["second"],
                    "model": q["model"],
                    "claude": _plain(c),
                    "gemini": _plain(g),
                }
            )
    out = Path(args.out)
    if args.review:
        # Everything the operator re-checks (owner, 2026-10-13): the
        # conflicts and the pairs the advisers decided against the model, of
        # every kind, in one file for the viewer's /advised.
        items = review_items(store, facts)
        review_path = out.parent / f"{out.stem}_review.json"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(json.dumps(items, ensure_ascii=False, indent=1), "utf-8")
        print(f"{len(items)} pairs to re-check → {review_path}")
    if args.into_proposals:
        added = add_to_proposals(
            Path(args.into_proposals), Path(args.into_gemini), proposals, lines
        )
        print(f"{added} game pairs added to {args.into_proposals}")
        return
    gemini_dir, other_path = write_conflicts(out, proposals, lines, other)
    print(f"{len(proposals)} game pairs → {out}; {len(other)} other pairs → {other_path}")
    print(
        "viewer: .venv/Scripts/python.exe -X utf8 -m scripts.catalog_viewer"
        f"{_schema_flag(args)} --proposals {out} --gemini {gemini_dir}"
    )


def add_to_proposals(path: Path, gemini_dir: Path, proposals: list[dict], lines: list[str]) -> int:
    """The game pairs not in the viewer's proposals yet, appended (numbered on from
    the last) with Gemini's line for each in a file of its own; what is there is
    left as it is, so the numbers the viewer already holds keep their meaning."""
    existing = json.loads(path.read_text("utf-8")) if path.exists() else []
    seen = {frozenset((p["game_a"], p["game_b"])) for p in existing}
    by_number = {int(line.split("|", 1)[0]): line for line in lines}
    fresh, fresh_lines = [], []
    for n, proposal in enumerate(proposals, 1):
        key = frozenset((proposal["game_a"], proposal["game_b"]))
        if key in seen:
            continue
        seen.add(key)
        fresh.append(proposal)
        line = by_number.get(n)
        if line is not None:
            number = len(existing) + len(fresh)
            fresh_lines.append(f"{number}|{line.split('|', 1)[1]}")
    if fresh:
        lf = "\n"
        path.write_text(
            json.dumps([*existing, *fresh], ensure_ascii=False, indent=1), "utf-8", newline=lf
        )
        gemini_dir.mkdir(parents=True, exist_ok=True)
        (gemini_dir / "overruled.txt").write_text(lf.join(fresh_lines) + lf, "utf-8", newline=lf)
    return len(fresh)


def review_items(store: AdviceStore, facts: Facts) -> list[dict[str, Any]]:
    """The pairs for the operator's second look: every conflict, and every
    answer Claude and Gemini gave against the model (written or kept aside),
    with all three opinions and, for a written one, the pair of versions its
    label is on (so a correction replaces it)."""
    claude, gemini, applied = store.answers("claude"), store.answers("gemini"), store.applied()
    items = []
    for q, state, _answer, _by, reason in states(store, facts):
        pid = q["pair_id"]
        done = applied.get(pid) or {}
        if state == "conflict":
            why = "conflict"
        elif done.get("decided_by") == BOTH:
            why = "overruled"
        else:
            continue
        item: dict[str, Any] = {
            "pair_id": pid,
            "type": q["type"],
            "why": why,
            "reason": reason,
            "audit": q.get("audit", False),
            "first": q["first"],
            "second": q["second"],
            "model": q.get("model"),
            "claude": _plain(claude[pid]) if pid in claude else None,
            "gemini": _plain(gemini[pid]) if pid in gemini else None,
            "state": done.get("state") or state,
            "label": done.get("label"),
        }
        if q["type"] == "games":
            item["game_a"] = facts.current_game(q["game_a"])
            item["game_b"] = facts.current_game(q["game_b"])
        for key in (
            "version_id",
            "other_id",
            "game_id",
            "platform",
            "title_id",
            "hltb_id",
            "dlc_id",
        ):
            if key in q:
                item[key] = q[key]
        items.append(item)
    order = {"games": 0, "versions": 1, "hltb": 2, "dlc": 3}
    items.sort(key=lambda i: (order.get(i["type"], 9), i["why"] != "conflict", i["pair_id"]))
    return items


def write_conflicts(
    out: Path, proposals: list[dict], lines: list[str], other: list[dict]
) -> tuple[Path, Path]:
    """The proposals file, Gemini's answers beside it (`<stem>_gemini/`) and
    the other kinds of pair (`<stem>_other.json`)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    lf = "\n"
    out.write_text(json.dumps(proposals, ensure_ascii=False, indent=1), "utf-8", newline=lf)
    gemini_dir = out.parent / f"{out.stem}_gemini"
    gemini_dir.mkdir(exist_ok=True)
    (gemini_dir / "answers.txt").write_text(lf.join(lines) + lf, "utf-8", newline=lf)
    other_path = out.parent / f"{out.stem}_other.json"
    other_path.write_text(json.dumps(other, ensure_ascii=False, indent=1), "utf-8", newline=lf)
    return gemini_dir, other_path


def _plain(answer: Answer) -> dict[str, Any]:
    return {
        "relation": answer.relation,
        "direction": answer.direction,
        "confidence": answer.confidence,
        "why": answer.why,
    }


# ---------------------------------------------------------------- main


def _store(args: argparse.Namespace) -> AdviceStore:
    if args.advice_dir:
        return AdviceStore(Path(args.advice_dir))
    return AdviceStore.for_db(get_settings().db_path)


def _schema_flag(args: argparse.Namespace) -> str:
    return f" --schema {args.schema}" if args.schema else ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    tools.add_arguments(parser)
    parser.add_argument(
        "--advice-dir",
        default=None,
        help="where questions and answers are kept (<DB_PATH's folder>/advice)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("export", help="the questions and the advisers' prompt batches")
    p.add_argument("--types", default=",".join(PAIR_TYPES))
    p.add_argument("--audit", type=float, default=AUDIT_FRACTION, help="share of sure pairs")
    p.add_argument("--seed", type=int, default=AUDIT_SEED)
    p.add_argument("--out", default=None, help="the batches' folder (<advice dir>/batches)")
    p = sub.add_parser("import", help="an adviser's replies")
    p.add_argument("--adviser", required=True, choices=ADVISERS)
    p.add_argument("files", nargs="+")
    sub.add_parser("status", help="where every pair stands")
    p = sub.add_parser("apply", help="write the agreed answers as labels")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("conflicts", help="the disputed pairs, for the viewer's /proposals")
    p.add_argument("--out", required=True)
    p.add_argument(
        "--into-proposals",
        help="add the game pairs not in this proposals file yet to it, instead of writing --out",
    )
    p.add_argument("--into-gemini", help="the folder of Gemini's lines beside that file")
    p.add_argument(
        "--review",
        action="store_true",
        help="also <out>_review.json: conflicts and the advisers' answers against the model,"
        " every kind, for the viewer's /advised",
    )
    args = parser.parse_args()
    if args.command == "import":
        import_command(args)
        return
    command = {"export": export, "status": status, "apply": apply, "conflicts": conflicts}
    tools.run(command[args.command](args))


if __name__ == "__main__":
    main()
