"""Fitting the matcher's weights to the operator's labels (#147; plan step 8).
No database access: examples in, weights out.

The model is `game_match`'s: each class (one game, remaster, remake,
compilation, VR) sums its weights over a pair's signs, "other" is the
reference at 0, a softmax gives probabilities. Fitting is plain gradient
descent on the log-loss, **pulled towards the current weights** (an L2 term
around them, not around zero): with a few dozen labels the weights should
move only where the operator's answers clearly disagree with them.

**Labels weigh by who gave them** (owner, 2026-10-17): the operator's 0.9
(he errs too), the three advisers agreeing (Gemini Argon, GPT Pro, Sonnet —
`UNANIMOUS`, or the older model + Claude + Gemini) 0.8, two of three
(`MAJORITY`, or the older Claude + Gemini against the model) 0.4.

**How a fit is judged** (the training audit, 2026-10-24): on labels held
out **a whole group of games at a time** (`held_out`) — a random split
leaves the same game on both sides and flatters the fit by some 4 points —
and **by the operator's labels alone** (`gate`): the advisers' are reported,
never the gate. The bias is not fitted (`FROZEN`): labels picked from the
review list say nothing of how often two versions are one game. A class
with few labels is held closer to its start (`class_strengths`).
"""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from bot.services.advice import ADVISER_SOURCES, ALL_THREE, BOTH
from bot.services.game_match import CLASSES, probabilities

# What a label teaches, by who gave it (owner, 2026-10-17).
OPERATOR_WEIGHT = 0.9
UNANIMOUS_WEIGHT = 0.8
MAJORITY_WEIGHT = 0.4
# Two advisers (a Claude and a Gemini, with a web search) agreeing: right on
# 14 of 15 pairs the operator answered blind (2026-10-24).
BOTH_WEIGHT = 0.7
# Who gave a label in the full run: all three advisers, or two of the three.
UNANIMOUS = "advisers:3/3"
MAJORITY = "advisers:2/3"
ADVISER_WEIGHT = MAJORITY_WEIGHT  # the older name, kept for its callers

# Never fitted: how common each class is among labels is the review list's
# doing, not the catalog's (the training audit, 2026-10-24).
FROZEN = frozenset({"bias"})
# A class with fewer labels than this is pulled to its start that much
# harder (remake 10, compilation 8, VR 3 labels in October 2026).
FEW_LABELS = 40

# What an operator's label teaches about the pair: its class.
LABEL_CLASS = {
    "same": "same",
    "edition": "same",
    "demo_of": "same",
    "tool_of": "same",
    "mode_of": "same",
    "extra_of": "same",  # a soundtrack or an artbook is a part of its game
    "remaster_of": "remaster_of",
    "remake_of": "remake_of",
    "contains": "contains",
    "vr_of": "vr_of",
    "other": "other",
    "series": "other",  # another game of the series: not related
}

Weights = dict[str, dict[str, float]]


def label_weight(decided_by: str | None) -> float:
    """How much a label teaches: an adviser's less than the operator's, two
    of three advisers less than all three."""
    by = decided_by or ""
    if by in (UNANIMOUS, ALL_THREE):
        return UNANIMOUS_WEIGHT
    if by == BOTH:
        return BOTH_WEIGHT
    if by == MAJORITY or by in ADVISER_SOURCES:
        return MAJORITY_WEIGHT
    return OPERATOR_WEIGHT


@dataclass(slots=True)
class Example:
    features: dict[str, float]
    label: str  # a class: one of CLASSES or "other"
    weight: float = OPERATOR_WEIGHT  # `label_weight` of who gave it
    source: str = ""  # who gave it (`decided_by`)
    # What it is about — the games of its two versions: labels sharing one
    # are held out together.
    groups: tuple[object, ...] = field(default_factory=tuple)

    @property
    def operator(self) -> bool:
        return self.source not in (UNANIMOUS, MAJORITY) and self.source not in ADVISER_SOURCES


