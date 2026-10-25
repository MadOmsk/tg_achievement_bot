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


def test_the_bias_is_not_fitted() -> None:
    """Labels come from the review list: they say nothing of how often two
    versions are one game (the training audit, 2026-10-24)."""
    fitted = fit(_examples(), WEIGHTS, strength=0.0001, rate=0.2, epochs=200)
    assert all(fitted[c]["bias"] == WEIGHTS[c]["bias"] for c in fitted)


def test_a_class_with_few_labels_is_held_to_its_start() -> None:
    from bot.services.match_fit import FEW_LABELS, class_strengths

    examples = [*_examples(), Example({"bias": 1.0, "vr_word": 1.0}, "vr_of")]
    pulls = class_strengths(examples, 0.001)
    assert pulls["vr_of"] == 0.001 * FEW_LABELS
    assert pulls["same"] == 0.001 * FEW_LABELS / 12


def test_labels_about_one_game_are_held_out_together() -> None:
    from bot.services.match_fit import _folds

    examples = [
        Example({"bias": 1.0}, "same", groups=(("game", 1), ("game", 2))),
        Example({"bias": 1.0}, "same", groups=(("game", 2), ("game", 3))),
        Example({"bias": 1.0}, "other", groups=(("game", 4), ("game", 5))),
        Example({"bias": 1.0}, "other", groups=(("game", 6), ("game", 7))),
    ]
    fold = _folds(examples, 2, 147)
    assert fold[0] == fold[1]  # joined through game 2
    assert len(set(fold)) == 2


def test_the_gate_is_the_operators_labels() -> None:
    from bot.services.match_fit import gate, held_out

    examples = [
        Example(e.features, e.label, e.weight, "viewer", (("game", i),))
        for i, e in enumerate(_examples())
    ]
    verdict = gate(held_out(examples, WEIGHTS, strength=0.01, rate=0.2, epochs=300))
    assert verdict.fitted.n == len(examples)
    assert verdict.passed
    adviser = [Example(e.features, e.label, 0.4, "claude+gemini") for e in _examples()]
    assert gate(held_out(adviser, WEIGHTS, epochs=50)).fitted.n == 0


def test_a_sign_of_difference_never_speaks_for_one_game() -> None:
    """Labels where an undated version with another genre happened to be its
    namesake must not teach "unknown year" or "other genres" to mean one game
    (2026-10-25: Valve's Deadlock became LLL games' DeadLock)."""
    examples = [
        Example({"bias": 1.0, "year_unknown": 1.0, "genres_differ": 1.0}, "same") for _ in range(30)
    ]
    fitted = fit(examples, WEIGHTS)
    assert fitted["same"]["genres_differ"] <= 0.0
    assert fitted["same"]["year_unknown"] <= WEIGHTS["same"]["year_unknown"]
