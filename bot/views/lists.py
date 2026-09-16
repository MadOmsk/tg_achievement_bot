"""The lists this bot renders, and what they have in common (#64).

A list here is a header, its rows, sometimes a total line above them, a cap,
and a wrapper. The wrapper is *usually* a collapsible blockquote — a report
section you tap to open, which is Telegram's own shape for it and reads far
better than the monospace table this used to be — but that is a default, not
the definition: `/online` is a list too and is not quoted.

What is deliberately **not** shared is the row. A list of games and a list of
people are different things, and forcing both through one template would
make every future change to one of them a change to the other. Each kind of
list keeps its own row renderer here, side by side, where the difference is
visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape as html_escape

from bot.constants import Platform, PsnTrophyTier
from bot.views.parts import (
    PLATFORM_ICON,
    TROPHY_TIER_BADGE,
    plural_achievements,
    plural_trophies,
    score_suffix,
)

# A long name does not get cut off gracefully — it wraps the whole line onto
# a second one on a phone screen (found live: a game called "Minecraft
# Legends - Windows" did exactly this in the old table). Generous compared to
# that table's 20: a plain line has room a rigid column did not.
NAME_LIMIT = 28


def truncate_name(name: str, limit: int = NAME_LIMIT) -> str:
    return name if len(name) <= limit else name[: limit - 1].rstrip() + "…"


def blockquote(rows: list[str], *, expandable: bool = True) -> str:
    """Wraps already-built, already-escaped lines in a Telegram blockquote.
    `expandable=False` for a list reached by an explicit "показать всех" tap
    (SPEC 6.3) — collapsing it again would undo the point of asking."""
    tag = "<blockquote expandable>" if expandable else "<blockquote>"
    return tag + "\n".join(rows) + "</blockquote>"


@dataclass(frozen=True)
class Listing:
    """One list, whole: what it is called, its rows, and how it is wrapped.

    The pieces are named rather than positional because each of them is a
    decision some list makes differently — /online has no header line of its
    own shape, the leaderboard puts a total above its rows, the games lists
    have neither. Nothing here builds a row: that is each list's own job (see
    `game_rows` below and the row renderers in views/chat.py and
    views/summary.py).
    """

    rows: list[str]
    header: str | None = None
    total: str | None = None
    #: A collapsible quote is the default because most of these are report
    #: sections somebody taps open. /online is the exception that made this a
    #: field: it is redrawn every few minutes and has to stay readable at a
    #: glance, so it is never quoted.
    quoted: bool = True
    expandable: bool = True

    def body(self) -> str:
        """The rows and their wrapper, without the header or the total — for
        the callers that stitch several blocks together themselves (the
        summary composes day, month and games with blank lines between)."""
        return (
            blockquote(self.rows, expandable=self.expandable)
            if self.quoted
            else "\n".join(self.rows)
        )

    def render(self) -> str:
        above = [line for line in (self.header, self.total) if line]
        return "\n".join([*above, self.body()]) if above else self.body()


def total_line(label: str, text: str) -> str:
    """The line a list's summary starts with, highlighted the same way
    everywhere so it reads as a total rather than another row — and placed
    *before* the list it summarizes, so the headline number is read before
    anything is tapped open (SPEC 6.3, 7.3)."""
    return f"<b>{label}:</b> {text}"


@dataclass(frozen=True)
class GameRow:
    """One game in a games list, whichever list it came from.

    `/stats` ranks one person's own recent games (`TopGame`) and the monthly
    summary ranks the whole chat's (`ChatTopGame`); the row on screen is the
    same row, which is why both now arrive here as this. `tiers` is PSN's
    bronze/silver/gold/platinum, all zero elsewhere.
    """

    platform: str | None
    name: str | None
    count: int
    score: int = 0
    tiers: tuple[int, int, int, int] = (0, 0, 0, 0)


def game_rows(games: list[GameRow], untitled: str, locale: str) -> list[str]:
    """`N. 🟢 Название — 29 ач. (+525 G)`, or a PSN row's trophy tiers.

    Not truncated (2026-09-08, owner request), unlike an achievement row: a
    games list always lives inside its own collapsible quote, so a long title
    wrapping onto a second line costs nothing a scrollable screen minds.

    This was two identical copies until #64 — one in /stats, one in the
    monthly summary — down to the comment above.
    """
    return [
        f"{place}. {PLATFORM_ICON.get(game.platform or '', '')} "
        f"{html_escape(game.name or untitled)} — {_game_tail(game, locale)}"
        for place, game in enumerate(games, start=1)
    ]


def _game_tail(game: GameRow, locale: str) -> str:
    """PSN games show a trophy-tier breakdown instead of gamerscore (owner
    request, 2026-09-08) — the same per-tier icons every other screen uses.
    Xbox and Steam show the "(+N G)" tail, skipped for a zero score, which a
    Steam row's always is."""
    if game.platform == Platform.PSN:
        platinum, gold, silver, bronze = game.tiers
        tail = "".join(
            f" {badge}{count}"
            for count, badge in (
                (platinum, TROPHY_TIER_BADGE[PsnTrophyTier.PLATINUM]),
                (gold, TROPHY_TIER_BADGE[PsnTrophyTier.GOLD]),
                (silver, TROPHY_TIER_BADGE[PsnTrophyTier.SILVER]),
                (bronze, TROPHY_TIER_BADGE[PsnTrophyTier.BRONZE]),
            )
            if count
        )
        return f"{plural_trophies(game.count, locale)}{tail}"
    return f"{plural_achievements(game.count, locale)}{score_suffix(game.score)}"
