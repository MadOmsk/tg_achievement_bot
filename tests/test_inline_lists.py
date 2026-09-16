"""Shared keyboard-list rendering used by /who, /panel, /hltb and /admin.

The arithmetic here used to live in three screens at once, so these tests
are about the cases where those three disagreed: what an out-of-range page
does, what an empty list does, and whether a paginated row still knows its
place in the *whole* list rather than in its own page.
"""

from __future__ import annotations

from bot.views.inline_lists import (
    InlineListing,
    arrow_nav,
    button_rows,
    counted_nav,
    paginate,
)

BACK = "a:home"


def _callbacks(markup) -> list[list[str]]:
    return [[button.callback_data for button in row] for row in markup.inline_keyboard]


def test_one_button_per_row_by_default() -> None:
    rows = button_rows(["a", "b", "c"], str, lambda item: f"pick:{item}")
    assert [[b.callback_data for b in row] for row in rows] == [
        ["pick:a"],
        ["pick:b"],
        ["pick:c"],
    ]


def test_per_row_packs_the_grid_and_allows_a_short_last_row() -> None:
    """/who's picker: three across, because a chat with twenty members would
    otherwise be twenty rows deep."""
    rows = button_rows(range(7), str, lambda n: f"who:stats:{n}", per_row=3)
    assert [len(row) for row in rows] == [3, 3, 1]


def test_listing_puts_navigation_above_the_way_out() -> None:
    listing = InlineListing(
        rows=button_rows(["a"], str, lambda item: f"pick:{item}"),
        nav=[*arrow_nav(paginate(["a", "b"], 0, 1), "a:users:")],
        tail=[button for button in button_rows([BACK], lambda _: "Назад", str)[0]],
    )
    assert _callbacks(listing.markup()) == [["pick:a"], ["a:users:1"], [BACK]]


def test_listing_without_navigation_or_tail_is_just_its_rows() -> None:
    listing = InlineListing(rows=button_rows(["a"], str, lambda item: f"pick:{item}"))
    assert _callbacks(listing.markup()) == [["pick:a"]]


def test_a_page_keeps_each_row_index_in_the_whole_list() -> None:
    """/hltb's suggestions are looked up by their index in the *whole* list —
    a page's own 0..N offsets would pick the wrong game entirely."""
    names = [f"game{i}" for i in range(12)]
    second = paginate(list(enumerate(names)), 1, 5)
    rows = button_rows(second.items, lambda item: item[1], lambda item: f"hltb:qr:{item[0]}")
    assert [row[0].callback_data for row in rows] == [f"hltb:qr:{i}" for i in range(5, 10)]


def test_the_last_page_is_short_rather_than_padded() -> None:
    page = paginate(list(range(12)), 2, 5)
    assert page.items == [10, 11]
    assert (page.number, page.count) == (2, 3)


def test_an_out_of_range_page_is_clamped_into_the_list() -> None:
    """Each of the three screens that did this arithmetic had its own answer;
    the one that cannot show an empty keyboard is the right one."""
    assert paginate(list(range(12)), 99, 5).number == 2
    assert paginate(list(range(12)), -3, 5).number == 0


def test_an_empty_list_is_one_empty_page_not_zero_pages() -> None:
    page = paginate([], 0, 5)
    assert (page.items, page.number, page.count) == ([], 0, 1)
    assert not page.has_pages


def test_neither_navigation_shape_appears_on_a_single_page() -> None:
    page = paginate(list(range(3)), 0, 5)
    assert counted_nav(page, "hltb:page:") is None
    assert arrow_nav(page, "a:users:") is None


def test_counted_navigation_carries_the_page_number_between_its_arrows() -> None:
    first, middle, last = (paginate(list(range(12)), n, 5) for n in (0, 1, 2))
    assert [b.text for b in counted_nav(first, "hltb:page:")] == ["1/3", "▶️"]
    assert [b.text for b in counted_nav(middle, "hltb:page:")] == ["◀️", "2/3", "▶️"]
    assert [b.text for b in counted_nav(last, "hltb:page:")] == ["◀️", "3/3"]


def test_counted_navigation_points_at_the_neighbouring_pages() -> None:
    nav = counted_nav(paginate(list(range(12)), 1, 5), "hltb:rpage:")
    assert [b.callback_data for b in nav] == ["hltb:rpage:0", "hltb:noop", "hltb:rpage:2"]


def test_arrow_navigation_drops_the_arrow_it_has_nowhere_to_point() -> None:
    """The admin's roster carries its page count in the header text instead,
    so its row is arrows only — and only the ones that lead somewhere."""
    first, middle, last = (paginate(list(range(12)), n, 5) for n in (0, 1, 2))
    assert [b.text for b in arrow_nav(first, "a:users:")] == ["›"]
    assert [b.text for b in arrow_nav(middle, "a:users:")] == ["‹", "›"]
    assert [b.text for b in arrow_nav(last, "a:users:")] == ["‹"]
