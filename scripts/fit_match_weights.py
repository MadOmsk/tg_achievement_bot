"""Fit the games matcher's weights to the labels and judge the fit (#147;
the training audit, 2026-10-24).

Reads every label (`match_decisions`), works out each pair's signs as the
model reads them now — the label's own version as the subject, so "a is a
remaster of b" teaches the remaster's side — and fits the weights, pulled
towards the current ones (`match_fit.fit`: the bias kept, a class with few
labels held closer). Then:

- **held out by game** (`match_fit.held_out`): every label answered by
  weights fitted without its group of games;
- **the gate** (`match_fit.gate`): the frozen set of pairs
  (`--freeze-eval` writes it, `advice/eval_set.json` beside the database)
  or, without one, the operator's labels decide whether the fit is better —
  each class's recall printed, a class lost refused; every source's scores
  are printed beside;
- **what it would change**: every pair the linker compares, scored by the
  current and the fitted weights — how many would be linked, sent to review
  or kept apart otherwise, with examples.

Writes the fitted weights as JSON. With `--save` it also keeps them in the
database (`match_weights`) and makes them the active set — the linker's
weights from its next link — but only when the gate passed. `--activate N`
switches to a set kept before (`--activate hand`: back to the hand weights),
`--list` lists them; neither fits anything.

Without those flags read-only, safe beside a running bot.

Usage:
    .venv/Scripts/python.exe -X utf8 -m scripts.fit_match_weights [--out weights.json]
        [--schema dev] [--without model+claude+gemini] [--strength 0.001] [--save]
    .venv/Scripts/python.exe -X utf8 -m scripts.fit_match_weights --list | --activate N|hand
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from pathlib import Path

from bot.config import get_settings
from bot.db import tools
from bot.db.repo import Repo
from bot.services.game_link import GameLinker, _candidate, _Index, load_candidates
from bot.services.game_match import WEIGHTS, Candidate, compare, features, subject_of
from bot.services.match_fit import (
    LABEL_CLASS,
    Example,
    HeldOut,
    Weights,
    calibrated,
    changes,
    class_strengths,
    fit,
    gate,
    held_out,
    label_weight,
    macro,
    reliability,
    temperature,
    tempered,
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
        reverse, turned = None, False
        if a is not None and b is not None:
            # A directed label is learnt from its own side, the rest from
            # the side the linker picks; both are read when scoring.
            if label in ("same", "other"):
                a, b = subject_of(a, b)
            else:
                turned = subject_of(a, b)[0] is not a
            f, reverse = features(a, b, ordered=True), features(b, a, ordered=True)
        elif lab["features"]:
            f = json.loads(lab["features"])  # the versions are gone: what was seen then
        else:
            continue
        groups = tuple(
            ("game", games[v]["game_id"]) if v in games else ("version", v)
            for v in (lab["version_id"], lab["other_id"])
        )
        by = str(lab["decided_by"] or "?")
        found.append(
            Example(
                f,
                label,
                label_weight(by),
                by,
                groups,
                (lab["version_id"], lab["other_id"]),
                reverse,
                turned,
            )
        )
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
    database = await tools.open_database(schema=args.schema)
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

        if args.freeze_eval:
            frozen_pairs = sorted(e.pair for e in examples if e.operator and e.pair)
            _freeze(Path(args.freeze_eval), frozen_pairs)
            print(f"frozen: {len(frozen_pairs)} pairs → {args.freeze_eval}")
        frozen = _frozen(Path(args.eval or args.freeze_eval or _default_eval(args)))

        rows = held_out(examples, WEIGHTS, train=lambda e: e.source not in without, **kw)
        t = temperature(rows)
        sure, sure_n = reliability(rows)
        rows = [HeldOut(r.example, r.start, tempered(r.fitted, t)) for r in rows]
        sure_t, sure_t_n = reliability(rows)
        print(
            f"temperature {t:.2f}: p >= 0.95 right {sure:.1%} of {sure_n}"
            f" → {sure_t:.1%} of {sure_t_n}"
        )
        verdict = gate(rows, frozen)
        print("held out by game (right · log-loss), current → fitted:")
        for src, (was, now) in verdict.by_source.items():
            print(
                f"  {src:22} n={was.n:4}  {was.accuracy:5.1%} · {was.log_loss:.3f}"
                f"  →  {now.accuracy:5.1%} · {now.log_loss:.3f}"
            )
        print(f"recall per class on the yardstick ({verdict.yardstick}), current → fitted:")
        for c, (was, n) in verdict.recall_start.items():
            now = verdict.recall_fitted.get(c, (0.0, 0))[0]
            print(f"  {c:12} n={n:4}  {was:5.1%} → {now:5.1%}")
        print(
            f"  macro          {macro(verdict.recall_start):5.1%} → "
            f"{macro(verdict.recall_fitted):5.1%}"
        )
        print("judged as one game / related / other:")
        for c, (was, n) in verdict.coarse_recall_start.items():
            now = verdict.coarse_recall_fitted.get(c, (0.0, 0))[0]
            mark = "  LOST" if c in verdict.lost else ""
            print(f"  {c:12} n={n:4}  {was:5.1%} → {now:5.1%}{mark}")
        if verdict.viewer and verdict.viewer[0].n:
            was, now = verdict.viewer
            print(
                f"  viewer only  n={was.n:4}  {was.accuracy:5.1%} · {was.log_loss:.3f}"
                f"  →  {now.accuracy:5.1%} · {now.log_loss:.3f}"
            )
        print(
            f"all classes ({verdict.yardstick}): {verdict.start.accuracy:.1%} · "
            f"{verdict.start.log_loss:.3f} → {verdict.fitted.accuracy:.1%} · "
            f"{verdict.fitted.log_loss:.3f}"
        )
        was, now = verdict.coarse_start, verdict.coarse_fitted
        print(
            f"GATE ({verdict.yardstick}, coarse): {was.accuracy:.1%} · {was.log_loss:.3f}"
            f" → {now.accuracy:.1%} · {now.log_loss:.3f}"
            f" — {'PASSED' if verdict.passed else 'not passed'}"
        )
        if args.quick:
            return None

        fitted = calibrated(fit(learn, WEIGHTS, **kw), t)
        print("weights that moved most:")
        for cls, sign, was, now in changes(WEIGHTS, fitted, at_least=0.3)[:30]:
            print(f"  {cls:12} {sign:26} {was:+6.2f} → {now:+6.2f}")
        moves, shown = await population(repo, fitted)
        print(f"pairs the linker compares, not apart either way: {sum(moves.values())}")
        for move, n in moves.most_common(15):
            print(f"  {n:5}  {move if isinstance(move, str) else ' → '.join(move)}")
        for line in shown:
            print(f"    {line}")
        rounded = {
            c: {k: round(v, 2) for k, v in w.items() if round(v, 2)} for c, w in fitted.items()
        }
        if args.save:
            if verdict.passed:
                weights_id = await repo.add_match_weights(
                    rounded,
                    gate_before=verdict.start.accuracy,
                    gate_after=verdict.fitted.accuracy,
                    labels=len(learn),
                    note=args.note,
                    activate=True,
                )
                print(f"kept as set {weights_id} and made active; relink to apply")
                # The weights and the labels they were fitted on, as files
                # for git (`scripts/catalog_files.py`): every copy takes them.
                from scripts.catalog_files import export

                labels, _ = await export(repo)
                print(f"written to catalog/ with its {labels} labels: commit them")
            else:
                print("the gate did not pass: nothing kept")
        return rounded
    finally:
        await database.close()


def _freeze(path: Path, pairs: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pairs), encoding="utf-8")


def _frozen(path: Path) -> set[tuple[int, int]] | None:
    """The frozen yardstick's pairs, or None when there is none."""
    if not path.is_file():
        return None
    return {(int(a), int(b)) for a, b in json.loads(path.read_text(encoding="utf-8"))}


