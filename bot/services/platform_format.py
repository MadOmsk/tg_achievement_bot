"""Mapping and formatting of game platforms and player devices (#79).

Separates:
1. Game platforms: available platforms for a title (e.g. Xbox devices, PSN title_platform).
2. Player device: physical console / device where player is online or earned an achievement.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

# Xbox device tokens
_XBOX_SERIES_TOKENS = {"xboxseriesx", "xboxseriess", "xboxseries", "xboxscarlett"}
_XBOX_ONE_TOKENS = {"xboxone"}
_XBOX_PC_TOKENS = {"windowsonecore", "pc", "win32", "windows"}
_XBOX_360_TOKENS = {"xbox360", "xbox 360"}
_XBOX_MOBILE_TOKENS = {"mobile", "ios", "android", "windowsphone"}
_XBOX_CLOUD_TOKENS = {"web", "cloud"}

# PSN tokens
_PSN_VITA_TOKENS = {"psvita", "ps vita", "vita"}


def normalize_device_name(device: str | None, *, short: bool = False) -> str | None:
    """Normalize a raw device string (from presence or earned achievement)
    into a human-readable display string."""
    if not device:
        return None
    raw = device.strip()
    key = raw.lower()

    if key in _XBOX_SERIES_TOKENS:
        return "XSeries" if short else "XBOX Series X|S"
    if key in _XBOX_ONE_TOKENS:
        return "XOne" if short else "XBOX One"
    if key in _XBOX_PC_TOKENS:
        return "XBOX PC"
    if key in _XBOX_360_TOKENS:
        return "X360" if short else "XBOX 360"
    if key in _XBOX_MOBILE_TOKENS:
        return "XBOX Mobile"
    if key in _XBOX_CLOUD_TOKENS:
        return "XBOX Cloud"

    if key == "ps5":
        return "PS5" if short else "PlayStation 5"
    if key == "ps4":
        return "PS4" if short else "PlayStation 4"
    if key == "ps3":
        return "PS3" if short else "PlayStation 3"
    if key in _PSN_VITA_TOKENS:
        return "PS Vita" if short else "PlayStation Vita"
    if key in {"pspc", "ps pc"}:
        return "PS PC"

    if key in {"steam", "valve"}:
        return "Steam"

    return raw


def _parse_raw_platforms(platforms_raw: str | Iterable[str] | None) -> list[str]:
    """Parse raw JSON string or comma-separated string into a list of strings."""
    if not platforms_raw:
        return []
    if isinstance(platforms_raw, str):
        text = platforms_raw.strip()
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if item]
            except (json.JSONDecodeError, TypeError):
                pass
        return [part.strip() for part in text.split(",") if part.strip()]
    return [str(item).strip() for item in platforms_raw if item]


def format_game_platforms(
    platforms_raw: str | Iterable[str] | None,
    fallback_platform: str | None = None,
    *,
    device: str | None = None,
    short: bool = False,
) -> str:
    """Format available game platforms into a Full or Short display string.

    Rules:
    XBOX:
      Play Anywhere: (One or Series) + PC -> Full: 'XBOX Play Anywhere', Short: 'XPA'
      Cross-gen: One + Series -> Full: 'XBOX One | Series', Short: 'XOne | Series'
      Series only: -> Full: 'XBOX Series X|S', Short: 'XSeries'
      One only: -> Full: 'XBOX One', Short: 'XOne'
      360 only: -> Full: 'XBOX 360', Short: 'X360'
      PC only: -> Full: 'XBOX PC', Short: 'XBOX PC'

    PlayStation:
      PS3 + PS4 + Vita -> Full: 'PlayStation 3 | 4 | Vita', Short: 'PS3 | 4 | Vita'
      PS3 + Vita -> Full: 'PlayStation 3 | Vita', Short: 'PS3 | Vita'
      PS4 + Vita -> Full: 'PlayStation 4 | Vita', Short: 'PS4 | Vita'
      PS4 + PS5 -> Full: 'PlayStation 4 | 5', Short: 'PS4 | PS5'
      PS5 only -> Full: 'PlayStation 5', Short: 'PS5'
      PS4 only -> Full: 'PlayStation 4', Short: 'PS4'
      PS3 only -> Full: 'PlayStation 3', Short: 'PS3'
      Vita only -> Full: 'PlayStation Vita', Short: 'PS Vita'

    Steam:
      Steam -> Full: 'Steam', Short: 'Steam'
    """
    raw_list = _parse_raw_platforms(platforms_raw)
    tokens = {item.lower() for item in raw_list}

    if not tokens and device:
        dev_norm = normalize_device_name(device, short=short)
        if dev_norm:
            return dev_norm

    if not tokens:
        if fallback_platform:
            fb = fallback_platform.lower()
            if fb in {"xbox_360", "x360"}:
                return "X360" if short else "XBOX 360"
            if fb in {"xbox_modern", "modern", "xbox"}:
                return "XBOX"
            if fb == "psn":
                return "PS" if short else "PlayStation"
            if fb == "steam":
                return "Steam"
        return ""

    # Check for Steam (Steam always formats as Steam)
    if (fallback_platform and fallback_platform.lower() == "steam") or "steam" in tokens:
        return "Steam"

    # Check for Xbox
    has_series = bool(tokens & _XBOX_SERIES_TOKENS)
    has_one = bool(tokens & _XBOX_ONE_TOKENS)
    has_pc = bool(tokens & _XBOX_PC_TOKENS)
    has_360 = bool(tokens & _XBOX_360_TOKENS)

    if has_series or has_one or has_pc or has_360:
        if (has_series or has_one) and has_pc:
            return "XPA" if short else "XBOX Play Anywhere"
        if has_series and has_one:
            return "XOne | Series" if short else "XBOX One | Series"
        if has_series:
            return "XSeries" if short else "XBOX Series X|S"
        if has_one:
            return "XOne" if short else "XBOX One"
        if has_360:
            return "X360" if short else "XBOX 360"
        if has_pc:
            return "XBOX PC"
        return "XBOX"

    # Check for PlayStation
    has_ps5 = "ps5" in tokens
    has_ps4 = "ps4" in tokens
    has_ps3 = "ps3" in tokens
    has_vita = bool(tokens & _PSN_VITA_TOKENS)

    if has_ps5 or has_ps4 or has_ps3 or has_vita:
        if has_ps3 and has_ps4 and has_vita:
            return "PS3 | 4 | Vita" if short else "PlayStation 3 | 4 | Vita"
        if has_ps3 and has_vita:
            return "PS3 | Vita" if short else "PlayStation 3 | Vita"
        if has_ps4 and has_vita:
            return "PS4 | Vita" if short else "PlayStation 4 | Vita"
        if has_ps4 and has_ps5:
            return "PS4 | PS5" if short else "PlayStation 4 | 5"
        if has_ps5:
            return "PS5" if short else "PlayStation 5"
        if has_ps4:
            return "PS4" if short else "PlayStation 4"
        if has_ps3:
            return "PS3" if short else "PlayStation 3"
        if has_vita:
            return "PS Vita" if short else "PlayStation Vita"
        return "PS" if short else "PlayStation"

    if "pc" in tokens:
        return "Steam"

    return "XBOX" if "xbox" in tokens else "PlayStation"
