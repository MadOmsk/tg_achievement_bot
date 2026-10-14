"""Fit the games matcher's weights to the operator's labels (#147, plan step 8).

Reads every label (`match_decisions`), works out each pair's signs as the
model reads them now — the label's own version as the subject, so "a is a
remaster of b" teaches the remaster's side — and fits the weights, pulled
towards the current ones. Prints how well the current and the fitted weights
answer held-out labels, and the weights that moved; writes the fitted weights
as JSON. Changes nothing: the weights are put into `game_match.WEIGHTS` by
hand, once they are judged better. The advisers' labels (Claude and Gemini
agreeing, `scripts/advise_pairs.py`) count `match_fit.ADVISER_WEIGHT` each,
the operator's whole; the counts per source are printed.

Read-only, safe beside a running bot.

Usage:
    .venv/Scripts/python.exe -X utf8 -m scripts.fit_match_weights [--out weights.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from bot.config import get_settings
from bot.db.repo import Database, Repo
from bot.services.game_link import load_candidates
from bot.services.game_match import WEIGHTS, features
from bot.services.match_fit import (
    LABEL_CLASS,
    Example,
    changes,
    cross_validate,
    fit,
    label_weight,
    score,
)

logging.basicConfig(level="WARNING")


async def examples_from(repo: Repo, sources: dict[str, int] | None = None) -> list[Example]:
    """Every label as an example; `sources` counts them by who gave them."""
    labels = await repo.all_decisions()
    ids = sorted({lab["version_id"] for lab in labels} | {lab["other_id"] for lab in labels})
    candidates = await load_candidates(repo, ids)
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
        found.append(Example(f, label, label_weight(lab["decided_by"])))
        if sources is not None:
            by = str(lab["decided_by"] or "?")
            sources[by] = sources.get(by, 0) + 1
    return found


async def load(sources: dict[str, int]) -> list[Example]:
    database = await Database(Path(get_settings().db_path)).connect()
    try:
        return await examples_from(Repo(database), sources)
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="match_weights.fitted.json")
    parser.add_argument("--strength", type=float, default=0.001)
    args = parser.parse_args()
    sources: dict[str, int] = {}
    examples = asyncio.run(load(sources))
    by_class: dict[str, int] = {}
    for e in examples:
        by_class[e.label] = by_class.get(e.label, 0) + 1
    print(f"labels: {len(examples)} {by_class}")
    print(
        "by source: "
        + ", ".join(f"{by} {n} (×{label_weight(by):g})" for by, n in sorted(sources.items()))
    )
    if len(examples) < 5:
        print("too few labels to fit anything yet")
        return
    before, after = cross_validate(examples, WEIGHTS, strength=args.strength)
    print(f"held out — current: {before.accuracy:.0%} right, log-loss {before.log_loss:.3f}")
    print(f"held out — fitted:  {after.accuracy:.0%} right, log-loss {after.log_loss:.3f}")
    fitted = fit(examples, WEIGHTS, strength=args.strength)
    print(f"all labels — fitted: {score(examples, fitted).accuracy:.0%} right")
    for cls, sign, was, now in changes(WEIGHTS, fitted):
        print(f"  {cls:12} {sign:26} {was:+6.2f} → {now:+6.2f}")
    rounded = {c: {k: round(v, 2) for k, v in w.items() if round(v, 2)} for c, w in fitted.items()}
    Path(args.out).write_text(json.dumps(rounded, indent=1), encoding="utf-8")
    print(f"written to {args.out}")


if __name__ == "__main__":
    main()
