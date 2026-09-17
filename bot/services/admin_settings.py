"""What the /admin panel's settings *are* (#63).

The numeric settings with their bounds and their labels, the defaults a new
person or chat starts at, the page size of the user list. Neither layout
nor behaviour: views/admin.py draws these and handlers/admin.py validates
what an operator types into them, and a constant with two readers in two
layers belongs under both rather than inside one of them.
"""

from __future__ import annotations

from dataclasses import dataclass

from bot.constants import RarityMode, SettingKey, TokenStatus
from bot.i18n import gettext
from bot.poller.message_cleanup import DEFAULT_TTL_MINUTES as DEFAULT_SYSTEM_MESSAGE_TTL_MIN
from bot.poller.message_cleanup import TTL_SETTING_KEY as SYSTEM_MESSAGE_TTL_KEY
from bot.poller.online_refresh import DEFAULT_REFRESH_INTERVAL_MIN as DEFAULT_ONLINE_REFRESH_MIN
from bot.poller.online_refresh import DEFAULT_TTL_HOURS as DEFAULT_ONLINE_REFRESH_TTL_HOURS
from bot.poller.online_refresh import REFRESH_INTERVAL_KEY as ONLINE_REFRESH_INTERVAL_KEY
from bot.poller.online_refresh import TTL_HOURS_KEY as ONLINE_REFRESH_TTL_KEY
from bot.poller.service_health import (
    DEFAULT_KEY_CHECK_INTERVAL_MIN,
    KEY_CHECK_INTERVAL_KEY,
)

# /hltb's own two limits, admin-set like every other number here — the
# command reads them from this module rather than owning them, so nothing
# in bot/services/ has to reach into a handler for a constant.
RESULTS_LIMIT_KEY = "hltb_results_limit"
PAGE_SIZE_KEY = "hltb_page_size"
DEFAULT_RESULTS_LIMIT = 20
DEFAULT_PAGE_SIZE = 5


# How many rows a summary leaderboard shows before its "show everyone"
# button appears; 0 means uncapped.
TOP_LIMIT_KEY = "summary_top_limit"
DEFAULT_TABLE_TOP = 15


def unlimited_label(locale: str) -> str:
    """What a 0 renders as in the numeric-settings screens. Was a
    module-level constant, which froze whichever locale loaded first (#48) —
    the same trap PLATFORM_LABEL and HELP_TEXT had."""
    return gettext("admin", "admin-unlimited", locale=locale)


PAGE_SIZE = 8

STATUS_ICON = {
    TokenStatus.ACTIVE: "✅",
    TokenStatus.INVALID: "⚠️",
    TokenStatus.REVOKED: "🔕",
}


RARE_THRESHOLD_MIN = 0.01
RARE_THRESHOLD_MAX = 100.0
LIMIT_MIN = 1
LIMIT_MAX = 50

# Anti-flood filter (2026-09-09 user request) — per-chat, admin-set like the
# rare threshold above. flood_limit's own 0 means "off for this chat", same
# convention as min_gamerscore/summary_top_limit.
FLOOD_LIMIT_MIN = 0
FLOOD_LIMIT_MAX = 50
FLOOD_WINDOW_MIN = 1
FLOOD_WINDOW_MAX = 1440  # 24h — a longer buffer than that stops being "soon"
# What the on/off toggle below turns flood_limit *back on* to — matches
# chat_settings' own schema default (schema.sql), so a chat that never
# touched this setting and one that was switched off and back on land on
# the same starting point.
FLOOD_LIMIT_DEFAULT = 3

# Chat-scoped keys sharing numeric_setting_input()'s "type a number" flow
# with the always-global NUMERIC_SETTINGS above (rare_threshold_percent's
# own comment there explains the split).
CHAT_SCOPED_KEYS = ("rare_threshold_percent", "flood_limit", "flood_window_minutes")

# What a brand-new subscription starts at (Repo.subscribe) — used to be a
# flat DEFAULT 'all' baked into the subscriptions table (schema.sql), now an
# admin-configurable app_settings row instead, same cycling button/helpers
# the personal and per-chat toggles already use (keyboards.py) rather than
# the free-text numeric flow above — 'all'/'rare'/'hidden' isn't a number.
DEFAULT_RARITY_MODE_KEY = "default_rarity_mode"
DEFAULT_RARITY_MODE_DEFAULT = RarityMode.ALL

