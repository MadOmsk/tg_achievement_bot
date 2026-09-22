from __future__ import annotations

import json

from bot.services.platform_format import format_game_platforms, normalize_device_name


def test_normalize_device_name() -> None:
    # Full by default
    assert normalize_device_name("XboxSeriesX") == "XBOX Series X|S"
    assert normalize_device_name("XboxSeriesS") == "XBOX Series X|S"
    assert normalize_device_name("XboxScarlett") == "XBOX Series X|S"
    assert normalize_device_name("XboxOne") == "XBOX One"
    assert normalize_device_name("WindowsOneCore") == "XBOX PC"
    assert normalize_device_name("PC") == "XBOX PC"
    assert normalize_device_name("Xbox360") == "XBOX 360"
    assert normalize_device_name("Mobile") == "XBOX Mobile"

    assert normalize_device_name("PS5") == "PlayStation 5"
    assert normalize_device_name("PS4") == "PlayStation 4"
    assert normalize_device_name("PS3") == "PlayStation 3"
    assert normalize_device_name("PSVITA") == "PlayStation Vita"
    assert normalize_device_name("PSPC") == "PS PC"

    assert normalize_device_name("Steam") == "Steam"
    assert normalize_device_name(None) is None
    assert normalize_device_name("") is None

    # Short
    assert normalize_device_name("XboxSeriesX", short=True) == "XSeries"
    assert normalize_device_name("XboxOne", short=True) == "XOne"
    assert normalize_device_name("Xbox360", short=True) == "X360"
    assert normalize_device_name("PC", short=True) == "XBOX PC"
    assert normalize_device_name("PS5", short=True) == "PS5"
    assert normalize_device_name("PS4", short=True) == "PS4"
    assert normalize_device_name("PS3", short=True) == "PS3"
    assert normalize_device_name("PSVITA", short=True) == "PS Vita"


def test_format_game_platforms_full() -> None:
    # Xbox Full
    assert format_game_platforms(json.dumps(["XboxSeriesX"])) == "XBOX Series X|S"
    assert format_game_platforms(json.dumps(["XboxOne"])) == "XBOX One"
    assert format_game_platforms(json.dumps(["PC"])) == "XBOX PC"
    assert format_game_platforms(json.dumps(["Xbox360"])) == "XBOX 360"
    assert format_game_platforms(json.dumps(["XboxOne", "XboxSeriesX"])) == "XBOX One | Series"
    assert format_game_platforms(json.dumps(["XboxOne", "PC"])) == "XBOX Play Anywhere"
    assert format_game_platforms(json.dumps(["XboxSeriesX", "PC"])) == "XBOX Play Anywhere"
    assert (
        format_game_platforms(json.dumps(["XboxOne", "XboxSeriesX", "PC"])) == "XBOX Play Anywhere"
    )

    # PlayStation Full
    assert format_game_platforms("PS5") == "PlayStation 5"
    assert format_game_platforms("PS4") == "PlayStation 4"
    assert format_game_platforms("PS3") == "PlayStation 3"
    assert format_game_platforms("PSVITA") == "PlayStation Vita"
    assert format_game_platforms("PS3,PSVITA") == "PlayStation 3 | Vita"
    assert format_game_platforms("PS4,PSVITA") == "PlayStation 4 | Vita"
    assert format_game_platforms("PS4,PS3,PSVITA") == "PlayStation 3 | 4 | Vita"
    assert format_game_platforms("PS4,PS5") == "PlayStation 4 | 5"

    # Steam Full
    assert format_game_platforms(["PC"], fallback_platform="steam") == "Steam"
    assert format_game_platforms(["Steam"]) == "Steam"


def test_format_game_platforms_short() -> None:
    # Xbox Short
    assert format_game_platforms(["XboxSeriesX"], short=True) == "XSeries"
    assert format_game_platforms(["XboxOne"], short=True) == "XOne"
    assert format_game_platforms(["Xbox360"], short=True) == "X360"
    assert format_game_platforms(["PC"], short=True) == "XBOX PC"
    assert format_game_platforms(["XboxOne", "XboxSeriesX"], short=True) == "XOne | Series"
    assert format_game_platforms(["XboxOne", "PC"], short=True) == "XPA"
    assert format_game_platforms(["XboxSeriesX", "PC"], short=True) == "XPA"
    assert format_game_platforms(["XboxOne", "XboxSeriesX", "PC"], short=True) == "XPA"

    # PlayStation Short
    assert format_game_platforms("PS5", short=True) == "PS5"
    assert format_game_platforms("PS4", short=True) == "PS4"
    assert format_game_platforms("PS3", short=True) == "PS3"
    assert format_game_platforms("PSVITA", short=True) == "PS Vita"
    assert format_game_platforms("PS3,PSVITA", short=True) == "PS3 | Vita"
    assert format_game_platforms("PS4,PSVITA", short=True) == "PS4 | Vita"
    assert format_game_platforms("PS4,PS3,PSVITA", short=True) == "PS3 | 4 | Vita"
    assert format_game_platforms("PS4,PS5", short=True) == "PS4 | PS5"

    # Steam Short
    assert format_game_platforms(["PC"], fallback_platform="steam", short=True) == "Steam"
    assert format_game_platforms(["Steam"], short=True) == "Steam"


def test_format_game_platforms_fallback() -> None:
    assert format_game_platforms(None, fallback_platform="xbox_360") == "XBOX 360"
    assert format_game_platforms(None, fallback_platform="xbox_360", short=True) == "X360"
    assert format_game_platforms(None, fallback_platform="xbox_modern") == "XBOX"
    assert format_game_platforms(None, fallback_platform="psn") == "PlayStation"
    assert format_game_platforms(None, fallback_platform="psn", short=True) == "PS"
    assert format_game_platforms(None, fallback_platform="steam") == "Steam"
    assert format_game_platforms(None, fallback_platform=None) == ""
