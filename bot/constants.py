"""Shared enums for persisted and external string values."""

from enum import IntEnum, StrEnum


class Platform(StrEnum):
    MODERN = "modern"
    X360 = "x360"
    STEAM = "steam"
    PSN = "psn"


class PresenceState(StrEnum):
    ONLINE = "Online"
    OFFLINE = "Offline"


class TokenStatus(StrEnum):
    ACTIVE = "active"
    INVALID = "invalid"
    REVOKED = "revoked"


class RarityMode(StrEnum):
    ALL = "all"
    RARE = "rare"
    HIDDEN = "hidden"


class AchievementBadge(StrEnum):
    DIAMOND = "💎"
    CUP = "🏆"
    GOLD = "🥇"
    SILVER = "🥈"
    BRONZE = "🥉"


class PsnTrophyTier(StrEnum):
    PLATINUM = "platinum"
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"


class SettingKey(StrEnum):
    SUMMARY_TOP_LIMIT = "summary_top_limit"
    STATS_GAMES_LIMIT = "stats_games_limit"
    HLTB_RESULTS_LIMIT = "hltb_results_limit"
    HLTB_PAGE_SIZE = "hltb_page_size"


class XboxApiValue(StrEnum):
    ACHIEVED = "Achieved"
    ICON = "Icon"
    GAMERSCORE = "Gamerscore"
    FULL = "Full"
    ACTIVE = "Active"
    INVALID_GRANT = "invalid_grant"


class SteamCommunityVisibility(IntEnum):
    PUBLIC = 3
