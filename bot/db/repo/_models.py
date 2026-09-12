"""Every dataclass returned by Repo's methods, plus the row->dataclass
helpers shared by more than one mixin. Split out of what used to be one
2900-line bot/db/repo.py (2026-09-09) — see this package's own __init__.py
for why and how the split is organized; nothing about behavior changed,
only where each piece of it lives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import aiosqlite

from bot.constants import RarityMode


@dataclass(slots=True)
class User:
    tg_id: int
    username: str | None
    xuid: str | None
    gamertag: str | None
    gamerscore: int | None
    is_excluded: bool
    last_online_at: str | None
    # /stats' header identity (Follow-up 2026-09-06) — see users.first_name
    # in schema.sql for how these get refreshed.
    first_name: str | None = None
    last_name: str | None = None
    # Xbox's ModernGamertag, the first step of the Xbox chain (#51) —
    # `gamertag` above stays the classic one. Defaulted so the many call
    # sites that build a User by hand keep working.
    gamertag_modern: str | None = None


@dataclass(slots=True)
class TokenRecord:
    tg_id: int
    refresh_token_enc: bytes
    status: str
    fail_count: int
    last_refresh_at: str | None
    invalid_at: str | None
    notify_count: int
    last_notified_at: str | None


@dataclass(slots=True)
class UserSettings:
    tg_id: int
    tz_offset_min: int | None
    show_profile_links: bool
    # This person's own language for DMs (#48); a group follows its own
    # chat_settings.locale instead. Defaulted rather than required so the
    # many test/call sites that build a UserSettings by hand keep working.
    locale: str = "ru"


@dataclass(slots=True)
class PollTarget:
    """A user the poller may look at, with his last known presence."""

    tg_id: int
    xuid: str
    state: str | None
    title_id: str | None
    title_name: str | None
    changed_at: str | None
    last_ach_poll_at: str | None
    updated_at: str | None


@dataclass(slots=True)
class SteamPollTarget:
    """Steam's counterpart of `PollTarget` (SPEC 9, M-Steam-2c) — same
    shape, Steam's own field names (`persona_state`/`gameid`/`game_name`
    instead of `state`/`title_id`/`title_name`)."""

    tg_id: int
    steam_id: str
    persona_state: int | None
    gameid: str | None
    game_name: str | None
    changed_at: str | None
    last_ach_poll_at: str | None
    updated_at: str | None
    # Sticky through brief presence gaps — see steam_presence_state's own
    # comment (schema.sql) and poller/steam_presence.py's grace period.
    last_active_gameid: str | None = None
    last_active_game_name: str | None = None
    last_active_at: str | None = None


@dataclass(slots=True)
class PsnPollTarget:
    """A linked PSN account the trophy poller may look at (SPEC 9, M-PSN-2)
    — no presence fields at all, unlike PollTarget/SteamPollTarget: trophy
    sync has no signal to key off, so there is nothing here but who to poll
    and when they were last checked."""

    tg_id: int
    account_id: str
    online_id: str | None
    last_polled_at: str | None
    # #21: False until backfill() has finished this account's first-ever
    # scan. poller/psn_fetcher.py's tick() skips a target that is still
    # False — polling it would race the in-flight backfill and publish the
    # account's whole trophy history at once.
    backfill_done: bool = True


@dataclass(slots=True)
class PsnPresenceTarget:
    """A linked PSN account the *presence* poller may look at (issue #1) —
    separate from PsnPollTarget above, which is the trophy poller's own
    unrelated cadence. No last_ach_poll_at here: presence has never driven
    trophy polling on PSN (see psn_presence_state's own schema.sql
    comment), so there is nothing to debounce against."""

    tg_id: int
    account_id: str
    state: str | None
    title_id: str | None
    title_name: str | None
    changed_at: str | None
    updated_at: str | None
    # The stored online ID, so the poller can tell a rename from a no-op
    # without a second query (#51) — the value it replaces is this
    # platform's own "previous online ID" step.
    online_id: str | None = None


@dataclass(slots=True)
class AchievementRow:
    title_id: str
    achievement_id: str
    name: str
    description: str | None
    icon_url: str | None
    unlocked_at: str | None
    gamerscore: int
    rarity_percent: float | None
    platform: str
    title_name: str | None = None
    is_secret: bool = False
    trophy_type: str | None = None  # PSN's tier — bronze/silver/gold/platinum, NULL elsewhere
    # The per-platform external id this row belongs to (SteamID64/xuid/PSN
    # account_id) — every seen_achievements row always has one, but only
    # unpublished_achievements() below actually populates it: that's the one
    # caller (poller/flood_flush.py) that can't assume every row in its list
    # shares a single xuid the way every other AchievementRow list in the
    # codebase does (2026-09-09, anti-flood filter spans every platform a
    # person has, not just one).
    xuid: str | None = None


@dataclass(slots=True)
class ChatTarget:
    chat_id: int
    title: str | None
    min_gamerscore: int
    muted_title_ids: list[str]
    # Always explicit per chat, no shared fallback (SPEC 5.5, 5.7) — every
    # chat gets a real value the moment it's created.
    rare_threshold_percent: float
    daily_summary_time: str
    tz_offset_min: int
    # Anti-flood (2026-09-09 user request), admin-set per chat like the
    # fields above — 0 disables it for this chat. See poller/flood_flush.py.
    # Defaults match chat_settings' own schema defaults, same reasoning as
    # digest_threshold's default below: only call sites with no real row to
    # read from (tests mostly) ever see the default instead of a real value.
    flood_limit: int = 3
    flood_window_minutes: int = 60
    # The language everything published to this chat renders in (#48).
    # Carried on the target itself rather than looked up per message: the
    # publisher already loops over these, and a second query per chat on the
    # hot publication path would buy nothing.
    locale: str = "ru"
    # The person's own choice for *this* chat (SPEC 9, M-Steam-2e's
    # follow-up — moved off user_settings, one value for every chat, onto
    # subscriptions, one value per chat). Defaults to 'all' only for call
    # sites (admin_chats) that have no one specific subscriber in mind.
    rarity_mode: str = RarityMode.ALL
    # N+ achievements in one game at once collapse into a summary message
    # instead of separate ones — per (person, chat), same follow-up as
    # rarity_mode above and for the same reason (2026-09-05). Default only
    # applies to call sites (admin_chats) with no one specific subscriber.
    digest_threshold: int = 3
    # Filled in by the admin panel only; the publisher never looks at them.
    is_active: bool = True
    daily_summary: bool = True
    subscribers: int = 0


@dataclass(slots=True)
class ChatDailySettings:
    """The same few per-chat values as on `ChatTarget`, fetched alone for
    call sites (chat.py's /summary) that have a chat_id but no reason to pull
    the rest of the chat/subscriber JOIN."""

    rare_threshold_percent: float
    daily_summary_time: str
    tz_offset_min: int
    # Every caller of this already hands all of the above to build_summary,
    # which needs the chat's language for the same render (#48) — fetching it
    # here keeps that one query, and keeps the locale impossible to forget.
    locale: str = "ru"


@dataclass(slots=True)
class FloodState:
    """One `notification_throttle` row (2026-09-09 user request) — see
    schema.sql's own comment on that table for the full picture.
    `count_in_window` and `throttled` are meaningless to callers that only
    ever read the `throttled = 1` rows (poller/flood_flush.py's own sweep),
    but cost nothing to carry along either."""

    tg_id: int
    chat_id: int
    window_started_at: datetime
    count_in_window: int
    throttled: bool


@dataclass(slots=True)
class CachedDescription:
    """One `achievement_description_cache` row (2026-09-09 user request) —
    see schema.sql's own comment on that table for what `source` means."""

    description_ru: str | None
    description_en: str | None
    source: str


@dataclass(slots=True)
class DeletableMessage:
    """What `last_non_system_bot_message` returns (2026-09-09 user request)
    — /delete_last needs to show *what* it's about to delete, not just a
    bare id, so its own confirmation can name the message back."""

    message_id: int
    preview: str | None


@dataclass(slots=True)
class UserChatRow:
    """One chat a person has ever touched — subscribed at some point, or
    just seen writing there (SPEC 6.2's "Мои чаты") — with whether they are
    publishing there right now."""

    chat_id: int
    title: str | None
    is_subscribed: bool
    rarity_mode: str | None  # only meaningful while subscribed; None otherwise
    digest_threshold: int | None  # same — per subscription, None while not subscribed


@dataclass(slots=True)
class AdminUserRow:
    """A row of /admin's own user list — was Xbox-only (`WHERE u.xuid IS
    NOT NULL`, admin_users() below), so a Steam-only person never showed up
    in the admin panel at all (2026-09-05 follow-up, SPEC 9 M-Steam-2e:
    the same class of gap /stats had before it summed both platforms).
    `xuid` and the Steam fields are each optional now — never both None,
    admin_users() only returns someone connected on at least one."""

    tg_id: int
    gamertag: str | None
    username: str | None
    xuid: str | None
    gamerscore: int | None
    is_excluded: bool
    last_online_at: str | None
    token_status: str | None
    last_refresh_at: str | None
    steam_id: str | None = None
    steam_name: str | None = None
    psn_account_id: str | None = None
    psn_online_id: str | None = None
    # The rest of what the person chain needs (#51) — this row carried only
    # `gamertag`/`username`, so the roster sorted people under whichever
    # platform happened to answer first.
    first_name: str | None = None
    last_name: str | None = None
    gamertag_modern: str | None = None


@dataclass(slots=True)
class PresenceRow:
    xuid: str
    state: str | None
    title_id: str | None
    title_name: str | None
    updated_at: str | None


@dataclass(slots=True)
class SteamPresenceRow:
    """Steam's counterpart of PresenceRow — raw persona_state/gameid, not
    normalized to Xbox's state vocabulary (that stitching is chat_member_
    presence()'s own job, SPEC 9 M-Steam-2e); the admin card (2026-09-05
    follow-up) reads these two fields directly instead."""

    steam_id: str
    persona_state: int | None
    gameid: str | None
    game_name: str | None
    updated_at: str | None


@dataclass(slots=True)
class PsnPresenceRow:
    """PSN's counterpart of PresenceRow (issue #1) — already normalized to
    the same Online/Offline vocabulary (PresenceState), unlike
    SteamPresenceRow's raw persona_state: PSN's own presence has no
    numeric enum of its own to preserve, `get_presence()`'s onlineStatus
    is translated once, in services/psn/client.py::get_presence."""

    account_id: str
    state: str | None
    title_id: str | None
    title_name: str | None
    updated_at: str | None


@dataclass(slots=True)
class ChatPresenceRow:
    """One row of /online (SPEC 6.3): a subscribed member plus his presence.

    `state`/`title_id`/`title_name` are already normalized to Xbox's own
    vocabulary regardless of which platform they actually came from (SPEC 9,
    M-Steam-2e) — the query picks whichever platform's presence updated more
    recently and translates Steam's own persona_state/gameid into the same
    shape, so the "playing/online/offline" wording never needs to know
    Steam presence exists. `platform` is exposed separately, only for the
    icon colour next to the name — not mixed into `state`.
    """

    tg_id: int
    gamertag: str | None
    xuid: str | None  # can be unset for a Steam-only person
    state: str | None
    title_id: str | None
    title_name: str | None
    platform: str  # whichever platform state/title_id/title_name came from
    # Xbox's ModernGamertag, the first step of the Xbox chain (#51).
    gamertag_modern: str | None = None
    # Follow-up 2026-09-08 — services/online_view.py's row label: the
    # platform-specific nickname of `platform` above, or (platform == "none")
    # the Telegram name/username fallback. See chat_member_presence()'s
    # docstring for why gamertag alone stopped being enough.
    steam_display_name: str | None = None
    psn_display_name: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


@dataclass(slots=True)
class OnlineAutoRefreshRow:
    """One chat's live-updating /online table (Follow-up 2026-09-05,
    poller/online_refresh.py). Timestamps are raw ISO strings, like
    everywhere else in this module — the poller parses them."""

    chat_id: int
    message_id: int
    created_at: str
    last_updated_at: str


@dataclass(slots=True)
class AdminPanelRefreshRow:
    """One admin's live-updating /admin screen (Follow-up 2026-09-06,
    poller/admin_refresh.py) — same shape as OnlineAutoRefreshRow above,
    just keyed by admin tg_id instead of chat_id."""

    admin_id: int
    message_id: int
    created_at: str
    last_updated_at: str


@dataclass(slots=True)
class ChatMemberStat:
    tg_id: int
    gamertag: str | None
    xuid: str | None  # can be unset for a Steam-only person (SPEC 9, M-Steam-2e)
    count: int
    score: int
    rare: int
    # Behind `count`'s single combined total (2026-09-05 follow-up) — a
    # parenthetical next to it, not a second sort key or a second row.
    xbox_count: int = 0
    steam_count: int = 0
    psn_count: int = 0
    # Everything services/naming.py::person_name needs (#51) — the leaderboard
    # used to carry only `gamertag`, so a member with no Xbox account had no
    # name to render and fell through to a bare "id<tg_id>".
    gamertag_modern: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    steam_name: str | None = None
    psn_name: str | None = None


@dataclass(slots=True)
class RecentAchievement:
    gamertag: str | None
    name: str
    game: str | None
    gamerscore: int
    rarity_percent: float | None
    platform: str
    unlocked_at: str | None
    is_secret: bool = False
    # Same as ChatMemberStat above (#51): /recent rendered "кто-то" for
    # anyone without an Xbox account, for the same reason.
    tg_id: int = 0
    gamertag_modern: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    steam_name: str | None = None
    psn_name: str | None = None


@dataclass(slots=True)
class TopGame:
    name: str | None
    gamerscore: int | None
    unlocked: int | None
    platform: str | None = None


@dataclass(slots=True)
class ChatTopGame:
    """One row of the monthly summary's own games block (#7) — a game
    someone in the chat played this window, and how many achievements/
    trophies the chat's subscribed members earned in it combined, across
    everyone who played it. Unlike `TopGame` (one *person's* own recent
    games), this is a chat-wide aggregate — but still one platform per row:
    a title_id is always in that platform's own id format (an Xbox numeric
    id, a Steam appid, or a PSN "NPWR..." string), so it can never actually
    span two platforms in practice, unlike the union `seen_achievements`
    itself is queried from.

    `bronze`/`silver`/`gold`/`platinum` are PSN's own trophy tiers (#5, user
    request) — always 0 for a non-PSN row, no separate NULL handling needed
    since a tier count of 0 already renders as "nothing to show" the same
    way `score == 0` does for gamerscore.
    """

    title_id: str
    platform: str
    name: str | None
    count: int
    score: int = 0
    bronze: int = 0
    silver: int = 0
    gold: int = 0
    platinum: int = 0


@dataclass(slots=True)
class TitleHistoryRow:
    title_id: str
    name: str
    platform: str
    current_gamerscore: int | None
    max_gamerscore: int | None
    achievements_unlocked: int | None
    achievements_total: int | None
    last_played_at: str | None


@dataclass(slots=True)
class HltbCacheRow:
    hltb_id: int
    name: str
    release_year: int | None
    main_hours: float | None
    extra_hours: float | None
    completionist_hours: float | None
    platforms: list[str] = field(default_factory=list)
    game_url: str | None = None
    image_url: str | None = None
    genre: str | None = None
    description_en: str | None = None
    description_ru: str | None = None


@dataclass(slots=True)
class PlatformLink:
    tg_id: int
    platform: str
    external_id: str
    display_name: str | None
    linked_at: str
    # The middle step of this platform's naming chain (#51): Steam's vanity,
    # PSN's previous online ID. See schema.sql's own column comment.
    secondary_name: str | None = None
    # Account-wide PSN level (Follow-up 2026-09-06) — always None for a
    # Steam row, or a PSN row the poller hasn't cached one for yet.
    psn_trophy_level: int | None = None
    # Whether the shared service credential could see this account's
    # achievements/trophies as of the last check (#5) — None until checked
    # once, then True/False. See schema.sql's own column comment for why
    # this needs re-checking beyond the coarser connect-time profile check.
    achievements_visible: bool | None = None
    # When the check above last ran (UTC ISO string), or None if never.
    achievements_visible_checked_at: str | None = None


@dataclass(slots=True)
class SteamSchemaAchievement:
    """One achievement's game-level (not per-person) data — the game's
    achievement list itself, cached forever (SPEC 9, M-Steam-2b)."""

    apiname: str
    icon: str | None
    hidden: bool


def _as_user(row: aiosqlite.Row) -> User:
    return User(
        tg_id=row["tg_id"],
        username=row["username"],
        xuid=row["xuid"],
        gamertag=row["gamertag"],
        gamerscore=row["gamerscore"],
        is_excluded=bool(row["is_excluded"]),
        last_online_at=row["last_online_at"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        gamertag_modern=row["gamertag_modern"],
    )


def _as_token(row: aiosqlite.Row) -> TokenRecord:
    return TokenRecord(
        tg_id=row["tg_id"],
        refresh_token_enc=row["refresh_token_enc"],
        status=row["status"],
        fail_count=row["fail_count"],
        last_refresh_at=row["last_refresh_at"],
        invalid_at=row["invalid_at"],
        notify_count=row["notify_count"],
        last_notified_at=row["last_notified_at"],
    )


def _as_user_settings(row: aiosqlite.Row) -> UserSettings:
    return UserSettings(
        tg_id=row["tg_id"],
        tz_offset_min=row["tz_offset_min"],
        show_profile_links=bool(row["show_profile_links"]),
        locale=row["locale"],
    )


def _iso(moment: datetime) -> str:
    """Stored timestamps are UTC ISO strings truncated to seconds."""
    return moment.astimezone(UTC).isoformat(timespec="seconds")
