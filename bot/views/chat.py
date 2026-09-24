"""The group screens: /stats, /recent, /who, the chat hub (#63).

/online has its own module (views/online.py) because the auto-refresh
poller draws it too; the daily summary has its own (poller/daily.py) for
the same reason. What lives here is everything a person asks for in a group
and reads once.
"""

from __future__ import annotations

from html import escape as html_escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram_i18n import I18nContext

from bot.constants import SettingKey
from bot.db.repo import (
    ChatPresenceRow,
    GameAchievements,
    PlatformLink,
    RecentAchievement,
    Repo,
    User,
)
from bot.i18n import DEFAULT_LOCALE, gettext
from bot.services.mini_app import mini_app_group_url, mini_app_open_url
from bot.services.naming import (
    person_name,
    person_name_of,
    subscriber_names,
    xbox_nickname,
)
from bot.services.platform_format import format_game_platforms
from bot.services.stats import counters_for, local_now, month_cutoff_utc
from bot.util import humanize_ago, thousands
from bot.version import version
from bot.views.inline_lists import InlineListing, button_rows
from bot.views.keyboards import close_button
from bot.views.lists import Listing, games_listing, truncate_name
from bot.views.parts import (
    PLATFORM_ICON,
    PLATFORM_ICON_UNKNOWN,
    bracketed,
    platform_breakdown_suffix,
    platform_header_lines,
    plural_achievements,
    rarity_badge,
    trophy_tier_badge,
    value_parts,
)
from bot.views.summary import month_name, month_window_label

DEFAULT_STATS_GAMES_LIMIT = 15


async def _stats_games_limit(repo: Repo) -> int:
    return await repo.get_int_setting(SettingKey.STATS_GAMES_LIMIT, DEFAULT_STATS_GAMES_LIMIT)


def _hub_text(i18n: I18nContext | None, key: str, **kwargs: object) -> str:
    return (
        i18n.get(key, **kwargs)
        if i18n is not None
        else gettext("chat", key, locale=DEFAULT_LOCALE, **kwargs)
    )


def _locale_of(i18n: I18nContext | None) -> str:
    """The locale this render belongs to (#48). In a group the middleware has
    already resolved `i18n.locale` to that chat's own setting, which is
    exactly what everything built here needs; the None case is the handful of
    internal callers that render without an aiogram context at all."""
    return i18n.locale if i18n is not None else DEFAULT_LOCALE


def _games_list(games: list[GameAchievements], i18n: I18nContext | None = None) -> str:
    """/stats' own games list — the shared template over one person (2026-09-17)."""
    locale = _locale_of(i18n)
    return games_listing(games, _hub_text(i18n, "chat-untitled"), locale).render()


def display_name(target: User, links: list[PlatformLink]) -> str:
    """The Telegram identity, not a platform gamertag (Follow-up
    2026-09-06, user request) — the card already lists every connected
    platform's own name on its own line below (XBOX/Steam/PSN), so the
    header identifying *the person* rather than defaulting to whichever
    platform happened to be Xbox reads better once someone has more than
    one. first_name/last_name only exist once UsernameMiddleware (below)
    has seen at least one message from them — a brand-new /start with
    nothing yet falls through to a platform name as a last resort.

    One of four hand-rolled versions of this chain until #51; now just the
    shared one, handed whichever platform links this person happens to
    have."""
    return person_name_of(target, links)


def who_label(row: ChatPresenceRow) -> str:
    """/who's picker button (#40) — identify *the person*, the same chain
    /stats' header uses, never a bare "idNNNN" for someone who has anything
    else. `chat_member_presence` already carries every field it needs (the
    #38 /online work joined them in), so no extra lookup per row."""
    return person_name(
        tg_id=row.tg_id,
        first_name=row.first_name,
        last_name=row.last_name,
        username=row.username,
        xbox=xbox_nickname(gamertag_modern=row.gamertag_modern, gamertag=row.gamertag),
        steam=row.steam_display_name,
        psn=row.psn_display_name,
    )


