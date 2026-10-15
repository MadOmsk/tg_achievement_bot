"""Which HowLongToBeat platform a version of ours is (#147; owner,
2026-10-15): a version takes the row HLTB keeps for its platform. A version is
one console (`platform_format`'s names, plus `steam`); a PC version of any
store — Steam, the Microsoft Store, one of a store not known — is HLTB's "PC".
HLTB names its platforms its own way; this is the one place that says how."""

from __future__ import annotations

HLTB_PLATFORM = {
    "series": "Xbox Series X/S",
    "one": "Xbox One",
    "360": "Xbox 360",
    "ps5": "PlayStation 5",
    "ps4": "PlayStation 4",
    "ps3": "PlayStation 3",
    "vita": "PlayStation Vita",
    "steam": "PC",
    "pc": "PC",
    "mobile": "Mobile",
}


def hltb_platform(console: str | None) -> str | None:
    """The platform HLTB calls our console, None when HLTB has none for it
    (the cloud, a console we do not know)."""
    return HLTB_PLATFORM.get(str(console or ""))


def platforms_of_group(platforms: str | None) -> list[str]:
    """The platforms of a group HLTB writes as one string ("PC, PlayStation
    Vita, Xbox One")."""
    return [p.strip() for p in str(platforms or "").split(",") if p.strip()]