@dataclass(slots=True)
class Score:
    accuracy: float
    log_loss: float
    n: int


def score(examples: list[Example], weights: Weights) -> Score:
    """How well the weights answer the examples: the share whose likeliest
    class is the label, and the mean log-loss."""
    if not examples:
        return Score(0.0, 0.0, 0)
    right, loss = 0, 0.0
    for e in examples:
        probs = probabilities(e.features, weights)
        if max(probs, key=probs.__getitem__) == e.label:
            right += 1
        loss -= math.log(max(probs.get(e.label, 0.0), 1e-12))
    return Score(right / len(examples), loss / len(examples), len(examples))


def fit(
    examples: list[Example],
    start: Weights,
    *,
    strength: float = 0.001,
    rate: float = 0.5,
    epochs: int = 800,
    frozen: frozenset[str] = FROZEN,
    strengths: dict[str, float] | None = None,
) -> Weights:
    """Weights fitted to the examples, starting from and pulled towards
    `start` (`strength` per unit of squared distance). The step and the
    passes are large enough to settle (2026-10-13: at 0.05 × 400 a sign
    seen on a tenth of the labels barely moved off its start — the text
    signs, starting at 0, could not show what they are worth). The pull
    is weak: held out, 0.02 → 80%, 0.005 → 83%, 0.001 → 85% right on 677
    labels — the labels, not the start, should speak. `frozen` signs keep
    their start; `strengths` gives a class its own pull (`class_strengths`)."""
    signs = sorted(
        {k for e in examples for k in e.features} | {k for c in CLASSES for k in start[c]}
    )
    w = {c: {k: start[c].get(k, 0.0) for k in signs} for c in CLASSES}
    if not examples:
        return w
    n = sum(e.weight for e in examples) or 1.0
    for _ in range(epochs):
        grad = {c: dict.fromkeys(signs, 0.0) for c in CLASSES}
        for e in examples:
            probs = probabilities(e.features, w)
            for c in CLASSES:
                error = probs[c] - (1.0 if e.label == c else 0.0)
                if error:
                    for k, x in e.features.items():
                        grad[c][k] += e.weight * error * x / n
        # A step on the labels, then the pull back towards the start taken
        # exactly (a proximal step): stable however strong the pull.
        for c in CLASSES:
            pull = (strengths or {}).get(c, strength)
            shrink = 1.0 + 2 * rate * pull
            for k in signs:
                if k in frozen:
                    continue
                moved = w[c][k] - rate * grad[c][k]
                w[c][k] = (moved + 2 * rate * pull * start[c].get(k, 0.0)) / shrink
    return w


def cross_validate(
    examples: list[Example], start: Weights, *, folds: int = 5, seed: int = 147, **kw: float
) -> tuple[Score, Score]:
    """(the start's score, the fitted weights' score) on held-out folds: each
    fold answered by weights fitted on the others."""
    order = list(examples)
    random.Random(seed).shuffle(order)
    folds = max(2, min(folds, len(order)))
    held: list[tuple[Example, Weights]] = []
    for i in range(folds):
        test = order[i::folds]
        train = [e for j, e in enumerate(order) if j % folds != i]
        fitted = fit(train, start, **kw)  # type: ignore[arg-type]
        held += [(e, fitted) for e in test]
    before = score(order, start)
    right = sum(
        1 for e, w in held if max((p := probabilities(e.features, w)), key=p.__getitem__) == e.label
    )
    loss = -sum(
        math.log(max(probabilities(e.features, w).get(e.label, 0.0), 1e-12)) for e, w in held
    )
    after = Score(right / len(held), loss / len(held), len(held)) if held else Score(0, 0, 0)
    return before, after


def changes(
    start: Weights, fitted: Weights, *, at_least: float = 0.1
) -> list[tuple[str, str, float, float]]:
    """`(class, sign, before, after)` for every weight that moved."""
    found = []
    for c in CLASSES:
        for k, after in fitted[c].items():
            before = start[c].get(k, 0.0)
            if abs(after - before) >= at_least:
                found.append((c, k, before, after))
    return sorted(found, key=lambda t: -abs(t[3] - t[2]))


