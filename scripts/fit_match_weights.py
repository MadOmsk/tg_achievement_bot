"""Fit the games matcher's weights to the labels and judge the fit (#147;
the training audit, 2026-10-24).

Reads every label (`match_decisions`), works out each pair's signs as the
model reads them now — the label's own version as the subject, so "a is a
remaster of b" teaches the remaster's side — and fits the weights, pulled
towards the current ones (`match_fit.fit`: the bias kept, a class with few
labels held closer). Then:

- **held out by game** (`match_fit.held_out`): every label answered by
  weights fitted without its group of games;
- **the gate** (`match_fit.gate`): the operator's labels alone decide
  whether the fit is better; every source's scores are printed beside;
- **what it would change**: every pair the linker compares, scored by the
  current and the fitted weights — how many would be linked, sent to review
  or kept apart otherwise, with examples.

Writes the fitted weights as JSON. Changes nothing in the database.

Read-only, safe beside a running bot.

Usage:
    .venv/Scripts/python.exe -X utf8 -m scripts.fit_match_weights [--out weights.json]
        [--db data/games.db] [--without model+claude+gemini] [--strength 0.001]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections import Counter
from pathlib import Path

from bot.config import get_settings
from bot.db.repo import Database, Repo
from bot.services.game_link import GameLinker, _candidate, _Index, load_candidates
from bot.services.game_match import WEIGHTS, Candidate, compare, features
from bot.services.match_fit import (
    LABEL_CLASS,
    Example,
    Weights,
    changes,
    class_strengths,
    fit,
    gate,
    held_out,
    label_weight,
)

logging.basicConfig(level="WARNING")


async def examples_from(repo: Repo, sources: dict[str, int] | None = None) -> list[Example]:
    """Every label as an example, its games as its groups; `sources` counts
    them by who gave them."""
    labels = await repo.all_decisions()
    ids = sorted({lab["version_id"] for lab in labels} | {lab["other_id"] for lab in labels})
    candidates = await load_candidates(repo, ids)
    games = await repo.memberships(ids)
    found = []
    for lab in labels:
        label = LABEL_CLASS.get(lab["relation"])
        if label is None:
            continue
        a, b = candidates.get(lab["version_id"]), candidates.get(lab["other_id"])
        if a is not None and b is not None:
            f = features(a, b, ordered=label != "same" and label != "other")
        elif lab["features"]:
            f = json.loads(lab["features"])  # the versions are gone: what was seen then
        else:
            continue
        groups = tuple(
            ("game", games[v]["game_id"]) if v in games else ("version", v)
            for v in (lab["version_id"], lab["other_id"])
        )
        by = str(lab["decided_by"] or "?")
        found.append(Example(f, label, label_weight(by), by, groups))
        if sources is not None:
            sources[by] = sources.get(by, 0) + 1
    return found


async def population(repo: Repo, fitted: Weights) -> tuple[Counter, list[str]]:
    """Every pair the linker compares, scored by the current weights and
    the fitted ones: how the states move, and a few named examples."""
    rows = await repo.match_rows()
    candidates = [_candidate(r) for r in rows]
    await GameLinker(repo)._load_achievements(candidates, rows)
    by_id = {c.version_id: c for c in candidates}
    moves: Counter = Counter()
    shown: list[str] = []

    def name(c: Candidate) -> str:
        return f"{c.names[0] if c.names else c.product_id} [{c.console}]"

    for a, b in sorted(_Index(candidates).pairs(candidates)):
        was, now = compare(by_id[a], by_id[b]), compare(by_id[a], by_id[b], fitted)
        before, after = f"{was.state}:{was.relation}", f"{now.state}:{now.relation}"
        if was.state == "apart" and now.state == "apart":
            continue
        moves[(before, after) if before != after else "unchanged"] += 1
        if before != after and len(shown) < 40:
            shown.append(f"{name(by_id[a])} ~ {name(by_id[b])}: {before} → {after}")
    return moves, shown


async def run(args: argparse.Namespace) -> Weights | None:
    """The report, printed; the fitted weights, rounded (None: too few labels)."""
    database = await Database(Path(args.db or get_settings().db_path)).connect()
    try:
        repo = Repo(database)
        sources: dict[str, int] = {}
        examples = await examples_from(repo, sources)
        print(f"labels: {len(examples)} {dict(Counter(e.label for e in examples))}")
        print(
            "by source: "
            + ", ".join(f"{by} {n} (×{label_weight(by):g})" for by, n in sorted(sources.items()))
        )
        if len(examples) < 5:
            print("too few labels to fit anything yet")
            return None
        without = set(args.without or ())
        learn = [e for e in examples if e.source not in without]
        kw = {
            "strength": args.strength,
            "strengths": class_strengths(learn, args.strength),
            "epochs": args.epochs,
        }

        rows = held_out(examples, WEIGHTS, train=lambda e: e.source not in without, **kw)
        verdict = gate(rows)
        print("held out by game (right · log-loss), current → fitted:")
        for src, (was, now) in verdict.by_source.items():
            print(
                f"  {src:22} n={was.n:4}  {was.accuracy:5.1%} · {was.log_loss:.3f}"
                f"  →  {now.accuracy:5.1%} · {now.log_loss:.3f}"
            )
        print(
            f"GATE (the operator's labels): {verdict.start.accuracy:.1%} · "
            f"{verdict.start.log_loss:.3f} → {verdict.fitted.accuracy:.1%} · "
            f"{verdict.fitted.log_loss:.3f} — {'PASSED' if verdict.passed else 'not passed'}"
        )

        fitted = fit(learn, WEIGHTS, **kw)
        print("weights that moved most:")
        for cls, sign, was, now in changes(WEIGHTS, fitted, at_least=0.3)[:30]:
            print(f"  {cls:12} {sign:26} {was:+6.2f} → {now:+6.2f}")
        moves, shown = await population(repo, fitted)
        print(f"pairs the linker compares, not apart either way: {sum(moves.values())}")
        for move, n in moves.most_common(15):
            print(f"  {n:5}  {move if isinstance(move, str) else ' → '.join(move)}")
        for line in shown:
            print(f"    {line}")
        return {c: {k: round(v, 2) for k, v in w.items() if round(v, 2)} for c, w in fitted.items()}
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="match_weights.fitted.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--strength", type=float, default=0.001)
    parser.add_argument("--epochs", type=int, default=800)
    parser.add_argument("--without", action="append", help="a source not to learn from")
    args = parser.parse_args()
    fitted = asyncio.run(run(args))
    if fitted is not None:
        Path(args.out).write_text(json.dumps(fitted, indent=1), encoding="utf-8")
        print(f"written to {args.out}")


if __name__ == "__main__":
    main()
