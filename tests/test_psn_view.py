"""services/psn/view.py::render_psn_trophy_table — the separate PSN trophy
table (Follow-up 2026-09-06), ahead of deciding how to merge it into
/stats' own games list."""

from __future__ import annotations

from bot.services.psn.client import AccountTrophyOverview, GameTrophyProgress
from bot.services.psn.view import render_psn_trophy_table


def _overview(games: list[GameTrophyProgress] | None = None) -> AccountTrophyOverview:
    return AccountTrophyOverview(
        online_id="superomsk",
        trophy_level=5,
        progress=50,
        earned_bronze=16,
        earned_silver=1,
        earned_gold=0,
        earned_platinum=0,
        games=games or [],
    )


def _game(name: str = "Ratchet & Clank") -> GameTrophyProgress:
    return GameTrophyProgress(
        title_name=name,
        progress=25,
        earned_total=17,
        defined_total=47,
        earned_bronze=16,
        earned_silver=1,
        earned_gold=0,
        earned_platinum=0,
        last_updated="2026-08-15T00:00:00",
    )


def test_shows_online_id_level_and_tier_totals() -> None:
    text = render_psn_trophy_table(_overview([_game()]))
    assert "superomsk" in text
    assert "уровень 5" in text
    assert "50%" in text
    assert "🥉 16" in text
    assert "🥈 1" in text


def test_lists_each_game_with_progress_and_earned_of_defined() -> None:
    text = render_psn_trophy_table(_overview([_game("Bloodborne")]))
    assert "Bloodborne" in text
    assert "25%" in text
    assert "(17/47)" in text


def test_no_games_says_so_instead_of_an_empty_list() -> None:
    text = render_psn_trophy_table(_overview([]))
    assert "не найдено" in text


def test_html_escapes_the_online_id_and_game_name() -> None:
    overview = _overview([_game("<script>")])
    overview.online_id = "<b>evil</b>"
    text = render_psn_trophy_table(overview)
    assert "<script>" not in text
    assert "<b>evil</b>" not in text
    assert "&lt;" in text
