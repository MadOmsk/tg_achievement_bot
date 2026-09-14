"""Shared enums for persisted and external string values."""

from enum import IntEnum, StrEnum


class Platform(StrEnum):
    """Persisted values — `seen_achievements.platform` and friends store
    these strings directly, so renaming one is a migration (034).

    `XBOX_MODERN` covers Xbox One, Series and the PC Microsoft Store: one
    achievement service, one contract (4), no distinction the bot could draw
    even if it wanted to. It was called plain `modern` while Xbox was the
    only platform here and the word had an obvious subject; next to `steam`
    and `psn` it stopped having one (2026-09-11, user request), and both
    Xbox values now say Xbox.
    """

    XBOX_MODERN = "xbox_modern"
    XBOX_360 = "xbox_360"
    STEAM = "steam"
    PSN = "psn"


class AccountPlatform(StrEnum):
    """Which platform an *account* is on (#52) — coarser than `Platform`
    above, which says where an achievement came from. Both Xbox generations
    are one account and one platform to a person (owner decision, they bind
    as a pair), so there is no `xbox_360` here; `seen_achievements`'
    GENERATED `account_platform` column computes exactly this mapping.
    """

    XBOX = "xbox"
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
    # The two naming steps of the Xbox chain (#51) — both already ride along
    # in the profile response read for GAMERSCORE, no extra request.
    GAMERTAG = "Gamertag"
    MODERN_GAMERTAG = "ModernGamertag"
    FULL = "Full"
    ACTIVE = "Active"
    INVALID_GRANT = "invalid_grant"


class SteamCommunityVisibility(IntEnum):
    PUBLIC = 3
