"""Data access. No SQL lives anywhere else in the project (CLAUDE.md).

Timestamps are UTC ISO strings; conversion to a person's timezone happens at
display time, never here.

Split (2026-09-09) out of what used to be one 2900-line repo.py into this
package, purely for navigability — no behavior changed, nothing outside
this package needed to change either: `from bot.db.repo import Repo` (and
every dataclass/`Database` import) keeps working exactly as before.

Layout:
    _database.py   the Database class — connection lifecycle, schema/
                    migration bring-up. Unrelated to Repo itself.
    _models.py      every dataclass Repo methods return, plus the row->
                    dataclass helpers shared by more than one mixin below.
    _accounts.py    users, Xbox tokens, per-user settings, app settings.
    _chats.py       chats, subscriptions, per-chat publication targets.
    _polling.py     poller target-fetching + presence-state saving, all
                    three platforms (trophy-scan and presence-poll cadences
                    for PSN are both here, side by side, but unrelated).
    _achievements.py  achievement/trophy insert+dedup, publication
                    bookkeeping, admin "reset & resync".
    _stats.py       Xbox title-history cache, achievement-count aggregates.
    _chat_stats.py  per-chat leaderboards, the monthly games block,
                    /online's merged presence + its auto-refresh state.
    _messages.py    self-dedup message tracking, /recent, recent-games
                    lookups, daily-report/publication markers, bot-message
                    cleanup tracking.
    _admin.py       /admin's own auto-refresh, its user/chat lists and
                    settings, plus the shared titles/HLTB caches that
                    happen to live in this same historical section.
    _platform_links.py  Steam's achievement schema/rarity caches, and the
                    generic platform_links table shared by Steam and PSN.
    _flood.py       anti-flood throttle state (notification_throttle,
                    2026-09-09) — added after the split, not part of the
                    original repo.py breakup.
    _descriptions.py  an achievement's names, descriptions and rarity in
                    the catalog (title_achievements; its own cache tables
                    until #119) — shared across every platform, unlike
                    _platform_links.py's Steam-specific schema/rarity
                    caches. Also added after the split.
    _steam.py       a game's Steam app, its guides' tips and its patch
                    notes (migration 069).
    _logins.py      ways in besides a Telegram update: email addresses and
                    their one-time codes, Telegram added later (#162).
    _notifications.py  the app's own notifications: the list per person and
                    the browsers that allowed push (#164).
    _merge.py       folding one person into another, in one transaction.
    _invites.py     invite codes members make, and who came by each (082).

Each mixin above is a plain class relying on `self._conn` — provided by
`Repo` itself below, not by a shared base class: this project runs no
static type checker (CLAUDE.md's own Tests section — just pytest and
ruff), so there is nothing to gain from one here that a comment doesn't
already say just as well.
"""

from __future__ import annotations

import aiosqlite

