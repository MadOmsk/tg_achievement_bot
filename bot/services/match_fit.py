"""Fitting the matcher's weights to the operator's labels (#147; plan step 8).
No database access: examples in, weights out.

The model is `game_match`'s: each class (one game, remaster, remake,
compilation, VR) sums its weights over a pair's signs, "other" is the
reference at 0, a softmax gives probabilities. Fitting is plain gradient
descent on the log-loss, **pulled towards the current weights** (an L2 term
around them, not around zero): with a few dozen labels the weights should
move only where the operator's answers clearly disagree with them.

**Labels weigh by who gave them** (owner, 2026-10-12): the operator's own
count whole, the advisers' (`advice.ADVISER_SOURCES`: Claude and Gemini
agreeing, with or without the model) count `ADVISER_WEIGHT` — two language
models agreeing is evidence, not the operator's word.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from bot.services.advice import ADVISER_SOURCES
from bot.services.game_match import CLASSES, probabilities

# What one adviser-made label weighs against one of the operator's (1.0).
OPERATOR_WEIGHT = 1.0
ADVISER_WEIGHT = 0.6

# What an operator's label teaches about the pair: its class.
LABEL_CLASS = {
    "same": "same",
    "edition": "same",
    "demo_of": "same",
    "tool_of": "same",
    "mode_of": "same",
    "remaster_of": "remaster_of",
    "remake_of": "remake_of",
    "contains": "contains",
    "vr_of": "vr_of",
    "other": "other",
    "series": "other",  # another game of the series: not related
}

Weights = dict[str, dict[str, float]]


def label_weight(decided_by: str | None) -> float:
    """How much a label teaches: an adviser's less than the operator's."""
    return ADVISER_WEIGHT if (decided_by or "") in ADVISER_SOURCES else OPERATOR_WEIGHT


@dataclass(slots=True)
class Example:
    features: dict[str, float]
    label: str  # a class: one of CLASSES or "other"
    weight: float = OPERATOR_WEIGHT  # `label_weight` of who gave it


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
    strength: float = 0.05,
    rate: float = 0.05,
    epochs: int = 400,
) -> Weights:
    """Weights fitted to the examples, starting from and pulled towards
    `start` (`strength` per unit of squared distance)."""
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
        shrink = 1.0 + 2 * rate * strength
        for c in CLASSES:
            for k in signs:
                moved = w[c][k] - rate * grad[c][k]
                w[c][k] = (moved + 2 * rate * strength * start[c].get(k, 0.0)) / shrink
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
