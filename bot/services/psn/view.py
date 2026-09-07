"""Renders a PSN account's trophy overview (Follow-up 2026-09-06) — a
deliberately separate table from /stats' own games list for now: a real
mock built to review before deciding whether/how to merge the two.
Currently only reached from the admin panel's live "🏆 Трофеи PSN (тест)"
screen (handlers/admin.py), same cache-only-rule carve-out as the rest of
that screen (SPEC 1.5).
"""

from __future__ import annotations

from html import escape as html_escape

from bot.constants import PsnTrophyTier
from bot.i18n import gettext
from bot.services.achievements import TROPHY_TIER_BADGE
from bot.services.psn.client import AccountTrophyOverview
from bot.services.tables import blockquote, total_line, truncate_name

_ = lambda key, **kwargs: gettext("psnview", key, **kwargs)  # noqa: E731


def render_psn_trophy_table(overview: AccountTrophyOverview) -> str:
    """HTML output (blockquote() expects already-escaped lines) — the
    caller sends this with ParseMode.HTML, same as /stats' own games list."""
    online_id = html_escape(overview.online_id)
    header = total_line(
        _("psnview-platform"),
        _(
            "psnview-level",
            online_id=online_id,
            level=overview.trophy_level,
            progress=overview.progress,
        ),
    )
    tier_line = (
        f"{TROPHY_TIER_BADGE[PsnTrophyTier.PLATINUM]} {overview.earned_platinum} · "
        f"{TROPHY_TIER_BADGE[PsnTrophyTier.GOLD]} {overview.earned_gold} · "
        f"{TROPHY_TIER_BADGE[PsnTrophyTier.SILVER]} {overview.earned_silver} · "
        f"{TROPHY_TIER_BADGE[PsnTrophyTier.BRONZE]} {overview.earned_bronze}"
    )
    if not overview.games:
        return f"{header}\n{tier_line}\n\n{_('psnview-no-games')}"

    rows = [
        f"{html_escape(truncate_name(game.title_name))} — {game.progress}% "
        f"({game.earned_total}/{game.defined_total})"
        for game in overview.games
    ]
    return f"{header}\n{tier_line}\n\n{blockquote(rows)}"
