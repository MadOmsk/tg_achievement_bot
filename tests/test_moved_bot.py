"""The old bot after the move (#238): where it sends people."""

from __future__ import annotations

from bot.moved import build_dispatcher, dm_screen, group_screen


def test_a_dm_is_sent_to_the_new_bot() -> None:
    text, keyboard = dm_screen("unlocked_project_bot")
    assert "@unlocked_project_bot" in text
    assert keyboard.inline_keyboard[0][0].url == "https://t.me/unlocked_project_bot?start=moved"


def test_a_group_is_offered_the_new_bot() -> None:
    text, keyboard = group_screen("unlocked_project_bot")
    assert "@unlocked_project_bot" in text
    assert keyboard.inline_keyboard[0][0].url == (
        "https://t.me/unlocked_project_bot?startgroup=moved"
    )


def test_the_dispatcher_has_both_handlers() -> None:
    assert len(build_dispatcher("unlocked_project_bot").message.handlers) == 2