def _default_eval(args: argparse.Namespace) -> Path:
    """The frozen set beside the database: `advice/eval_set.json`."""
    return get_settings().db_path.parent / "advice" / "eval_set.json"


async def manage(args: argparse.Namespace) -> None:
    database = await tools.open_database(schema=args.schema)
    try:
        repo = Repo(database)
        if args.activate:
            await repo.activate_match_weights(
                None if args.activate == "hand" else int(args.activate)
            )
            print(f"active: {args.activate}; relink to apply")
        for row in await repo.match_weights_list():
            gate = f"{row['gate_before'] or 0:.1%} → {row['gate_after'] or 0:.1%}"
            mark = "*" if row["active"] else " "
            print(
                f"{mark} {row['weights_id']:3}  {row['created_at']}  gate {gate}"
                f"  labels {row['labels']}  {row['note'] or ''}"
            )
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="match_weights.fitted.json")
    tools.add_arguments(parser)
    parser.add_argument("--strength", type=float, default=0.0001)
    parser.add_argument("--epochs", type=int, default=3000, help="at most; stops when settled")
    parser.add_argument("--without", action="append", help="a source not to learn from")
    parser.add_argument("--save", action="store_true", help="keep and activate (gate passed)")
    parser.add_argument("--freeze-eval", help="write the operator's pairs as the yardstick")
    parser.add_argument("--eval", help="the frozen yardstick (default: advice/eval_set.json)")
    parser.add_argument("--quick", action="store_true", help="the scores only, nothing written")
    parser.add_argument("--note", default=None)
    parser.add_argument("--list", action="store_true", help="the sets kept")
    parser.add_argument("--activate", default=None, help="a kept set's id, or 'hand'")
    args = parser.parse_args()
    if args.list or args.activate:
        tools.run(manage(args))
        return
    fitted = tools.run(run(args))
    if fitted is not None:
        Path(args.out).write_text(json.dumps(fitted, indent=1), encoding="utf-8")
        print(f"written to {args.out}")


if __name__ == "__main__":
    main()
