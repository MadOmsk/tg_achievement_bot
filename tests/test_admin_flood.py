"""Admin panel side of the anti-flood filter (2026-09-09 user request): the
chat card states it, and its two numbers are settings of the registry (#176),
in the card's «Антифлуд» group."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bot.db.repo import Repo
from bot.handlers.admin import _awaiting_input, chat_setting_open, setting_number_input
from bot.services.admin_registry import find, parse
from bot.services.admin_settings import SettingValueError
from bot.views.admin import render_chat_card

CHAT_ID = -100999


class _FakeCallback:
    """`.message` is deliberately not a real Message, so `_redraw` takes its
    "can't edit, just acknowledge" branch."""

    def __init__(self, data: str) -> None:
        self.data = data
        self.message = None
        self.from_user = SimpleNamespace(id=1)

    async def answer(self, *args: object, **kwargs: object) -> None:
        pass


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=1)
        self.answers: list[str] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append(text)


def _callback_datas(markup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row if btn.callback_data]


def test_bounds_reject_a_negative_limit_and_an_absurd_window() -> None:
    limit, window = find("chat", "flood_limit"), find("chat", "flood_window_minutes")
    with pytest.raises(SettingValueError):
        parse(limit, "-1")
    assert parse(limit, "0") == 0  # 0 = off, a valid value
    with pytest.raises(SettingValueError):
        parse(window, "0")  # 0 minutes is not a real window
    with pytest.raises(SettingValueError):
        parse(window, "1441")
    assert parse(window, "60") == 60


async def test_chat_card_states_the_flood_settings_and_opens_their_group(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.update_chat_settings(CHAT_ID, flood_limit=5, flood_window_minutes=45)

    text, markup = await render_chat_card(repo, CHAT_ID, locale="ru")

    assert "5 ач." in text
    assert "45 мин" in text
    assert f"a:cg:{CHAT_ID}:flood" in _callback_datas(markup)

    _text, group = await render_chat_card(repo, CHAT_ID, locale="ru", section="flood")
    datas = _callback_datas(group)
    assert f"a:cs:{CHAT_ID}:flood_limit" in datas
    assert f"a:cs:{CHAT_ID}:flood_window_minutes" in datas
    assert f"a:chat:{CHAT_ID}" in datas  # back to the card


async def test_chat_card_shows_off_when_flood_limit_is_zero(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.update_chat_settings(CHAT_ID, flood_limit=0)

    text, _markup = await render_chat_card(repo, CHAT_ID, locale="ru")

    assert "выключен" in text


async def test_a_typed_limit_is_saved_and_a_bad_one_refused(repo: Repo, i18n) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await chat_setting_open(_FakeCallback(f"a:cs:{CHAT_ID}:flood_limit"), repo, i18n)
    assert _awaiting_input[1] == ("set:chat:flood_limit", CHAT_ID)

    too_many = _FakeMessage("51")
    await setting_number_input(too_many, repo, i18n)
    assert "0" in too_many.answers[0] and "50" in too_many.answers[0]
    assert _awaiting_input[1] == ("set:chat:flood_limit", CHAT_ID)  # still waiting

    ok = _FakeMessage("0")
    await setting_number_input(ok, repo, i18n)
    assert 1 not in _awaiting_input
    text, _markup = await render_chat_card(repo, CHAT_ID, locale="ru")
    assert "выключен" in text
    assert ok.answers[0].startswith("✅")
