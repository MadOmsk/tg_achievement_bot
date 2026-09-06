"""Renders a PSN account's trophy overview (Follow-up 2026-09-06) — a
deliberately separate table from /stats' own games list for now: a real
mock built to review before deciding whether/how to merge the two.
Currently only reached from the admin panel's live "🏆 Трофеи PSN (тест)"
screen (handlers/admin.py), same cache-only-rule carve-out as the rest of
that screen (SPEC 1.5).
"""

from __future__ import annotations

from html import escape as html_escape

from bot.services.psn.client import AccountTrophyOverview
from bot.services.tables import blockquote, total_line, truncate_name


def render_psn_trophy_table(overview: AccountTrophyOverview) -> str:
    """HTML output (blockquote() expects already-escaped lines) — the
    caller sends this with ParseMode.HTML, same as /stats' own games list."""
    online_id = html_escape(overview.online_id)
    header = total_line(
        "PSN", f"{online_id} · уровень {overview.trophy_level} ({overview.progress}%)"
    )
    tier_line = (
        f"🏆 {overview.earned_platinum} · 🥇 {overview.earned_gold} · "
        f"🥈 {overview.earned_silver} · 🥉 {overview.earned_bronze}"
    )
    if not overview.games:
        return f"{header}\n{tier_line}\n\nИгр с трофеями не найдено."

    rows = [
        f"{html_escape(truncate_name(game.title_name))} — {game.progress}% "
        f"({game.earned_total}/{game.defined_total})"
        for game in overview.games
    ]
    return f"{header}\n{tier_line}\n\n{blockquote(rows)}"
