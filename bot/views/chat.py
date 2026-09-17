"""The group screens: /stats, /recent, /who, the chat hub (#63).

/online has its own module (views/online.py) because the auto-refresh
poller draws it too; the daily summary has its own (poller/daily.py) for
the same reason. What lives here is everything a person asks for in a group
and reads once.
"""

from __future__ import annotations

from html import escape as html_escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
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
from bot.services.naming import (
    person_name,
    person_name_of,
    subscriber_names,
    xbox_nickname,
)
from bot.services.stats import counters_for, month_cutoff_utc
from bot.util import humanize_ago, thousands
from bot.version import version
from bot.views.inline_lists import InlineListing, button_rows
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
    repo: Repo, target: User, chat_id: int, i18n: I18nContext | None = None
) -> str | None:
    """Shared by /stats and /who's buttons (SPEC 6.3) — one implementation,
    so a player's card looks the same no matter how it was opened.

    `chat_id` is what the games list counts rare achievements against: the
    threshold is per chat and admin-set, never a number hardcoded here
    (CLAUDE.md's own publication rule), so the same person's card can
    legitimately mark a different number of games as rare in two chats.

    Works for a Steam-only person too (SPEC 9, M-Steam-2e) — used to bail
    out on `not target.xuid` alone, which meant no card at all for anyone
    without Xbox connected."""
    platform_links = await repo.platform_links_of(target.tg_id)
    if not target.xuid and not platform_links:
        return None

    # Gates whether any nickname below becomes a clickable link at all — the
    # target's own choice (Follow-up 2026-09-06), off by default, and not
    # relaxed for the target viewing their own card: this card is one and
    # the same message regardless of who asked for it (no per-viewer
    # rendering), so "only hide it from others" isn't a distinction that
    # exists here. Own links live in /panel instead, which really is
    # per-viewer (never rendered in a group at all).
    settings_row = await repo.get_user_settings(target.tg_id)
    show_links = bool(settings_row and settings_row.show_profile_links)

    locale = _locale_of(i18n)
    tz_offset_min = settings_row.tz_offset_min if settings_row else None
    rare_threshold = (await repo.get_chat_daily_settings(chat_id)).rare_threshold_percent
    counters = await counters_for(repo, target.tg_id, rare_threshold=rare_threshold)
    lines = [f"👤 <b>{html_escape(display_name(target, platform_links))}</b>"]
    # Shared with /panel's own header (2026-09-08, user request: "пусть одни
    # одинаково формируются") — services/achievements.py::platform_header_lines.
    lines += await platform_header_lines(
        repo,
        tg_id=target.tg_id,
        xuid=target.xuid,
        gamertag=target.gamertag,
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
    # "За сутки" and "С 1 сентября" rather than "Сегодня"/"За месяц" (owner,
    # 2026-09-17): the first really is a rolling 24 hours, and the second has
    # been the calendar month since #14 — the games header below already said
    # "с 1 сентября", so one card was naming one window two ways.
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
            month=month_name(tz_offset_min, locale),
            achievements=plural_achievements(counters.month, locale),
            breakdown=month_breakdown,
            value=bracketed(
                value_parts(counters.month_score, counters.month_rare, counters.month_tiers)
            ),
        ),
        # No lifetime "Всего" here: seen_achievements is permanently
        # best-effort (title_history's cap, achievements with no unlock
        # date), so a lifetime count from it can't be trusted the way a
        # date-bounded one can — better absent than quietly wrong (SPEC 5.4).
    ]

    # One combined ranked list across every platform, not a section per
    # platform — same "one number, not one per platform" spirit as the
    # counters above. One query too, since 2026-09-17: this used to fire one
    # per linked account and merge them in Python, which applied the cap
    # twice (once per platform, once after the merge) and ranked by
    # gamerscore, so PSN and Steam — where gamerscore is always 0 — sank
    # below every Xbox game no matter what was actually played.
    # 0 = no cap (SPEC 6.4) — the list lives in a collapsible quote either
    # way, no separate "показать все игры" tap needed any more.
    limit = await _stats_games_limit(repo)
    since = month_cutoff_utc(tz_offset_min)
    games = await repo.users_games_achievements(
        [target.tg_id],
        since,
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
                window=month_window_label(tz_offset_min, locale),
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
        icon=icon,
        game=game,
        name=name,
        tail=tail_text,
        ago=humanize_ago(row.unlocked_at, _locale_of(i18n)),
    )