from bot.db.repo._accounts import _AccountsRepo
from bot.db.repo._achievements import _AchievementsRepo
from bot.db.repo._admin import _AdminRepo
from bot.db.repo._catalog import _CatalogRepo
from bot.db.repo._chat_stats import _ChatStatsRepo
from bot.db.repo._chats import _ChatsRepo
from bot.db.repo._database import (
    DEFAULT_APP_SETTINGS,
    MIGRATIONS_DIR,
    SCHEMA_PATH,
    Database,
)
from bot.db.repo._descriptions import _DescriptionsRepo
from bot.db.repo._flood import _FloodRepo
from bot.db.repo._follows import FollowTooSoon, PersonRow, _FollowsRepo
from bot.db.repo._handles import HandleInvalid, HandleState, HandleTooSoon, _HandlesRepo
from bot.db.repo._invites import InviteRow, _InvitesRepo
from bot.db.repo._logins import EmailCode, LoginTaken, _LoginsRepo
from bot.db.repo._merge import MergeChoices, MergeSide, _MergeRepo
from bot.db.repo._messages import _MessagesRepo
from bot.db.repo._models import (
    AchievementRow,
    AdminPanelRefreshRow,
    AdminUserRow,
    CachedDescription,
    ChatDailySettings,
    ChatMemberStat,
    ChatPresenceRow,
    ChatSubscriber,
    ChatTarget,
    CooldownCheckResult,
    DeletableMessage,
    FloodState,
    GameAchievements,
    HltbCacheRow,
    OnlineAutoRefreshRow,
    PlatformLink,
    PollTarget,
    PresenceRow,
    PsnPollTarget,
    PsnPresenceRow,
    PsnPresenceTarget,
    RecentAchievement,
    SteamPollTarget,
    SteamPresenceRow,
    SteamSchemaAchievement,
    TitleAchievementRow,
    TitleAchievementWithUnlock,
    TitleCoverRow,
    TitleHistoryRow,
    TitleHltbRow,
    TitleProgress,
    TokenRecord,
    User,
    UserChatRow,
    UserSettings,
)
from bot.db.repo._notifications import NotificationRow, PushSubscription, _NotificationsRepo
from bot.db.repo._platform_links import _PlatformLinksRepo
from bot.db.repo._polling import _PollingRepo
from bot.db.repo._sessions import _SessionsRepo
from bot.db.repo._stats import _StatsRepo
from bot.db.repo._steam import StoredPatch, TitleSteam, _SteamRepo

__all__ = [
    # Re-exported for scripts/backfill_*.py and the odd test that reaches
    # for a constant directly rather than through a Repo method — same
    # names, same values as before the split.
    "DEFAULT_APP_SETTINGS",
    "MIGRATIONS_DIR",
    "SCHEMA_PATH",
    "AchievementRow",
    "AdminPanelRefreshRow",
    "AdminUserRow",
    "CachedDescription",
    "ChatDailySettings",
    "ChatMemberStat",
    "ChatPresenceRow",
    "ChatSubscriber",
    "ChatTarget",
    "CooldownCheckResult",
    "Database",
    "DeletableMessage",
    "EmailCode",
    "FloodState",
    "FollowTooSoon",
    "GameAchievements",
    "HandleInvalid",
    "HandleState",
    "HandleTooSoon",
    "HltbCacheRow",
    "InviteRow",
    "LoginTaken",
    "MergeChoices",
    "MergeSide",
    "NotificationRow",
    "OnlineAutoRefreshRow",
    "PersonRow",
    "PlatformLink",
    "PollTarget",
    "PresenceRow",
    "PsnPollTarget",
    "PsnPresenceRow",
    "PsnPresenceTarget",
    "PushSubscription",
    "RecentAchievement",
    "Repo",
    "SteamPollTarget",
    "SteamPresenceRow",
    "SteamSchemaAchievement",
    "StoredPatch",
    "TitleAchievementRow",
    "TitleAchievementWithUnlock",
    "TitleCoverRow",
    "TitleHistoryRow",
    "TitleHltbRow",
    "TitleProgress",
    "TitleSteam",
    "TokenRecord",
    "User",
    "UserChatRow",
    "UserSettings",
]


class Repo(
    _AccountsRepo,
    _ChatsRepo,
    _PollingRepo,
    _AchievementsRepo,
    _StatsRepo,
    _ChatStatsRepo,
    _MessagesRepo,
    _AdminRepo,
    _PlatformLinksRepo,
    _FloodRepo,
    _DescriptionsRepo,
    _CatalogRepo,
    _SteamRepo,
    _HandlesRepo,
    _FollowsRepo,
    _SessionsRepo,
    _LoginsRepo,
    _NotificationsRepo,
    _MergeRepo,
    _InvitesRepo,
):
    """Every query in the project. Services call these; handlers call services."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @property
    def _conn(self) -> aiosqlite.Connection:
        return self._db.conn
