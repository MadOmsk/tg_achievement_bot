"""Admin panel side of the anti-flood filter (2026-09-09 user request) —
the chat card's own settings row, alongside rare_threshold_percent's."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.handlers.admin import (
    FLOOD_LIMIT_MAX,
    FLOOD_LIMIT_MIN,
    FLOOD_WINDOW_MAX,
    FLOOD_WINDOW_MIN,
    _chat,
)

CHAT_ID = -100999


def _callback_datas(markup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row if btn.callback_data]


async def test_bounds_reject_a_negative_limit_and_an_absurd_window() -> None:
    assert not (FLOOD_LIMIT_MIN <= -1 <= FLOOD_LIMIT_MAX)
    assert FLOOD_LIMIT_MIN <= 0 <= FLOOD_LIMIT_MAX  # 0 = off, a valid value
    assert not (FLOOD_WINDOW_MIN <= 0 <= FLOOD_WINDOW_MAX)  # 0 minutes is not a real window
    assert FLOOD_WINDOW_MIN <= 60 <= FLOOD_WINDOW_MAX


async def test_chat_card_shows_the_flood_settings_and_their_edit_buttons(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.update_chat_settings(CHAT_ID, flood_limit=5, flood_window_minutes=45)

    text, markup = await _chat(repo, CHAT_ID)

    assert "5 ач." in text
    assert "45 мин" in text
    datas = _callback_datas(markup)
    assert f"a:cfl:{CHAT_ID}" in datas
    assert f"a:cflw:{CHAT_ID}" in datas


async def test_chat_card_shows_off_when_flood_limit_is_zero(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.update_chat_settings(CHAT_ID, flood_limit=0)

    text, _markup = await _chat(repo, CHAT_ID)

    assert "выключен" in text
