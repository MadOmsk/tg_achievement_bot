"""The lists this bot renders, and what they have in common (#64).

A list here is a header, its rows, sometimes a total line above them, a cap,
and a wrapper. The wrapper is *usually* a collapsible blockquote — a report
section you tap to open, which is Telegram's own shape for it and reads far
better than the monospace table this used to be — but that is a default, not
the definition: `/online` is a list too and is not quoted.

**A row is shared only where it is genuinely the same row.** A list of games
and a list of people are different things, and forcing both through one
template would make every future change to one a change to the other — so
each kind keeps its own renderer here, side by side, where the difference is
visible.

Games are the case where it *is* the same row, and `games_listing` below is
the whole template rather than just the line: three screens draw it (`/stats`
for one person, each summary for every subscriber) and differ only in which
people and which window were asked for. The query behind them is one too
(`repo.users_games_achievements`). It was two copies six lines apart until
2026-09-17, which is the sort of duplicate that quietly grows a difference.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from html import escape as html_escape

from bot.constants import Platform
from bot.db.repo import GameAchievements
from bot.views.parts import (
    PLATFORM_ICON,
    bracketed,
    plural_achievements,
    plural_trophies,
    value_parts,
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

    `/stats` ranks one person's own games and the monthly summary ranks the
    whole chat's; the row on screen is the same row, and since 2026-09-17 so
    is the query behind it (`repo.users_games_achievements`). `tiers` is PSN's
    platinum/gold/silver/bronze, all zero elsewhere; `rare` is how many
    achievements cleared the chat's rarity threshold, which PSN rows never
    show — their tier already answers "how rare" on Sony's own scale.
    """

    platform: str | None
    name: str | None
    count: int
    score: int = 0
    rare: int = 0
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


def games_listing(games: Sequence[GameAchievements], untitled: str, locale: str) -> Listing:
    """The one games list this bot has (owner, 2026-09-17).

    Three screens draw it and they differ only in *which people* and *which
    window* were asked for: `/stats` passes one person and the calendar
    month, each summary passes every subscriber and its own cutoff. The query
    behind them is one too (`repo.users_games_achievements`), so what is left
    here is the mapping onto a row — which lived in two copies until this
    function, and is the sort of duplicate that quietly grows a difference.

    Returns the `Listing` rather than rendered text: the summary stitches its
    blocks together itself and needs the body and its header separable, while
    /stats just calls `.render()`.
    """
    return Listing(
        rows=game_rows(
            [
                GameRow(
                    platform=game.platform,
                    name=game.name,
                    count=game.count,
                    score=game.score,
                    rare=game.rare,
                    tiers=(game.platinum, game.gold, game.silver, game.bronze),
                )
                for game in games
            ],
            untitled,
            locale,
        )
    )


def _game_tail(game: GameRow, locale: str) -> str:
    """What was earned, then what it was worth, in brackets (owner, 2026-09-17).

    PSN breaks its trophies down by tier instead of showing a rarity count
    (owner request, 2026-09-08) — the tier already answers "how rare" on
    Sony's own scale, and its own badge is the same icon every other screen
    uses for it. Xbox and Steam show gamerscore and how many were rare, each
    skipped when zero: a Steam row's gamerscore always is, an Xbox 360 row's
    rare count always is (contract 1 carries no rarity at all), and "(+0 G)"
    on every line reads as noise.
    """
    if game.platform == Platform.PSN:
        # A PSN row breaks down by tier and shows no gamerscore (it has none)
        # and no rarity count — the tier already answers "how rare" on Sony's
        # own scale.
        return plural_trophies(game.count, locale) + bracketed(value_parts(0, 0, game.tiers))
    return plural_achievements(game.count, locale) + bracketed(
        value_parts(game.score, game.rare, (0, 0, 0, 0))
    )