def class_strengths(examples: list[Example], strength: float) -> dict[str, float]:
    """Each class's pull: `strength`, times how far short of `FEW_LABELS`
    its labels fall — a class seen three times keeps its start."""
    seen = Counter(e.label for e in examples)
    return {c: strength * max(1.0, FEW_LABELS / max(seen[c], 1)) for c in CLASSES}


@dataclass(slots=True)
class HeldOut:
    example: Example
    start: dict[str, float]  # the start's probabilities
    fitted: dict[str, float]  # those of weights fitted without its group


def _folds(examples: list[Example], folds: int, seed: int) -> list[int]:
    """Each example's fold: labels joined by a game, however indirectly, in
    one fold; folds balanced by size."""
    parent: dict[object, object] = {}

    def find(x: object) -> object:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    keys = []
    for i, e in enumerate(examples):
        key = e.groups[0] if e.groups else ("example", i)
        for g in e.groups[1:]:
            parent[find(g)] = find(key)
        keys.append(key)
    roots = [find(k) for k in keys]
    sizes = Counter(roots)
    order = sorted(sizes, key=str)
    random.Random(seed).shuffle(order)
    load = [0] * folds
    fold_of: dict[object, int] = {}
    for root in sorted(order, key=lambda r: -sizes[r]):
        i = load.index(min(load))
        fold_of[root] = i
        load[i] += sizes[root]
    return [fold_of[r] for r in roots]


def held_out(
    examples: list[Example],
    start: Weights,
    *,
    folds: int = 5,
    seed: int = 147,
    train: Callable[[Example], bool] | None = None,
    **kw: Any,
) -> list[HeldOut]:
    """Every example answered by the start and by weights fitted on the
    other folds (grouped by game, see `_folds`). `train` picks what a fit
    may learn from; every example is still answered."""
    folds = max(2, min(folds, len(examples)))
    fold = _folds(examples, folds, seed)
    out: list[HeldOut] = []
    for i in range(folds):
        learn = [
            e for e, f in zip(examples, fold, strict=True) if f != i and (train is None or train(e))
        ]
        fitted = fit(learn, start, **kw)
        out += [
            HeldOut(e, probabilities(e.features, start), probabilities(e.features, fitted))
            for e, f in zip(examples, fold, strict=True)
            if f == i
        ]
    return out


def _score(rows: list[tuple[Example, dict[str, float]]]) -> Score:
    if not rows:
        return Score(0.0, 0.0, 0)
    right = sum(1 for e, p in rows if max(p, key=p.__getitem__) == e.label)
    loss = -sum(math.log(max(p.get(e.label, 0.0), 1e-12)) for e, p in rows)
    return Score(right / len(rows), loss / len(rows), len(rows))


@dataclass(slots=True)
class Gate:
    start: Score  # the operator's held-out labels, the start's answers
    fitted: Score  # … the fitted weights'
    by_source: dict[str, tuple[Score, Score]]

    @property
    def passed(self) -> bool:
        """The fit answers the operator better: a lower log-loss, and no
        fewer right."""
        return (
            self.fitted.n > 0
            and self.fitted.log_loss < self.start.log_loss
            and self.fitted.accuracy >= self.start.accuracy
        )


def gate(rows: list[HeldOut]) -> Gate:
    """Whether fitted weights may replace the start: judged on the
    operator's labels only; every source's scores beside, for reading."""
    by: dict[str, list[HeldOut]] = {}
    for r in rows:
        by.setdefault(r.example.source or "?", []).append(r)
    operator = [r for r in rows if r.example.operator]
    return Gate(
        _score([(r.example, r.start) for r in operator]),
        _score([(r.example, r.fitted) for r in operator]),
        {
            src: (
                _score([(r.example, r.start) for r in rs]),
                _score([(r.example, r.fitted) for r in rs]),
            )
            for src, rs in sorted(by.items())
        },
    )
