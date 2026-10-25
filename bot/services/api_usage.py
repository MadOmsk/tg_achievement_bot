"""How many requests each outside API took, over the last 5 minutes, hour and
day — what the super-admin's home shows (owner, 2026-10-12).

Every request to Xbox, Steam, PSN and Anthropic is noted here as it is made:
Xbox's under the person whose token it rides on, since Microsoft's budget is
each person's own (300 per 5 minutes); Anthropic's with the tokens its answer
says it spent. Kept in memory for 24 hours, like the rate limiters beside it:
a restart starts the counts over, which is fine for a diagnostic.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

XBOX, STEAM, PSN, ANTHROPIC = "xbox", "steam", "psn", "anthropic"
# Not APIs, kept the same way: entries the octopus handled, and failed.
OCTOPUS, OCTOPUS_FAILED = "octopus", "octopus_failed"

FIVE_MINUTES, HOUR, DAY = 300.0, 3600.0, 86400.0
WINDOWS = (FIVE_MINUTES, HOUR, DAY)


@dataclass(frozen=True, slots=True)
class _Call:
    at: float
    key: int | None
    tokens: int


_calls: dict[str, deque[_Call]] = {}


def _now() -> float:
    return time.monotonic()


def _log(api: str) -> deque[_Call]:
    calls = _calls.setdefault(api, deque())
    cutoff = _now() - DAY
    while calls and calls[0].at < cutoff:
        calls.popleft()
    return calls


def record(api: str, key: int | None = None, *, tokens: int = 0) -> None:
    """One request to `api` — for `key` (a person) where its budget is a
    person's, with the `tokens` it spent where it spends them."""
    _log(api).append(_Call(_now(), key, tokens))


def count(api: str, span: float) -> int:
    since = _now() - span
    return sum(1 for call in _log(api) if call.at >= since)


def tokens(api: str, span: float) -> int:
    since = _now() - span
    return sum(call.tokens for call in _log(api) if call.at >= since)


def per_key(api: str, span: float) -> dict[int, int]:
    """Requests in the window, per key that made any."""
    since = _now() - span
    found: dict[int, int] = {}
    for call in _log(api):
        if call.at >= since and call.key is not None:
            found[call.key] = found.get(call.key, 0) + 1
    return found


def reset() -> None:
    """Forget everything — tests only."""
    _calls.clear()
