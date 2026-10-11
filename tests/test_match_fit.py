"""Fitting the matcher's weights to the operator's labels (#147, step 8)."""

from __future__ import annotations

from bot.services.game_match import WEIGHTS
from bot.services.match_fit import Example, changes, cross_validate, fit, score


def _examples() -> list[Example]:
    """The operator keeps saying that a pair showing `numbers_differ` with a
    very alike name is still one game — the current weights say otherwise."""
    one = {"bias": 1.0, "name": 0.2, "numbers_differ": 1.0, "years_near": 1.0}
    other = {"bias": 1.0, "name": -0.5, "years_gap": 5.0}
    return [Example(dict(one), "same") for _ in range(12)] + [
        Example(dict(other), "other") for _ in range(12)
    ]


def test_fitting_moves_the_weights_the_labels_disagree_with() -> None:
    examples = _examples()
    assert score(examples, WEIGHTS).accuracy < 1.0
    fitted = fit(examples, WEIGHTS, strength=0.01, rate=0.2, epochs=600)
    assert score(examples, fitted).accuracy == 1.0
    moved = {(c, k) for c, k, _, _ in changes(WEIGHTS, fitted)}
    assert ("same", "numbers_differ") in moved


def test_a_strong_pull_keeps_the_weights_where_they_are() -> None:
    fitted = fit(_examples(), WEIGHTS, strength=100.0, epochs=200)
    assert not changes(WEIGHTS, fitted, at_least=0.05)


def test_held_out_labels_tell_whether_fitting_helps() -> None:
    before, after = cross_validate(_examples(), WEIGHTS, strength=0.01, rate=0.2, epochs=400)
    assert after.accuracy >= before.accuracy
