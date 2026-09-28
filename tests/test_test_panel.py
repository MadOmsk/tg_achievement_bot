"""Tests for interactive test panel (#10, #20, #126) and Showcase screens."""

from __future__ import annotations

from bot.views.test_panel import (
    MockPanelState,
    render_screen,
)


def test_render_all_screens() -> None:
    state = MockPanelState()

    all_screens = [
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
    ]

    for scr in all_screens:
        text, markup = render_screen(scr, state, {"platform": "psn", "id": "1", "chat_id": 101})
        assert text, f"Empty text for {scr}"
        assert markup.inline_keyboard is not None, f"No keyboard for {scr}"
        assert len(markup.inline_keyboard) > 0, f"Empty keyboard for {scr}"


def test_psn_single_vs_multi_labeling() -> None:
    state = MockPanelState()
    assert len(state.psn_accounts) == 2

    # Multi PSN (2 accounts)
    text_multi, markup_multi = render_screen("home", state)
    assert "Вход PSN1:  SuperOmsk" in text_multi
    assert "Вход PSN2:  Omsk2" in text_multi
    assert any("🔵 PSN (2) ▸" in btn.text for row in markup_multi.inline_keyboard for btn in row)

    text_acc_multi, markup_acc_multi = render_screen("acc:psn", state)
    assert "PSN1: SuperOmsk" in text_acc_multi
    assert "PSN2: Omsk2" in text_acc_multi
    assert any(
        "👤 Профиль: PSN1 (SuperOmsk)" in btn.text
        for row in markup_acc_multi.inline_keyboard
        for btn in row
    )

    # Single PSN (1 account)
    state.psn_accounts = [state.psn_accounts[0]]
    assert len(state.psn_accounts) == 1

    text_single, markup_single = render_screen("home", state)
    assert "Вход PSN:  SuperOmsk" in text_single
    assert "Вход PSN1" not in text_single
    assert any("🔵 PSN ▸" in btn.text for row in markup_single.inline_keyboard for btn in row)

    text_acc_single, markup_acc_single = render_screen("acc:psn", state)
    assert "PSN: SuperOmsk" in text_acc_single
    assert "PSN1" not in text_acc_single
    assert any(
        "👤 Профиль: PSN (SuperOmsk)" in btn.text
        for row in markup_acc_single.inline_keyboard
        for btn in row
    )


def test_toggle_publication_and_rarity_state() -> None:
    state = MockPanelState()
    assert state.rarity_mode == "all"
    assert state.xbox_publishes is True

    # Toggle xbox
    state.xbox_publishes = False
    _, markup = render_screen("home", state)
    assert any("🔇 Не публикуется" in btn.text for row in markup.inline_keyboard for btn in row)

    # Toggle rarity cyclic button on home
    state.rarity_mode = "rare"
    _, markup_rare = render_screen("home", state)
    assert any(
        "Публиковать достижения: Редкие" in btn.text
        for row in markup_rare.inline_keyboard
        for btn in row
    )


def test_chat_delete_button_visibility() -> None:
    state = MockPanelState()
    chat_sub = state.chats[0]
    assert chat_sub["subscribed"] is True
    _, markup_sub = render_screen("chat_detail", state, {"chat_id": chat_sub["id"]})
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

    # Screen has add button when < 3
    _, markup = render_screen("acc:psn", state)
    assert any("➕ Добавить аккаунт" in btn.text for row in markup.inline_keyboard for btn in row)

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
    _, markup_full = render_screen("acc:psn", state)
    assert not any(
        "➕ Добавить аккаунт" in btn.text
        for row in markup_full.inline_keyboard
        for btn in row
    )

    # Unlink account 1
    state.psn_accounts = [a for a in state.psn_accounts if a["id"] != "1"]
    assert len(state.psn_accounts) == 2
    _, markup_after = render_screen("acc:psn", state)
    assert any(
        "➕ Добавить аккаунт" in btn.text
        for row in markup_after.inline_keyboard
        for btn in row
    )
