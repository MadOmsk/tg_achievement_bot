"""Shared list rendering for Telegram messages: /stats, /recent, /summary
and the daily itog all show a ranked or ordered list of rows.

Used to be a `<pre>` monospace table with padded columns — dropped: it reads
as a code block (grey background, wraps badly on a narrow phone screen), not
as a leaderboard or a list of games. A `<blockquote expandable>` of plain
lines is the Telegram-native shape for "here's a report section, tap to see
the rest" (SPEC 6.3, 7.3) — no column alignment attempted, each row is just
a readable sentence.
"""

from __future__ import annotations

# A long name doesn't get cut off gracefully — it wraps the whole line onto a
# second one on a phone screen (found live: a game called "Minecraft Legends
# - Windows" did exactly this in the old table). Generous compared to the old
# table's 20: a plain line has room a rigid column didn't.
NAME_LIMIT = 28


def truncate_name(name: str, limit: int = NAME_LIMIT) -> str:
    return name if len(name) <= limit else name[: limit - 1].rstrip() + "…"


def blockquote(rows: list[str], *, expandable: bool = True) -> str:
    """Wraps already-built, already-HTML-escaped lines in a Telegram
    blockquote. `expandable=False` for a view reached by an explicit
    "показать всех" tap (SPEC 6.3) — collapsing it again would undo the
    point of asking for the uncapped list.
    """
    tag = "<blockquote expandable>" if expandable else "<blockquote>"
    return tag + "\n".join(rows) + "</blockquote>"


def total_line(label: str, text: str) -> str:
    """The one line every list's summary starts with, highlighted the same
    way everywhere so it reads as a total, not another row (now placed
    *before* the list it summarizes, not after — SPEC 6.3, 7.3)."""
    return f"<b>{label}:</b> {text}"


def resolve_display_name(
    *,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    gamertag: str | None = None,
) -> str | None:
    """The Telegram identity, not a platform gamertag (Follow-up 2026-09-06,
    originally /stats' header only) — @username, else first+last name, else
    a platform display name as a last resort. Shared by /stats' header,
    /online's rows, and /summary's leaderboard rows (Follow-up 2026-09-08)
    so a Steam/PSN-only person — who has no `gamertag` at all — reads as
    themselves everywhere instead of a bare `idNNNN` in some views and their
    Telegram name in others.

    Returns None when nothing at all is known yet (a fresh connection with
    no message ever seen and no gamertag) — callers pick their own last
    resort, same as before this was pulled out into one place.
    """
    if username:
        return f"@{username}"
    full_name = " ".join(part for part in (first_name, last_name) if part)
    if full_name:
        return full_name
    if gamertag:
        return gamertag
    return None
