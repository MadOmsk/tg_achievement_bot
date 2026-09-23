"""Unit tests for date navigation keyboards and date helpers (#75)."""

from __future__ import annotations

from datetime import date

from bot.views.date_picker import (
    format_day_month,
    format_month_year,
    next_month,
    prev_month,
    stats_month_calendar_keyboard,
    stats_navigation_keyboard,
    summary_day_calendar_keyboard,
    summary_day_navigation_keyboard,
    summary_month_navigation_keyboard,
)


def _callback_data(markup) -> list[str | None]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def _button_texts(markup) -> list[str]:
    return [b.text for row in markup.inline_keyboard for b in row]


def test_prev_and_next_month_calculation() -> None:
    assert prev_month(2026, 1) == (2025, 12)
    assert prev_month(2026, 9) == (2026, 8)
    assert next_month(2026, 12) == (2027, 1)
    assert next_month(2026, 9) == (2026, 10)


def test_format_helpers() -> None:
    assert format_month_year(2026, 9, "ru") == "Сентябрь 2026"
    assert format_month_year(2026, 9, "en") == "September 2026"
    assert format_day_month(date(2026, 9, 21), "ru") == "21 сентября"
    assert format_day_month(date(2026, 9, 21), "en") == "21 Sep"


def test_stats_navigation_keyboard_current_month_hides_next() -> None:
    markup = stats_navigation_keyboard(12345, 2026, 9, 2026, 9, locale="ru")
    data = _callback_data(markup)
    texts = _button_texts(markup)

    assert data == ["st:nav:12345:2026:8", "st:cal:12345:2026"]
    assert texts == ["◀️", "📅 Сентябрь 2026"]


def test_stats_navigation_keyboard_past_month_shows_next() -> None:
    markup = stats_navigation_keyboard(12345, 2026, 8, 2026, 9, locale="ru")
    data = _callback_data(markup)
    texts = _button_texts(markup)

    assert data == ["st:nav:12345:2026:7", "st:cal:12345:2026", "st:nav:12345:2026:9"]
    assert texts == ["◀️", "📅 Август 2026", "▶️"]


def test_stats_month_calendar_keyboard_grid() -> None:
    markup = stats_month_calendar_keyboard(12345, 2026, 2026, 9, locale="ru")
    data = _callback_data(markup)
    texts = _button_texts(markup)

    # Year header row
    assert data[0:2] == ["st:cal:12345:2025", "noop"]
    assert texts[0:2] == ["◀️ 2025", "• 2026 •"]

    # Month grid (12 months): 1..9 enabled, 10..12 disabled (noop)
    assert data[2 + 0] == "st:nav:12345:2026:1"
    assert data[2 + 8] == "st:nav:12345:2026:9"
    assert data[2 + 9] == "noop"
    assert data[2 + 11] == "noop"

    # Back button
    assert data[-1] == "st:nav:12345:2026:9"


def test_summary_month_navigation_keyboard() -> None:
    markup = summary_month_navigation_keyboard(2026, 9, 2026, 9, locale="ru", has_more=True)
    data = _callback_data(markup)
    assert "summary:all:month" in data


def test_summary_day_navigation_keyboard() -> None:
    markup = summary_day_navigation_keyboard(
        date(2026, 9, 21), date(2026, 9, 21), locale="ru", has_more=True
    )
    data = _callback_data(markup)
    texts = _button_texts(markup)

    assert data[0:2] == ["sd:nav:2026-09-20", "sd:cal:2026-09-21"]
    assert texts[0:2] == ["◀️", "📅 21 сентября"]
    assert "summary:all:day" in data


def test_summary_day_calendar_keyboard_has_14_days() -> None:
    markup = summary_day_calendar_keyboard(date(2026, 9, 21), date(2026, 9, 21), locale="ru")
    data = _callback_data(markup)
    # 14 days + 1 back button = 15 buttons
    assert len(data) == 15
    assert data[0] == "sd:nav:2026-09-08"
    assert data[13] == "sd:nav:2026-09-21"
    assert data[14] == "sd:nav:2026-09-21"
