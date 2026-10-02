"""Nicknames (#157): the only name a person is shown by.

Pure rules, no database: what a nickname may look like, how it is shown, how a
first one is made for somebody who never chose, and which four digits a taken
nickname gets. The storage and the claim loop are in `db/repo/_handles.py`.
"""

from __future__ import annotations

import random
import re
from collections.abc import Iterable
from dataclasses import dataclass

HANDLE_MIN = 3
HANDLE_MAX = 20
# Once per this many days, after the first choice (which is free).
CHANGE_COOLDOWN_DAYS = 30
FALLBACK_HANDLE = "Player"

_VALID = re.compile(rf"[A-Za-z0-9]{{{HANDLE_MIN},{HANDLE_MAX}}}")
_NOT_ALNUM = re.compile(r"[^A-Za-z0-9]+")


@dataclass(frozen=True, slots=True)
class Handle:
    """A nickname as stored: what was typed and the digits added to it, if any."""

    name: str
    number: int = 0

    @property
    def display(self) -> str:
        return f"{self.name}#{self.number:04d}" if self.number else self.name


def is_valid(name: str) -> bool:
    """Latin letters and digits only, 3-20 of them. `fullmatch`, so a trailing
    newline does not slip through."""
    return _VALID.fullmatch(name) is not None


def normalize(name: str) -> str:
    """The form uniqueness is judged on: `RideTheSun` and `ridethesun` are one."""
    return name.lower()


def from_text(*candidates: str | None) -> str:
    """A first nickname for somebody who never chose: the first candidate (a
    Telegram username, a platform nickname) that keeps three or more characters
    once everything but Latin letters and digits is stripped, cut to 20."""
    for text in candidates:
        if not text:
            continue
        stripped = _NOT_ALNUM.sub("", text)[:HANDLE_MAX]
        if len(stripped) >= HANDLE_MIN:
            return stripped
    return FALLBACK_HANDLE


def random_numbers(taken: Iterable[int] = (), *, count: int = 20) -> list[int]:
    """Four-digit candidates for a nickname somebody else already holds, none of
    them in `taken`. Several at once so the caller can try the next on a race."""
    banned = set(taken)
    pool = [n for n in random.sample(range(1000, 10000), count + len(banned)) if n not in banned]
    return pool[:count]
