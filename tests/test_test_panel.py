"""Tests for interactive test panel (#10, #20, #126)."""

from __future__ import annotations

from bot.views.test_panel import (
    MockPanelState,
    render_screen,
)


def test_render_all_screens() -> None:
    state = MockPanelState()

    for scr in [
        "home",
        "acc:psn",
        "acc:xbox",
        "acc:steam",
        "psn_add",
        "unlink_confirm",
        "chats",
        "chat_detail",
        "chat_del_confirm",
        "tz",
        "admin",
        "adm_digest",
        "adm_usercard",
    ]:
        text, markup = render_screen(scr, state, {"platform": "psn", "id": "1", "chat_id": 101})
        assert text
        assert markup.inline_keyboard is not None
        assert len(markup.inline_keyboard) > 0


def test_toggle_publication_and_rarity_state() -> None:
    state = MockPanelState()
    assert state.rarity_mode == "all"
    assert state.xbox_publishes is True
    assert state.psn_accounts[0]["publishes"] is True
    assert state.psn_accounts[1]["publishes"] is False

    # Toggle xbox
    state.xbox_publishes = False
    text, markup = render_screen("home", state)
    assert "XBOX: 🔇 Не публикуется" in text
    assert any("🔇 Не публикуется" in btn.text for row in markup.inline_keyboard for btn in row)

    # Toggle psn
    state.psn_accounts[1]["publishes"] = True
    text, _ = render_screen("acc:psn", state)
    assert "Snake (второй)" in text

    # Toggle rarity cyclic button on home
    state.rarity_mode = "rare"
    text, markup = render_screen("home", state)
    assert "Достижения (#126):</b> редкие" in text
    assert any(
        "Публиковать достижения: редкие" in btn.text
        for row in markup.inline_keyboard
        for btn in row
    )


def test_chat_delete_button_visibility() -> None:
    state = MockPanelState()
    chat_sub = state.chats[0]
    assert chat_sub["subscribed"] is True
    _, markup_sub = render_screen("chat_detail", state, {"chat_id": chat_sub["id"]})
    # Subscribed chat has no delete button
    assert not any(
        "Удалить из списка" in btn.text for row in markup_sub.inline_keyboard for btn in row
    )

    # Unsubscribed chat has delete button
    chat_unsub = state.chats[1]
    assert chat_unsub["subscribed"] is False
    _, markup_unsub = render_screen("chat_detail", state, {"chat_id": chat_unsub["id"]})
    assert any(
        "Удалить из списка" in btn.text for row in markup_unsub.inline_keyboard for btn in row
    )


def test_add_and_unlink_psn_accounts() -> None:
    state = MockPanelState()
    assert len(state.psn_accounts) == 2

    # Add 3rd
    state.psn_accounts.append(
        {
            "id": "3",
            "name": "Hunter3",
            "publishes": True,
            "level": 10,
            "trophies": 20,
            "platinum": 0,
        }
    )
    assert len(state.psn_accounts) == 3

    # Screen should not have add button anymore
    _, markup = render_screen("acc:psn", state)
    add_buttons = [
        btn for row in markup.inline_keyboard for btn in row if "Добавить аккаунт" in btn.text
    ]
    assert len(add_buttons) == 0

    # Unlink account 1
    state.psn_accounts = [a for a in state.psn_accounts if a["id"] != "1"]
    assert len(state.psn_accounts) == 2
    _, markup2 = render_screen("acc:psn", state)
    add_buttons2 = [
        btn for row in markup2.inline_keyboard for btn in row if "Добавить аккаунт" in btn.text
    ]
    assert len(add_buttons2) == 1
