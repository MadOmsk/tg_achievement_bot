"""The platforms' answers about achievements, kept whole (#147; owner,
2026-10-15: every field, as the stores' answers are). What each poll parses
is a part of what came; the rest — Xbox's `groupIds`, achievement types,
time windows, Steam's grey icons and stats, PSN's progress targets and
rewards — was dropped at the door, and learning it later meant asking again.

The platform clients know nothing of the database, so they hand an answer
to `keep`, and the bot's assembly points `keep` at the store of raw answers
(`set_sink(repo.save_payload)`: compressed, the latest per subject, not
rewritten while it does not change). With no sink — tests, scripts — it does
nothing. A failure to keep never fails the request it rode on."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger(__name__)

Sink = Callable[[str, str, Any], Awaitable[object]]
_sink: Sink | None = None


def set_sink(sink: Sink | None) -> None:
    global _sink
    _sink = sink


async def keep(subject: str, source: str, payload: Any) -> None:
    if _sink is None or payload is None:
        return
    try:
        await _sink(subject, source, payload)
    except Exception:
        log.warning("could not keep the %s answer for %s", source, subject, exc_info=True)
