"""services/profile_links.py — URL builders and the link_html gate
(Follow-up 2026-09-06)."""

from __future__ import annotations

from bot.services.profile_links import (
    link_html,
    platform_profile_url,
    psn_profile_url,
    steam_profile_url,
    xbox_profile_url,
)


def test_xbox_profile_url_encodes_the_gamertag() -> None:
    assert xbox_profile_url("Mad Omsk") == (
        "https://account.xbox.com/en-us/profile?gamertag=Mad%20Omsk"
    )


def test_steam_profile_url_uses_the_steamid64() -> None:
    assert steam_profile_url("76561197960287930") == (
        "https://steamcommunity.com/profiles/76561197960287930"
    )


def test_psn_profile_url_uses_the_online_id() -> None:
    assert psn_profile_url("superomsk") == "https://my.playstation.com/profile/superomsk"


def test_platform_profile_url_steam_uses_external_id_not_display_name() -> None:
    url = platform_profile_url("steam", external_id="76561197960287930", display_name="Gabe")
    assert url == "https://steamcommunity.com/profiles/76561197960287930"


def test_platform_profile_url_psn_uses_display_name_not_external_id() -> None:
    """PSN's own external_id is the internal account_id (link_platform_account's
    own third argument) — meaningless in a my.playstation.com URL, unlike
    Steam's. The onlineId lives in display_name instead."""
    url = platform_profile_url("psn", external_id="internal-account-id", display_name="superomsk")
    assert url == "https://my.playstation.com/profile/superomsk"


def test_platform_profile_url_psn_without_display_name_is_none() -> None:
    assert platform_profile_url("psn", external_id="internal-account-id", display_name=None) is None


def test_platform_profile_url_unknown_platform_is_none() -> None:
    assert platform_profile_url("xbox_modern", external_id="xuid-1", display_name="Igor") is None


def test_link_html_wraps_text_when_a_url_is_given() -> None:
    assert link_html("https://example.com", "Igor") == '<a href="https://example.com">Igor</a>'


def test_link_html_returns_text_unchanged_without_a_url() -> None:
    assert link_html(None, "Igor") == "Igor"