def hub_keyboard(
    bot_username: str, chat_id: int, i18n: I18nContext | None = None
) -> InlineKeyboardMarkup:
    """A short walkthrough, not a control panel: SPEC 6.3 walks through
    connect → publish in that order, so the keyboard should not offer more
    choices than that story needs. Steam's and PSN's connect buttons
    (SPEC 9, M-Steam-2e, M-PSN-1) sit next to Xbox's rather than adding a
    whole extra row each — it is still the same "connect" step, just
    another platform for it.

    Buttons act on whoever presses them — that is why "Публиковать мои
    достижения" is allowed here at all: SPEC 6.3 forbids rendering *someone
    else's* settings where any member could page through them, not a button
    that only ever touches the presser's own subscription.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_hub_text(i18n, "chat-hub-publish-button"), callback_data="sub:on"
                )
            ],
            [
                InlineKeyboardButton(
                    text=_hub_text(i18n, "chat-hub-xbox-button"),
                    # The chat id rides along in the deep-link payload so a
                    # successful login can auto-subscribe him right back here
                    # (SPEC 6.3) — see _parse_connect_payload in connect.py.
                    url=f"https://t.me/{bot_username}?start=connect{chat_id}",
                ),
                InlineKeyboardButton(
                    text=_hub_text(i18n, "chat-hub-psn-button"),
                    # No chat id here (unlike Xbox above) — see Steam's own
                    # button below for why (SPEC 9, M-PSN-1, handlers/psn.py,
                    # connect.py's ?start=connectpsn).
                    url=f"https://t.me/{bot_username}?start=connectpsn",
                ),
                InlineKeyboardButton(
                    text=_hub_text(i18n, "chat-hub-steam-button"),
                    # No chat id here (unlike Xbox above) — /connect_steam
                    # needs a profile link a button tap can't supply anyway,
                    # so this just opens the DM at the right prompt (SPEC 9,
                    # handlers/steam.py, connect.py's ?start=connectsteam).
                    url=f"https://t.me/{bot_username}?start=connectsteam",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_hub_text(i18n, "chat-hub-settings-button"),
                    url=f"https://t.me/{bot_username}?start=panel",
                ),
            ],
        ]
    )


def help_text(i18n: I18nContext) -> str:
    """What the bot is for, its commands, and — last line — which build is
    answering (#56, owner request). The version belongs here rather than in
    /admin alone: the question it answers is "is this the test bot or the
    real one", and anyone in the chat can have it."""
    return i18n.get("chat-help-text") + "\n\n" + i18n.get("chat-help-version", version=version())


async def hub_text(repo: Repo, chat_id: int, i18n: I18nContext) -> str:
    names = subscriber_names(await repo.chat_subscribers(chat_id))
    who = (
        i18n.get("chat-hub-nobody")
        if not names
        else i18n.get("chat-hub-publishing", names=", ".join(names))
    )
    # The version stays the last line of the whole message — under the
    # subscriber list, not buried above it.
    return (
        i18n.get("chat-help-text")
        + "\n\n"
        + who
        + "\n\n"
        + i18n.get("chat-help-version", version=version())
    )


def render_who_picker(rows: list[ChatPresenceRow], i18n: I18nContext) -> InlineKeyboardMarkup:
    """Everyone the chat has seen write, three to a row. The cancel button is
    not decoration: found live, there was no way out of this prompt except
    picking somebody, and it never went away after a pick either."""
    return InlineListing(
        rows=button_rows(rows, who_label, lambda row: f"who:stats:{row.tg_id}", per_row=3),
        tail=[
            InlineKeyboardButton(text=i18n.get("chat-cancel-button"), callback_data="who:cancel")
        ],
    ).markup()