async def build_stats_text(
    repo: Repo,
    target: User,
    chat_id: int,
    i18n: I18nContext | None = None,
    *,
    target_year: int | None = None,
    target_month: int | None = None,
) -> str | None:
    """Shared by /stats and /who's buttons (SPEC 6.3) — one implementation,
    so a player's card looks the same no matter how it was opened."""
    platform_links = await repo.platform_links_of(target.tg_id)
    if not target.xuid and not platform_links:
        return None

    settings_row = await repo.get_user_settings(target.tg_id)
    show_links = bool(settings_row and settings_row.show_profile_links)

    locale = _locale_of(i18n)
    tz_offset_min = settings_row.tz_offset_min if settings_row else None
    rare_threshold = (await repo.get_chat_daily_settings(chat_id)).rare_threshold_percent
    counters = await counters_for(
        repo,
        target.tg_id,
        rare_threshold=rare_threshold,
        target_year=target_year,
        target_month=target_month,
    )
    lines = [f"👤 <b>{html_escape(display_name(target, platform_links))}</b>"]
    lines += await platform_header_lines(
        repo,
        tg_id=target.tg_id,
        xuid=target.xuid,
        gamertag=target.gamertag,
        gamertag_modern=target.gamertag_modern,
        gamerscore=target.gamerscore,
        platform_links=platform_links,
        show_links=show_links,
        locale=locale,
    )

    today_breakdown = platform_breakdown_suffix(
        counters.today_xbox, counters.today_steam, counters.today_psn
    )
    month_breakdown = platform_breakdown_suffix(
        counters.month_xbox, counters.month_steam, counters.month_psn
    )

    now_local = local_now(tz_offset_min)
    is_current_month = (
        target_year is None
        or target_month is None
        or (target_year == now_local.year and target_month == now_local.month)
    )

    if is_current_month:
        m_label = month_name(tz_offset_min, locale)
        window_label = month_window_label(tz_offset_min, locale)
    else:
        assert target_month is not None
        assert target_year is not None
        from bot.views.date_picker import target_month_labels

        m_label, window_label = target_month_labels(
            target_year, target_month, now_local.year, locale
        )

    lines += [
        "",
        _hub_text(
            i18n,
            "chat-stats-today",
            achievements=plural_achievements(counters.today, locale),
            breakdown=today_breakdown,
            value=bracketed(
                value_parts(counters.today_score, counters.today_rare, counters.today_tiers)
            ),
        ),
        _hub_text(
            i18n,
            "chat-stats-month",
            month=m_label,
            achievements=plural_achievements(counters.month, locale),
            breakdown=month_breakdown,
            value=bracketed(
                value_parts(counters.month_score, counters.month_rare, counters.month_tiers)
            ),
        ),
    ]

    limit = await _stats_games_limit(repo)
    if target_year is not None and target_month is not None:
        from bot.services.stats import month_window_utc

        since, until = month_window_utc(target_year, target_month, tz_offset_min)
    else:
        since = month_cutoff_utc(tz_offset_min)
        until = None

    games = await repo.users_games_achievements(
        [target.tg_id],
        since,
        until=until,
        rare_threshold=rare_threshold,
        limit=limit,
        locale=locale,
    )
    if games:
        lines += [
            "",
            _hub_text(
                i18n,
                "chat-stats-games-header",
                window=window_label,
            ),
            _games_list(games, i18n),
        ]
    return "\n".join(lines)


def recent_list(rows: list[RecentAchievement], i18n: I18nContext | None = None) -> str:
    return Listing(rows=[_recent_row(row, i18n) for row in rows]).render()


def _recent_row(row: RecentAchievement, i18n: I18nContext | None = None) -> str:
    # A real Telegram spoiler works fine inside a blockquote (unlike the old
    # <pre> table it replaced, SPEC 7.1) — the real name stays hidden behind
    # a tap, instead of a placeholder that gave nothing away to look up.
    name = html_escape(truncate_name(row.name))
    if row.is_secret:
        name = f'<span class="tg-spoiler">{name}</span>'
    # Leads the line instead of a fixed "🏆" bullet (2026-09-05) — now that
    # rarity_badge() always returns something (diamond or cup, never
    # empty), a separate generic bullet would double up with it on every
    # "common" row: two trophies back to back on the same line.
    #
    # PSN leads with its own tier instead (owner, 2026-09-17), the same swap
    # the achievement card has always made: the tier already answers "how
    # rare" on Sony's scale, and a platinum trophy and an "ordinary" rarity
    # badge are the same 🏆 — so every PSN row here read as ordinary.
    badge = trophy_tier_badge(row.trophy_type) or rarity_badge(row.rarity_percent)
    gamertag = html_escape(
        truncate_name(
            person_name(
                tg_id=row.tg_id,
                first_name=row.first_name,
                last_name=row.last_name,
                username=row.username,
                xbox=xbox_nickname(gamertag_modern=row.gamertag_modern, gamertag=row.gamertag),
                steam=row.steam_name,
                psn=row.psn_name,
            )
        )
    )
    game = html_escape(truncate_name(row.game or _hub_text(i18n, "chat-untitled")))
    icon = PLATFORM_ICON.get(row.platform, PLATFORM_ICON_UNKNOWN)
    plat = format_game_platforms(row.game_platforms, row.platform, device=row.device, short=True)
    icon_tag = f"({icon} <i>{plat}</i>)" if plat else icon
    # Found live: every Steam row showed a flat "+0 G" — Steam achievements
    # have no gamerscore at all (services/steam/achievements.py), same
    # "0 is 0 on any platform, don't name it" rule the achievement message
    # itself already follows (services/achievements.py's _rarity_line).
    # Rarity here is a bare percentage, with no label — the badge
    # already says "rare or not", the number is just the detail behind it.
    tail = []
    if row.gamerscore:
        tail.append(f"+{thousands(row.gamerscore)} G")
    if row.rarity_percent is not None:
        tail.append(f"{row.rarity_percent:g}%")
    tail_text = f" ({' · '.join(tail)})" if tail else ""
    return _hub_text(
        i18n,
        "chat-recent-row",
        badge=badge,
        gamertag=gamertag,
        icon=icon_tag,
        game=game,
        name=name,
        tail=tail_text,
        ago=humanize_ago(row.unlocked_at, _locale_of(i18n)),
    )


