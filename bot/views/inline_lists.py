"""The lists this bot renders as a keyboard, and what they have in common.

The same idea as `views/lists.py`, one layer over. There a list's rows are
text and the question is how they are wrapped; here the rows *are* the
keyboard, because every one of them has to be tappable. Which of the two a
screen wants is a rendering decision, not a data one — the admin's user list
is deliberately both at once, one loop feeding a text row and a button row
for each person, so the roster can be skimmed and still be tapped.

A list here is rows of buttons, sometimes a navigation row, and a trailing
row that is the way out — "назад" or "отмена". Nothing here decides a label:
what a row is called is each screen's own job, the same way `Listing` never
builds a text row.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


@dataclass(frozen=True)
class InlineListing:
    """One keyboard-shaped list, whole: its rows, its navigation, its way out.

    The three are named rather than positional because each is a decision some
    screen makes differently — `/who` has no navigation at all, `/hltb` ends
    in "отмена" where the admin's screens end in "назад".
    """

    rows: list[list[InlineKeyboardButton]]
    nav: list[InlineKeyboardButton] | None = None
    tail: list[InlineKeyboardButton] | None = None

    def markup(self) -> InlineKeyboardMarkup:
        rows = [*self.rows]
        if self.nav:
            rows.append(self.nav)
        if self.tail:
            rows.append(self.tail)
        return InlineKeyboardMarkup(inline_keyboard=rows)


def button_rows[T](
    items: Sequence[T],
    label: Callable[[T], str],
    callback: Callable[[T], str],
    *,
    per_row: int = 1,
) -> list[list[InlineKeyboardButton]]:
    """One button per item, `per_row` of them to a row.

    One per row is the default because almost every list here is read as a
    column of names; `/who`'s picker is the exception, where three fit and a
    chat with twenty members would otherwise be twenty rows deep.
    """
    buttons = [
        InlineKeyboardButton(text=label(item), callback_data=callback(item)) for item in items
    ]
    return [buttons[start : start + per_row] for start in range(0, len(buttons), per_row)]


@dataclass(frozen=True)
class Page[T]:
    """One page of a list, and the arithmetic every paginated screen used to
    do for itself — `-(-len(items) // size)` was written three times over,
    each with its own idea of what an out-of-range page should do."""

    items: list[T]
    number: int
    count: int

    @property
    def has_pages(self) -> bool:
        return self.count > 1


def paginate[T](items: Sequence[T], page: int, size: int) -> Page[T]:
    """The page actually shown, clamped into range. An empty list is one empty
    page, not zero pages: every caller then asks the same `has_pages` question
    without a special case for "nothing here yet"."""
    count = max(1, -(-len(items) // size))
    number = max(0, min(page, count - 1))
    start = number * size
    return Page(list(items[start : start + size]), number, count)


def page_nav[T](page: Page[T], prefix: str, *, noop: str) -> list[InlineKeyboardButton] | None:
    """`◀️ 2/5 ▶️` — where you are and how much is left, next to the arrows
    that act on it.

    One shape for every paginated list (2026-09-16, owner decision). There
    were two: this one, and the admin roster's bare `‹ ›` with its page count
    in the header text. Same job, two looks — the count moved here, where it
    is read in the same glance as the arrow it decides to press.

    `noop` is the counter's own callback, which does nothing but stop
    Telegram's spinner. It is per-screen rather than one shared value because
    every callback here lives in its screen's own namespace (`a:`, `hltb:`),
    and a counter answering another screen's router is exactly the kind of
    cross-wiring that namespace prevents.
    """
    if not page.has_pages:
        return None
    row = []
    if page.number > 0:
        row.append(InlineKeyboardButton(text="◀️", callback_data=f"{prefix}{page.number - 1}"))
    row.append(InlineKeyboardButton(text=f"{page.number + 1}/{page.count}", callback_data=noop))
    if page.number < page.count - 1:
        row.append(InlineKeyboardButton(text="▶️", callback_data=f"{prefix}{page.number + 1}"))
    return row