# What a brand-new person's user_settings row starts with (Repo.ensure_user,
# Follow-up 2026-09-06) — same admin-configurable-default shape as
# DEFAULT_RARITY_MODE_KEY above, just a plain on/off instead of a cycle
# through three modes.
DEFAULT_SHOW_LINKS_KEY = "default_show_profile_links"
DEFAULT_SHOW_LINKS_DEFAULT = "0"


_DEFAULT_STATS_GAMES_LIMIT = 15

#: What /recent shows when nobody has said otherwise.
DEFAULT_RECENT_LIMIT = 5


@dataclass(frozen=True, slots=True)
class NumericSetting:
    """One row of the "type a number" admin flow (2026-09-05 refactor —
    replaces five parallel dicts, all keyed by the same setting names, with
    one). `zero_label` only matters when `min == 0`; a setting that doesn't
    allow 0 never reaches _format_limit's zero branch at all."""

    label: str
    default: int
    min: int = LIMIT_MIN
    max: int = LIMIT_MAX
    zero_label: str = "admin-unlimited"


# Every admin-configurable count/limit/interval in the bot, one place —
# each (key, default) pair still lives with the code that actually falls
# back to it (imported above), so this registry can't drift from reality
# the way five hand-typed dicts eventually would have.
NUMERIC_SETTINGS: dict[str, NumericSetting] = {
    TOP_LIMIT_KEY: NumericSetting("admin-setting-summary-rows", DEFAULT_TABLE_TOP, min=0),
    # SPEC 1.6: both render into a <blockquote expandable>, not a fixed-width
    # table — an "unlimited" list fits there just fine, so these two alone
    # allow 0 for "no cap". Everything else below stays at min=1: a page
    # size or a search pool of 0 is just broken, not "show everything".
    SettingKey.STATS_GAMES_LIMIT: NumericSetting(
        "admin-setting-stats-games", _DEFAULT_STATS_GAMES_LIMIT, min=0
    ),
    # /recent's own row count (owner, 2026-09-17) — it used to be a constant
    # in the handler with an optional `N` argument on top, the one list whose
    # size was not the admin's to set. The argument stays, bounded by
    # RECENT_MAX, as a one-off "show me more" rather than the only way.
    SettingKey.RECENT_LIMIT: NumericSetting("admin-setting-recent-rows", DEFAULT_RECENT_LIMIT),
    RESULTS_LIMIT_KEY: NumericSetting("admin-setting-hltb-results", DEFAULT_RESULTS_LIMIT),
    # Feeds Telegram inline-keyboard rows directly — 50 buttons on one page
    # would be unusable, unlike the two above.
    PAGE_SIZE_KEY: NumericSetting("admin-setting-hltb-page", DEFAULT_PAGE_SIZE, max=10),
    # These two's own 0 means something else again — "off", not "no cap".
    SYSTEM_MESSAGE_TTL_KEY: NumericSetting(
        "admin-setting-system-ttl",
        DEFAULT_SYSTEM_MESSAGE_TTL_MIN,
        min=0,
        max=60,
        zero_label="admin-disabled",
    ),
    ONLINE_REFRESH_INTERVAL_KEY: NumericSetting(
        "admin-setting-online-interval",
        DEFAULT_ONLINE_REFRESH_MIN,
        min=0,
        max=60,
        zero_label="admin-disabled",
    ),
    # Stays at the default min (1): a 0-hour window is just "off" spelled a
    # more confusing way than the interval's own off switch already is.
    ONLINE_REFRESH_TTL_KEY: NumericSetting(
        "admin-setting-online-ttl", DEFAULT_ONLINE_REFRESH_TTL_HOURS, max=24
    ),
    # One shared cadence for two things (Follow-up 2026-09-06): how often
    # poller/service_health.py rechecks the Steam/PSN keys, AND how often
    # the /admin home screen refreshes itself in place — deliberately the
    # same knob, not two settings that merely start out equal, since the
    # panel's own numbers (key status, request counts) are only ever as
    # fresh as the last health check anyway. No off switch (unlike the
    # online-refresh interval above): silently killing the key-dead alert
    # by tweaking a "refresh interval" setting would be a real footgun.
    KEY_CHECK_INTERVAL_KEY: NumericSetting(
        "admin-setting-key-check",
        DEFAULT_KEY_CHECK_INTERVAL_MIN,
        min=1,
        max=60,
    ),
}


TOAST_PREVIEW_MAX_CHARS = 100
