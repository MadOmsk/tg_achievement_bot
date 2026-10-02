"""A guide is cut into blocks at its achievements' names, and the model's pointers
into a block are checked before a single line is used."""

from __future__ import annotations

from bot.services.translate.guide_tips import (
    MAX_SECTION_LINES,
    MIN_NAMED,
    blocks_of,
    locate_sections,
    parse_blocks,
)

LINES = (
    "Intro",
    "Clincher",
    "100 enemies shot in the head.",
    "Aim for the head.",
    "Bingo",
    "Experience every effect.",
    "Bleeding - get hurt.",
    "Sleep - do not sleep.",
    "Done",
    "Goss",
    "Sit by a campfire.",
)
MARKS = {1: 1, 4: 2, 9: 3}


def test_a_guide_is_cut_from_each_name_to_the_next() -> None:
    # (achievement, first line, last line); the name itself is not in its block.
    assert blocks_of(LINES, MARKS) == [(1, 2, 3), (2, 5, 8), (3, 10, 10)]


def test_a_name_with_nothing_under_it_has_no_block() -> None:
    lines = ("A", "B", "Text of B.")
    assert blocks_of(lines, {0: 1, 1: 2}) == [(2, 2, 2)]


def test_an_answer_is_read_in_the_whole_guides_lines() -> None:
    blocks = blocks_of(LINES, MARKS)
    reply = "\n".join(
        [
            "1 § 2 § 2",  # Clincher: the second line of its block -> line 3
            "2 § 2 § 3",  # Bingo: lines 6..7 of the guide
            "2 § 4 § 4",  # a second piece of it, line 8
            "3 § 1 § 1 §",  # a stray closing separator -> line 10
            "3 § 1 § 9",  # outside its block
            "9 § 1 § 1",  # no such block
            "1 § 3 § 2",  # last before first
            "Here are the pieces:",
        ]
    )
    assert parse_blocks(reply, blocks) == {1: [(3, 3)], 2: [(6, 7), (8, 8)], 3: [(10, 10)]}


def test_pieces_of_one_achievement_never_overlap() -> None:
    blocks = blocks_of(LINES, MARKS)
    assert parse_blocks("2 § 1 § 3\n2 § 2 § 4", blocks) == {2: [(5, 7)]}


def test_a_block_longer_than_the_cap_is_cut_off_at_it() -> None:
    blocks = [(1, 1, MAX_SECTION_LINES + 10)]
    reply = f"1 § 1 § {MAX_SECTION_LINES}\n1 § {MAX_SECTION_LINES + 1} § {MAX_SECTION_LINES + 5}"
    assert parse_blocks(reply, blocks) == {1: [(1, MAX_SECTION_LINES)]}


async def test_a_guide_naming_too_few_achievements_is_not_asked_about() -> None:
    marks = {i: i + 1 for i in range(MIN_NAMED - 1)}
    assert await locate_sections("key", LINES, [("A", "")] * 3, marks) == {}
    assert await locate_sections("key", LINES, [("A", "")] * 3, {}) == {}
