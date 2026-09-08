"""Rendering /online's table (SPEC 6.3) — split out of test_chat_online.py
when the rendering itself moved to services/online_view.py (Follow-up
2026-09-05, needed by the auto-refresh poller too)."""

from __future__ import annotations

from bot.db.repo import ChatPresenceRow
from bot.services.online_view import _row_name, presence_icon, presence_text, render_online_table

XUID_A = "xuid-a"


def presence(
    state: str | None,
    title_id: str | None = None,
    title_name: str | None = None,
    platform: str = "modern",
    **extra: str | None,
):
    return ChatPresenceRow(
        tg_id=1,
        gamertag="Igor",
        xuid=XUID_A,
        state=state,
        title_id=title_id,
        title_name=title_name,
        platform=platform,
        **extra,
    )


def test_playing_shows_the_game() -> None:
    row = presence("Online", "123", "Halo Infinite")
    assert presence_text(row) == "играет — Halo Infinite"


def test_online_not_playing() -> None:
    row = presence("Online", None)
    assert presence_text(row) == "в сети, не играет"


def test_offline() -> None:
    row = presence("Offline")
    assert presence_text(row) == "не в сети"


def test_never_polled() -> None:
    row = presence(None)
    assert presence_text(row) == "нет данных"


def test_presence_icon_is_platform_colour_while_online() -> None:
    """SPEC 9, M-Steam-2e: online (playing or not) — the circle marks which
    platform, not whether they're playing (status is already in the text
    next to it). Playing and merely-online both get the platform colour."""
    assert presence_icon(presence("Online", "123", "Halo Infinite", platform="modern")) == "🟢"
    assert presence_icon(presence("Online", None, platform="modern")) == "🟢"
    assert presence_icon(presence("Online", "550", "L4D2", platform="steam")) == "⚫"
    assert presence_icon(presence("Online", None, platform="steam")) == "⚫"


def test_presence_icon_is_grey_when_offline_regardless_of_platform() -> None:
    """Found live: a pure platform colour made offline rows indistinguishable
    from online ones — grey is the one thing a status colour is actually
    good for, and it should mean the same thing on every platform."""
    assert presence_icon(presence("Offline", platform="modern")) == "⚪"
    assert presence_icon(presence("Offline", platform="steam")) == "⚪"
    assert presence_icon(presence(None, platform="modern")) == "⚪"
    assert presence_icon(presence(None, platform="steam")) == "⚪"


def test_render_online_table_shows_the_updated_stamp_in_italics() -> None:
    """Follow-up 2026-09-05: /online now says when it was last refreshed,
    so a live-updating table doesn't look identical whether it just ran or
    is about to go stale."""
    text = render_online_table([presence("Online", "123", "Halo Infinite")], "14:32")
    assert "<i>Обновлено: 14:32</i>" in text
    assert "Igor" in text


def test_row_name_uses_the_gamertag_when_platform_is_modern() -> None:
    row = presence("Online", "123", "Halo Infinite", platform="modern")
    assert _row_name(row) == "Igor"


def test_row_name_uses_the_steam_display_name_when_platform_is_steam() -> None:
    row = presence("Online", "550", "L4D2", platform="steam", steam_display_name="IgorSteam")
    assert _row_name(row) == "IgorSteam"


def test_row_name_uses_the_psn_display_name_when_platform_is_psn() -> None:
    row = presence(None, platform="psn", psn_display_name="IgorPSN")
    assert _row_name(row) == "IgorPSN"


def test_row_name_falls_back_to_telegram_full_name_when_nothing_tracked() -> None:
    """`platform == "none"` (Follow-up 2026-09-08): no Xbox/Steam presence
    was ever tracked — a PSN-only person, or an account never polled yet.
    Falls back to the Telegram name, not a platform nickname it has no
    presence evidence for."""
    row = presence(None, platform="none", first_name="Igor", last_name="Petrov")
    assert _row_name(row) == "Igor Petrov"


def test_row_name_falls_back_to_plain_username_without_at_sign() -> None:
    """Deliberately not "@username" — this table auto-refreshes every few
    minutes, and a live mention would ping that person every time (the
    reason #38's Telegram-identity attempt got reverted)."""
    row = presence(None, platform="none", username="igor")
    name = _row_name(row)
    assert name == "igor"
    assert "@" not in name


def test_row_name_falls_back_to_bare_id_when_nothing_is_known_at_all() -> None:
    row = ChatPresenceRow(
        tg_id=42,
        gamertag=None,
        xuid=None,
        state=None,
        title_id=None,
        title_name=None,
        platform="none",
    )
    assert _row_name(row) == "id42"
