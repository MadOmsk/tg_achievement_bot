"""Labels that contradict each other (#218 step 5)."""

from __future__ import annotations

from bot.services.label_conflicts import around, conflicts


def _rows(*labels: tuple[int, int, str]) -> list[dict]:
    return [{"version_id": a, "other_id": b, "relation": r} for a, b, r in labels]


def test_apart_yet_joined_by_a_chain() -> None:
    """A remaster label inside a group the same-game labels make."""
    found = conflicts(_rows((1, 2, "same"), (2, 3, "enhanced_of"), (3, 1, "remaster_of")))
    assert [c.kind for c in found] == ["apart_in_group"]
    assert found[0].label == (3, 1, "remaster_of")
    assert {lab[2] for lab in found[0].against} == {"same", "enhanced_of"}


def test_two_groups_said_two_things() -> None:
    """A remaster and a remake between one pair of groups; one relation
    both ways; a relation and "another game"."""
    rows = _rows(
        (1, 2, "same"),
        (3, 4, "same"),
        (1, 3, "remaster_of"),
        (2, 4, "remake_of"),
        (5, 6, "remaster_of"),
        (6, 5, "remaster_of"),
        (7, 8, "contains"),
        (8, 7, "other"),
    )
    assert sorted(c.label for c in conflicts(rows)) == [
        (2, 4, "remake_of"),
        (6, 5, "remaster_of"),
        (8, 7, "other"),
    ]


def test_agreeing_labels_are_no_contradiction() -> None:
    rows = _rows(
        (1, 2, "same"),
        (3, 4, "same"),
        (1, 3, "remaster_of"),
        (2, 4, "remaster_of"),
        (5, 6, "other"),
        (6, 5, "series"),
    )
    assert conflicts(rows) == []


def test_around_a_label() -> None:
    found = conflicts(_rows((1, 2, "same"), (2, 1, "other"), (5, 6, "vr_of"), (6, 5, "vr_of")))
    assert [c.label for c in around(found, [1])] == [(2, 1, "other")]
