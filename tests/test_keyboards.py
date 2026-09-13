"""Panel keyboard construction (SPEC 6.2)."""

from __future__ import annotations

from bot.handlers.keyboards import (
    next_rarity_mode,
    panel_keyboard,
    psn_profile_url,
    steam_profile_url,
    xbox_profile_url,
)


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
    assert data[-4:-1] == ["relogin", "psn:connect", "steam:connect"]
    # #33: uniform "🎮 Подключить X" wording, not "🔗 XBOX" / "🎮 Steam".
    texts = _button_texts(markup)
    assert texts[-4:-1] == [
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
    assert "panel:sync" in data
    assert "panel:linkstoggle" in data
    assert "panel:refresh" in data


def test_every_platform_is_exactly_one_row_in_xbox_psn_steam_order() -> None:
    """#33: one row per platform, always the same position — no split
    between a connect button at the top and a profile/disconnect row at the
    bottom for the same platform.

    Xbox, PlayStation, Steam: the one display order every screen uses
    (constants.platform_display_rank, owner decision 2026-09-13). /panel
    listed Steam second and /stats listed PlayStation second, which is how
    "a fixed order" turned out to mean two different orders.
    """
    markup = panel_keyboard(
        180,
        connected=True,
        steam_connected=True,
        psn_connected=False,
        gamertag="Mad Omsk",
        steam_id="76561197960287930",
    )
    rows = markup.inline_keyboard
    xbox_i = next(
        i for i, r in enumerate(rows) if any(b.callback_data == "panel:disconnect" for b in r)
    )
    steam_i = next(
        i for i, r in enumerate(rows) if any(b.callback_data == "steam:disconnectprompt" for b in r)
    )
    psn_i = next(i for i, r in enumerate(rows) if any(b.callback_data == "psn:connect" for b in r))
    assert psn_i == xbox_i + 1
    assert steam_i == xbox_i + 2
    assert rows[steam_i + 1][0].callback_data == "panel:refresh"  # platform block, then Обновить


def test_not_connected_keyboard_offers_steam_disconnect_once_connected() -> None:
    """Steam-only, no XBOX at all — still gets a real disconnect option for
    the platform it does have, not nothing (2026-09-05 follow-up)."""
    markup = panel_keyboard(None, connected=False, steam_connected=True)
    assert _callback_data(markup)[-4:-1] == ["relogin", "psn:connect", "steam:disconnectprompt"]


def test_connected_keyboard_offers_steam_connect_or_disconnect_not_both() -> None:
    connect_only = panel_keyboard(180, connected=True)
    assert "steam:connect" in _callback_data(connect_only)
    assert "steam:disconnectprompt" not in _callback_data(connect_only)

    disconnect_only = panel_keyboard(180, connected=True, steam_connected=True)
    assert "steam:disconnectprompt" in _callback_data(disconnect_only)
    assert "steam:connect" not in _callback_data(disconnect_only)


def test_connected_keyboard_offers_psn_connect_or_disconnect_not_both() -> None:
    """PSN's own counterpart of the Steam test above (SPEC 9, M-PSN-1)."""
    connect_only = panel_keyboard(180, connected=True)
    assert "psn:connect" in _callback_data(connect_only)
    assert "psn:disconnectprompt" not in _callback_data(connect_only)

    disconnect_only = panel_keyboard(180, connected=True, psn_connected=True)
    assert "psn:disconnectprompt" in _callback_data(disconnect_only)
    assert "psn:connect" not in _callback_data(disconnect_only)


def test_needs_reconnect_adds_a_button_without_hiding_settings() -> None:
    connected = panel_keyboard(None, connected=True, needs_reconnect=False)
    reconnecting = panel_keyboard(None, connected=True, needs_reconnect=True)

    assert "relogin" not in _callback_data(connected)
    data = _callback_data(reconnecting)
    assert data[0] == "relogin"  # up front, not buried under settings
    assert "panel:tz" in data  # settings still reachable, not replaced


def test_connected_keyboard_offers_disconnect() -> None:
    markup = panel_keyboard(180, connected=True)
    assert "panel:disconnect" in _callback_data(markup)


def _disconnect_row(markup, callback_data: str) -> list:
    return next(
        row for row in markup.inline_keyboard if callback_data in [b.callback_data for b in row]
    )


def test_xbox_disconnect_row_gains_a_profile_link_when_gamertag_is_known() -> None:
    """2026-09-05 follow-up: profile link and disconnect share one row."""
    without = panel_keyboard(180, connected=True)
    row = _disconnect_row(without, "panel:disconnect")
    assert len(row) == 1  # no gamertag given — no profile button to add

    with_tag = panel_keyboard(180, connected=True, gamertag="Mad Omsk")
    row = _disconnect_row(with_tag, "panel:disconnect")
    assert len(row) == 2
    assert row[0].url == xbox_profile_url("Mad Omsk")
    assert row[1].callback_data == "panel:disconnect"


def test_steam_disconnect_row_gains_a_profile_link_when_steam_id_is_known() -> None:
    without = panel_keyboard(180, connected=True, steam_connected=True)
    row = _disconnect_row(without, "steam:disconnectprompt")
    assert len(row) == 1

    with_id = panel_keyboard(
        180, connected=True, steam_connected=True, steam_id="76561197960287930"
    )
    row = _disconnect_row(with_id, "steam:disconnectprompt")
    assert len(row) == 2
    assert row[0].url == steam_profile_url("76561197960287930")
    assert row[1].callback_data == "steam:disconnectprompt"


def test_psn_disconnect_row_gains_a_profile_link_when_psn_id_is_known() -> None:
    """Same treatment as XBOX/Steam above (2026-09-06 follow-up, reversing
    the earlier "PSN has no linkable page" call)."""
    without = panel_keyboard(180, connected=True, psn_connected=True)
    row = _disconnect_row(without, "psn:disconnectprompt")
    assert len(row) == 1

    with_id = panel_keyboard(180, connected=True, psn_connected=True, psn_id="superomsk")
    row = _disconnect_row(with_id, "psn:disconnectprompt")
    assert len(row) == 2
    assert row[0].url == psn_profile_url("superomsk")
    assert row[1].callback_data == "psn:disconnectprompt"


def _toggle_button_text(markup):
    return next(
        b.text
        for row in markup.inline_keyboard
        for b in row
        if b.callback_data == "panel:linkstoggle"
    )


def test_show_profile_links_toggle_reflects_state_and_is_reachable() -> None:
    off = panel_keyboard(180, connected=True, show_profile_links=False)
    on = panel_keyboard(180, connected=True, show_profile_links=True)
    assert "panel:linkstoggle" in _callback_data(off)
    assert "нет" in _toggle_button_text(off)
    assert "да" in _toggle_button_text(on)


def test_xbox_profile_url_encodes_the_gamertag() -> None:
    assert xbox_profile_url("Mad Omsk") == (
        "https://account.xbox.com/en-us/profile?gamertag=Mad%20Omsk"
    )


def test_steam_profile_url_uses_the_steamid64() -> None:
    assert (
        steam_profile_url("76561197960287930")
        == "https://steamcommunity.com/profiles/76561197960287930"
    )
