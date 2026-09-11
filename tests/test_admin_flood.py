"""Admin panel side of the anti-flood filter (2026-09-09 user request) —
the chat card's own settings row, alongside rare_threshold_percent's."""

from __future__ import annotations

from types import SimpleNamespace

from bot.db.repo import Repo
from bot.handlers.admin import (
    FLOOD_LIMIT_DEFAULT,
    FLOOD_LIMIT_MAX,
    FLOOD_LIMIT_MIN,
    FLOOD_WINDOW_MAX,
    FLOOD_WINDOW_MIN,
    _chat,
    chat_flood_toggle,
)
from bot.i18n import AVAILABLE_LOCALES, gettext

CHAT_ID = -100999


class _FakeCallback:
    """A minimal stand-in for aiogram's CallbackQuery — `.message` is
    deliberately not a real `aiogram.types.Message`, so `_redraw` takes its
    "can't edit, just acknowledge" branch instead of needing a full
    Telegram message object."""

    def __init__(self, data: str) -> None:
        self.data = data
        self.message = None
        self.from_user = SimpleNamespace(id=1)

    async def answer(self, *args: object, **kwargs: object) -> None:
        pass


def _callback_datas(markup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row if btn.callback_data]


async def test_bounds_reject_a_negative_limit_and_an_absurd_window(i18n) -> None:
    assert not (FLOOD_LIMIT_MIN <= -1 <= FLOOD_LIMIT_MAX)
    assert FLOOD_LIMIT_MIN <= 0 <= FLOOD_LIMIT_MAX  # 0 = off, a valid value
    assert not (FLOOD_WINDOW_MIN <= 0 <= FLOOD_WINDOW_MAX)  # 0 minutes is not a real window
    assert FLOOD_WINDOW_MIN <= 60 <= FLOOD_WINDOW_MAX


async def test_chat_card_shows_the_flood_settings_and_their_edit_buttons(repo: Repo, i18n) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.update_chat_settings(CHAT_ID, flood_limit=5, flood_window_minutes=45)

    text, markup = await _chat(repo, CHAT_ID, locale="ru")

    assert "5 ач." in text
    assert "45 мин" in text
    datas = _callback_datas(markup)
    assert f"a:cfl:{CHAT_ID}" in datas
    assert f"a:cflw:{CHAT_ID}" in datas


async def test_chat_card_shows_off_when_flood_limit_is_zero(repo: Repo, i18n) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.update_chat_settings(CHAT_ID, flood_limit=0)

    text, _markup = await _chat(repo, CHAT_ID, locale="ru")

    assert "выключен" in text


async def test_chat_card_has_the_toggle_button(repo: Repo, i18n) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)

    _text, markup = await _chat(repo, CHAT_ID, locale="ru")

    assert f"a:cfltoggle:{CHAT_ID}" in _callback_datas(markup)


async def test_toggle_turns_a_configured_filter_off(repo: Repo, i18n) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.update_chat_settings(CHAT_ID, flood_limit=7)

    await chat_flood_toggle(_FakeCallback(f"a:cfltoggle:{CHAT_ID}"), repo, i18n)

    text, _markup = await _chat(repo, CHAT_ID, locale="ru")
    assert "выключен" in text


async def test_toggle_turns_an_off_filter_back_on_at_the_default(repo: Repo, i18n) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.update_chat_settings(CHAT_ID, flood_limit=0)

    await chat_flood_toggle(_FakeCallback(f"a:cfltoggle:{CHAT_ID}"), repo, i18n)

    text, _markup = await _chat(repo, CHAT_ID, locale="ru")
    assert f"{FLOOD_LIMIT_DEFAULT} ач." in text
    assert "выключен" not in text


async def test_saved_confirmations_append_the_chat_card_exactly_once(i18n) -> None:
    """Found while translating admin.ftl (#48): admin-flood-window-saved
    carried { $text } twice, so changing the anti-flood window replied with
    the whole chat card duplicated. Its two siblings always had it once."""
    for locale in AVAILABLE_LOCALES:
        for key in ("admin-threshold-saved", "admin-flood-saved", "admin-flood-window-saved"):
            rendered = gettext("admin", key, locale=locale, value=5, text="THE-CARD")
            assert rendered.count("THE-CARD") == 1, f"{locale}/{key}"