def hub_keyboard(
    bot_username: str,
    chat_id: int,
    i18n: I18nContext | None = None,
    *,
    mini_app_url: str = "",
    is_group: bool = True,
) -> InlineKeyboardMarkup:
    """A short walkthrough and quick navigation:
    1. App button (Open the app) - top row if configured
    2. Platforms to connect (Xbox, PSN, Steam)
    3. Management:
       - In groups: Publish toggle ('Настройка уведомлений') + Settings ('Настройки')
       - In private chat: Settings ('Настройки')
    """
    rows: list[list[InlineKeyboardButton]] = []
    app_url = (mini_app_url or "").strip()
    if app_url:
        if is_group:
            # A plain link, not a `web_app` button: Telegram answers
            # BUTTON_TYPE_INVALID for a WebApp button anywhere but a private
            # chat. `?startapp=` opens the same Mini App and carries this chat's
            # id, so it lands on the club the reader is standing in instead of a
            # chooser.
            rows.append(
                [
                    InlineKeyboardButton(
                        text=_hub_text(i18n, "chat-hub-open-app"),
                        url=mini_app_group_url(bot_username, chat_id=chat_id),
                    )
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=_hub_text(i18n, "chat-hub-open-app"),
                        web_app=WebAppInfo(url=mini_app_open_url(app_url, chat_id=chat_id)),
                    )
                ]
            )

    # In groups: add action rows and management
    settings_btn = InlineKeyboardButton(
        text=_hub_text(i18n, "chat-hub-settings-button"),
        url=f"https://t.me/{bot_username}?start=panel",
    )
    if is_group:
        # Action row 1: who, online, recent
        rows.append(
            [
                InlineKeyboardButton(
                    text=_hub_text(i18n, "chat-hub-who-button"),
                    callback_data="hub:who",
                ),
                InlineKeyboardButton(
                    text=_hub_text(i18n, "chat-hub-online-button"),
                    callback_data="hub:online",
                ),
                InlineKeyboardButton(
                    text=_hub_text(i18n, "chat-hub-recent-button"),
                    callback_data="hub:recent",
                ),
            ]
        )
        # Action row 2: summary day and month
        rows.append(
            [
                InlineKeyboardButton(
                    text=_hub_text(i18n, "chat-hub-summary-day-button"),
                    callback_data="hub:summary_day",
                ),
                InlineKeyboardButton(
                    text=_hub_text(i18n, "chat-hub-summary-month-button"),
                    callback_data="hub:summary_month",
                ),
            ]
        )
        # Action row 3: management (publish toggle + settings)
        rows.append(
            [
                InlineKeyboardButton(
                    text=_hub_text(i18n, "chat-hub-publish-button"), callback_data="sub:on"
                ),
                settings_btn,
            ]
        )
    else:
        # In private chat: settings
        rows.append([settings_btn])

    # Platforms row (at the bottom)
    xbox_url = (
        f"https://t.me/{bot_username}?start=connect{chat_id}"
        if is_group
        else f"https://t.me/{bot_username}?start=connect"
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=_hub_text(i18n, "chat-hub-xbox-button"),
                url=xbox_url,
            ),
            InlineKeyboardButton(
                text=_hub_text(i18n, "chat-hub-psn-button"),
                url=f"https://t.me/{bot_username}?start=connectpsn",
            ),
            InlineKeyboardButton(
                text=_hub_text(i18n, "chat-hub-steam-button"),
                url=f"https://t.me/{bot_username}?start=connectsteam",
            ),
        ]
    )
    rows.append([close_button(i18n=i18n)])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def help_text(i18n: I18nContext) -> str:
    """The list of chat commands for /help (#19)."""
    return i18n.get("chat-help-text")


async def hub_text(repo: Repo, chat_id: int, i18n: I18nContext) -> str:
    names = subscriber_names(await repo.chat_subscribers(chat_id))
    escaped_names = [html_escape(name) for name in names]
    who = (
        i18n.get("chat-hub-nobody")
        if not names
        else i18n.get("chat-hub-publishing", names=", ".join(escaped_names))
    )
    # The version stays the last line of the whole message — under the
    # subscriber list, not buried above it.
    return (
        i18n.get("chat-panel-text")
        + "\n\n"
        + who
        + "\n\n"
        + i18n.get("chat-help-version", version=version())
    )


def render_who_picker(rows: list[ChatPresenceRow], i18n: I18nContext) -> InlineKeyboardMarkup:
    """Everyone the chat has seen write, three to a row. The close button is
    not decoration: found live, there was no way out of this prompt except
    picking somebody, and it never went away after a pick either."""
    return InlineListing(
        rows=button_rows(rows, who_label, lambda row: f"who:stats:{row.tg_id}", per_row=3),
        tail=[close_button(i18n=i18n)],
    ).markup()
