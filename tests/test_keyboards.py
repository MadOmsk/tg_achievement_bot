"""Panel keyboard construction (SPEC 6.2)."""

from __future__ import annotations

from bot.services.profile_links import steam_profile_url, xbox_profile_url
from bot.views.keyboards import next_rarity_mode, panel_keyboard


def _button_texts(markup) -> list[str]:
    return [b.text for row in markup.inline_keyboard for b in row]


def _callback_data(markup) -> list[str | None]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def test_rarity_cycles_through_all_three_and_wraps() -> None:
    assert next_rarity_mode("all") == "rare"
    assert next_rarity_mode("rare") == "hidden"
    assert next_rarity_mode("hidden") == "all"


def test_unknown_rarity_mode_starts_the_cycle_over() -> None:
    # Defensive: a row that somehow holds neither of the three values must
    # not raise — it just resets to the first choice.
    assert next_rarity_mode("whatever") == "rare"


def test_not_connected_keyboard_offers_all_platforms() -> None:
    """Xbox, Steam and PSN are independent (M-Steam-1, M-PSN-1) — someone
    with none connected should be offered all three, not just Xbox
    (2026-09-05 follow-up, extended for PSN)."""
    markup = panel_keyboard(None, connected=False)
    data = _callback_data(markup)
    assert data[-6:-3] == ["relogin", "psn:connect", "steam:connect"]
    # #33: uniform "🎮 Подключить X" wording, not "🔗 XBOX" / "🎮 Steam".
    texts = _button_texts(markup)
    assert texts[-6:-3] == [
        "🎮 Подключить Xbox",
        "🎮 Подключить PSN",
        "🎮 Подключить Steam",
    ]


def test_not_connected_keyboard_still_offers_the_rest_of_the_settings() -> None:
    """Found live (2026-09-09, screenshot comparison): this whole config
    section used to be gated on `connected` (Xbox specifically) too — a
    Steam/PSN-only person saw nothing but the platform rows at all, not even
    a timezone or "Мои чаты" button. Timezone/chats/sync/toggle are
    person-wide settings, not Xbox-specific ones."""
    markup = panel_keyboard(None, connected=False)
    data = _callback_data(markup)
    assert "panel:tz" in data
    assert "panel:chatlist" in data
    assert "panel:linkstoggle" not in data  # the admin's now (2026-09-29)
    assert "panel:delete_account" in data
    assert "panel:sync" in data


def test_every_platform_is_exactly_one_row_in_xbox_psn_steam_order() -> None:
    """#33: one row per platform, always the same position.

    Xbox, PlayStation, Steam: the one display order every screen uses
    (constants.platform_display_rank, owner decision 2026-09-13)."""
    markup = panel_keyboard(180, connected=True, steam_connected=True, psn_connected=False)
    rows = markup.inline_keyboard
    xbox_i = next(
        i for i, r in enumerate(rows) if any(b.callback_data == "panel:acc:xbox" for b in r)
    )
    steam_i = next(
        i for i, r in enumerate(rows) if any(b.callback_data == "panel:acc:steam" for b in r)
    )
    psn_i = next(i for i, r in enumerate(rows) if any(b.callback_data == "psn:connect" for b in r))
    assert psn_i == xbox_i + 1
    assert steam_i == xbox_i + 2
    assert rows[steam_i + 1][0].callback_data == "panel:delete_account"
    assert rows[steam_i + 2][0].callback_data == "panel:sync"


def test_a_linked_platform_is_its_screen_and_its_switch() -> None:
    """#10: two buttons per linked platform — the platform, into its own
    screen, and the platform's publishing switch."""
    markup = panel_keyboard(None, connected=False, steam_connected=True)
    row = _row(markup, "panel:acc:steam")
    assert [b.callback_data for b in row] == ["panel:acc:steam", "panel:pub:steam"]
    assert row[0].text == "⚫ Steam ▸"


def test_connected_keyboard_offers_steam_connect_or_its_screen_not_both() -> None:
    connect_only = panel_keyboard(180, connected=True)
    assert "steam:connect" in _callback_data(connect_only)
    assert "panel:acc:steam" not in _callback_data(connect_only)

    linked = panel_keyboard(180, connected=True, steam_connected=True)
    assert "panel:acc:steam" in _callback_data(linked)
    assert "steam:connect" not in _callback_data(linked)


def test_connected_keyboard_offers_psn_connect_or_its_screen_not_both() -> None:
    connect_only = panel_keyboard(180, connected=True)
    assert "psn:connect" in _callback_data(connect_only)
    assert "panel:acc:psn" not in _callback_data(connect_only)

    linked = panel_keyboard(180, connected=True, psn_connected=True)
    assert "panel:acc:psn" in _callback_data(linked)
    assert "psn:connect" not in _callback_data(linked)


def test_several_psn_accounts_are_counted_on_the_button() -> None:
    one = panel_keyboard(180, connected=True, psn_connected=True)
    two = panel_keyboard(180, connected=True, psn_connected=True, psn_accounts=2)
    assert _row(one, "panel:acc:psn")[0].text == "🔵 PSN ▸"
    assert _row(two, "panel:acc:psn")[0].text == "🔵 PSN (2) ▸"


def test_a_dead_xbox_login_puts_reconnect_in_place_of_the_switch() -> None:
    """A dead login posts nothing, so the XBOX row offers the way back in
    where the posting switch was, and nothing is added on top (2026-09-29)."""
    connected = panel_keyboard(None, connected=True, needs_reconnect=False)
    reconnecting = panel_keyboard(None, connected=True, needs_reconnect=True)

    assert "relogin" not in _callback_data(connected)
    row = _row(reconnecting, "panel:acc:xbox")
    assert [b.callback_data for b in row] == ["panel:acc:xbox", "relogin"]
    assert reconnecting.inline_keyboard[0][0].callback_data == "panel:tz"


def _row(markup, callback_data: str) -> list:
    return next(
        row for row in markup.inline_keyboard if callback_data in [b.callback_data for b in row]
    )


def test_xbox_profile_url_encodes_the_gamertag() -> None:
    assert xbox_profile_url("Mad Omsk") == (
        "https://account.xbox.com/en-us/profile?gamertag=Mad%20Omsk"
    )


def test_steam_profile_url_uses_the_steamid64() -> None:
    assert (
        steam_profile_url("76561197960287930")
        == "https://steamcommunity.com/profiles/76561197960287930"
    )


def test_the_switch_says_on_off_or_partly() -> None:
    """#20: 🔔 while the platform posts, 🔇 once switched off, and "Частично"
    when only some of several PSN accounts post (#10)."""
    on = panel_keyboard(180, connected=True, psn_connected=True)
    off = panel_keyboard(180, connected=True, psn_connected=True, psn_publishes=False)
    partly = panel_keyboard(180, connected=True, psn_connected=True, psn_publishes=None)
    assert _row(on, "panel:pub:psn")[1].text == "🔔 Публикуется"
    assert _row(off, "panel:pub:psn")[1].text == "🔇 Не публикуется"
    assert _row(partly, "panel:pub:psn")[1].text == "🔔 Частично"
