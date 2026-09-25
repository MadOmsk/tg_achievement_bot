"""Which platform a screen names (#114): the version played, the platforms a
game was released on, the device somebody is on."""

from __future__ import annotations

import json

import pytest

from bot.services.platform_format import (
    device_label,
    game_platforms_json,
    game_platforms_label,
    played_version,
)

XPA = ["PC", "XboxOne", "XboxSeries"]
SMART = ["XboxOne", "XboxSeries"]


@pytest.mark.parametrize(
    ("platforms", "family", "device", "full", "short"),
    [
        # Xbox 360 is 360 on any console, even when titlehub lists the emulators
        (["Xbox360"], "xbox_360", "Scarlett", "XBOX 360", "360"),
        (["Xbox360", "XboxOne", "XboxSeries"], "xbox_modern", "Scarlett", "XBOX 360", "360"),
        (None, "xbox_360", None, "XBOX 360", "360"),
        # A game on one platform is that platform, whatever ran it
        (["XboxOne"], "xbox_modern", "Scarlett", "XBOX One", "One"),
        (["XboxOne"], "xbox_modern", None, "XBOX One", "One"),
        (["XboxSeries"], "xbox_modern", None, "XBOX Series X|S", "Series X|S"),
        (["PC"], "xbox_modern", None, "XBOX PC", "PC"),
        # Smart Delivery: the version of the console it ran on
        (SMART, "xbox_modern", "Scarlett", "XBOX Series X|S", "Series X|S"),
        (SMART, "xbox_modern", "Durango", "XBOX One", "One"),
        # Play Anywhere is never a version played
        (XPA, "xbox_modern", "WindowsOneCore", "XBOX PC", "PC"),
        (XPA, "xbox_modern", "XboxSeries", "XBOX Series X|S", "Series X|S"),
        (["PC", "XboxOne"], "xbox_modern", "Scarlett", "XBOX One", "One"),
        # The cloud runs the console version
        (XPA, "xbox_modern", "Web", "XBOX Series X|S ☁", "Series X|S ☁"),
        (["XboxOne"], "xbox_modern", "Web", "XBOX One ☁", "One ☁"),
        (XPA, "xbox_modern", "iOS", "XBOX Series X|S ☁", "Series X|S ☁"),
        (["Android", "PC", "XboxSeries"], "xbox_modern", "Android", "XBOX Mobile", "Mobile"),
        # Unknown: never guessed
        (XPA, "xbox_modern", None, "XBOX", "XBOX"),
        (None, "xbox_modern", None, "XBOX", "XBOX"),
        ("[]", "xbox_modern", None, "XBOX", "XBOX"),
        # The game unknown after three lookups: the device's own version
        ("[]", "xbox_modern", "Scarlett", "XBOX Series X|S", "Series X|S"),
        (None, "xbox_modern", "Web", "XBOX Series X|S ☁", "Series X|S ☁"),
        # PlayStation: backward compatibility gives the original, cross-buy the one played
        (["PS4"], "psn", "PS5", "PlayStation 4", "PS4"),
        (["PS4", "PS5"], "psn", "PS5", "PlayStation 5", "PS5"),
        (["PS4", "PS5"], "psn", "PS4", "PlayStation 4", "PS4"),
        (["PS3", "PS4", "PSVITA"], "psn", "PS5", "PlayStation 4", "PS4"),
        (["PS3", "PSVITA"], "psn", "PSVITA", "PlayStation Vita", "PS Vita"),
        (["PS4", "PS5"], "psn", None, "PSN", "PSN"),
        (None, "psn", None, "PSN", "PSN"),
        # Steam is Steam
        (["PC"], "steam", "PC", "Steam", "Steam"),
    ],
)
def test_played_version(platforms, family, device, full, short) -> None:
    raw = json.dumps(platforms) if isinstance(platforms, list) else platforms
    assert played_version(raw, family, device=device) == full
    assert played_version(raw, family, device=device, short=True) == short


@pytest.mark.parametrize(
    ("platforms", "family", "full", "short"),
    [
        (XPA, "xbox_modern", "XBOX Play Anywhere", "XPA"),
        (["PC", "XboxSeries"], "xbox_modern", "XBOX Play Anywhere", "XPA"),
        (SMART, "xbox_modern", "XBOX One | Series", "One | Series"),
        (["XboxSeries"], "xbox_modern", "XBOX Series X|S", "Series X|S"),
        (["XboxOne"], "xbox_modern", "XBOX One", "One"),
        (["PC"], "xbox_modern", "XBOX PC", "PC"),
        (["Xbox360"], "xbox_modern", "XBOX 360", "360"),
        (None, "xbox_360", "XBOX 360", "360"),
        (None, "xbox_modern", "XBOX", "XBOX"),
        (["PS4", "PS5"], "psn", "PlayStation 4 | 5", "PS4 | PS5"),
        (["PS3", "PS4", "PSVITA"], "psn", "PlayStation 3 | 4 | Vita", "PS3 | PS4 | Vita"),
        (["PS3", "PSVITA"], "psn", "PlayStation 3 | Vita", "PS3 | Vita"),
        (["PS4", "PSVITA"], "psn", "PlayStation 4 | Vita", "PS4 | Vita"),
        (["PS5"], "psn", "PlayStation 5", "PS5"),
        (["PSVITA"], "psn", "PlayStation Vita", "PS Vita"),
        (None, "psn", "PSN", "PSN"),
        (["PC"], "steam", "Steam", "Steam"),
    ],
)
def test_game_platforms_label(platforms, family, full, short) -> None:
    raw = json.dumps(platforms) if platforms is not None else None
    assert game_platforms_label(raw, family) == full
    assert game_platforms_label(raw, family, short=True) == short


@pytest.mark.parametrize(
    ("device", "short"),
    [
        ("Scarlett", "Series X|S"),
        ("XboxSeriesX", "Series X|S"),
        ("Durango", "One"),
        ("WindowsOneCore", "PC"),
        ("Web", "Series X|S ☁"),
        ("iOS", "Mobile"),
        ("PS5", "PS5"),
        ("PSVITA", "PS Vita"),
        (None, None),
        ("HoloLens", None),
    ],
)
def test_device_label(device, short) -> None:
    assert device_label(device) == short


def test_game_platforms_json() -> None:
    assert game_platforms_json(["PC", "XboxSeries"]) == '["PC", "XboxSeries"]'
    assert game_platforms_json(["Xbox360", "XboxOne"]) == '["Xbox360"]'
    assert game_platforms_json(["XboxOne"], is_x360=True) == '["Xbox360"]'
    assert game_platforms_json([]) is None
    assert game_platforms_json(None) is None
