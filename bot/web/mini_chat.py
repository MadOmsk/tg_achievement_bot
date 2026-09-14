"""Cache-only JSON for Mini App chat screens (feed, online, summary, person)."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta
from typing import Any

from bot.constants import Platform, PresenceState, SettingKey
from bot.db.repo import (
    CachedDescription,
    ChatMemberStat,
    ChatPresenceRow,
    RecentAchievement,
    Repo,
    User,
    UserChatRow,
)
from bot.i18n import translator
from bot.poller.daily import _MONTH_KEYS, DAY_WINDOW_HOURS, _month_window_label
from bot.services.achievements import PLATFORM_ICON, PLATFORM_ICON_UNKNOWN, trophy_tier_badge
from bot.services.naming import person_name, xbox_nickname
from bot.services.online_view import presence_display_name, presence_text
from bot.services.stats import counters_for, month_window_utc, week_cutoff_utc
from bot.util import utcnow

FEED_DEFAULT = 500
FEED_MAX = 500
_MONTH_KEY = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
DEFAULT_STATS_GAMES_LIMIT = 15


async def chat_of_user(repo: Repo, tg_id: int, chat_id: int) -> UserChatRow | None:
    chats = await repo.user_chats(tg_id)
    return next((c for c in chats if c.chat_id == chat_id), None)


def person_label(
    *,
    tg_id: int,
    first_name: str | None = None,
    last_name: str | None = None,
    username: str | None = None,
    gamertag: str | None = None,
    gamertag_modern: str | None = None,
    steam_name: str | None = None,
    psn_name: str | None = None,
) -> str:
    return person_name(
        tg_id=tg_id,
        first_name=first_name,
        last_name=last_name,
        username=username,
        xbox=xbox_nickname(gamertag_modern=gamertag_modern, gamertag=gamertag),
        steam=steam_name,
        psn=psn_name,
    )


def parse_month_key(value: str) -> tuple[int, int] | None:
    match = _MONTH_KEY.fullmatch(value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _calendar_month_key(tz_offset_min: int | None) -> str:
    local = utcnow() + timedelta(minutes=tz_offset_min or 0)
    return f"{local.year:04d}-{local.month:02d}"


def _month_label(month_num: int, locale: str) -> str:
    _ = translator("daily", locale)
    return _("daily-window-month", month=_(_MONTH_KEYS[month_num - 1]))


async def _club_month(
    repo: Repo, chat_id: int, month: str | None
) -> tuple[str, datetime, datetime, str, int]:
    settings = await repo.get_chat_daily_settings(chat_id)
    tz = settings.tz_offset_min
    current = _calendar_month_key(tz)
    parsed = parse_month_key(month or current)
    if parsed is None:
        raise ValueError("bad month")
    since, until = month_window_utc(parsed[0], parsed[1], tz)
    key = f"{parsed[0]:04d}-{parsed[1]:02d}"
    return key, since, until, current, parsed[1]


async def _month_choices(repo: Repo, chat_id: int, *extra: str) -> list[str]:
    months = await repo.chat_unlock_months(chat_id)
    ordered: list[str] = []
    for ym in [*extra, *months]:
        if ym and ym not in ordered:
            ordered.append(ym)
    ordered.sort(reverse=True)
    return ordered


async def build_feed_payload(
    repo: Repo,
    chat_id: int,
    *,
    locale: str,
    limit: int = FEED_DEFAULT,
    month: str | None = None,
) -> dict[str, Any]:
    limit = max(1, min(limit, FEED_MAX))
    key, since, until, current, _month_num = await _club_month(repo, chat_id, month)
    rows = await repo.chat_recent(chat_id, limit, since=since, until=until)
    descriptions = await _localized_feed_descriptions(repo, rows, locale)
    return {
        "items": [_feed_item_json(row, descriptions) for row in rows],
        "month": key,
        "current_month": current,
        "months": await _month_choices(repo, chat_id, current, key),
    }


async def build_online_payload(repo: Repo, chat_id: int, *, locale: str) -> dict[str, Any]:
    rows = await repo.chat_member_presence(chat_id)
    return {"members": [_presence_json(row, locale) for row in rows]}


async def build_summary_payload(
    repo: Repo, chat_id: int, *, locale: str, month: str | None = None
) -> dict[str, Any]:
    settings = await repo.get_chat_daily_settings(chat_id)
    threshold = settings.rare_threshold_percent
    key, since, until, current, month_num = await _club_month(repo, chat_id, month)
    day_rows = await repo.chat_member_stats(
        chat_id, utcnow() - timedelta(hours=DAY_WINDOW_HOURS), threshold
    )
    month_rows = await repo.chat_member_stats(chat_id, since, threshold, until=until)
    games = await repo.chat_top_games(chat_id, since, 15, until=until)
    label = _month_label(month_num, locale) if key != current else _month_window_label(
        settings.tz_offset_min, locale
    )
    return {
        "month_key": key,
        "current_month": current,
        "month_label": label,
        "day": [_stat_json(row) for row in day_rows],
        "month": [_stat_json(row) for row in month_rows],
        "games": [
            {
                "title_id": g.title_id,
                "platform": g.platform,
                "name": g.name,
                "count": g.count,
                "score": g.score,
                "bronze": g.bronze,
                "silver": g.silver,
                "gold": g.gold,
                "platinum": g.platinum,
                "icon_url": g.icon_url,
            }
            for g in games
        ],
    }


async def build_person_payload(
    repo: Repo,
    target: User,
    *,
    locale: str,
    chat_id: int | None = None,
    month: str | None = None,
) -> dict[str, Any]:
    links = await repo.platform_links_of(target.tg_id)
    counters = await counters_for(repo, target.tg_id)
    week_xbox, week_steam, week_psn = await repo.achievement_platform_breakdown(
        target.tg_id, week_cutoff_utc()
    )
    if chat_id is not None:
        key, month_since, month_until, current, _n = await _club_month(repo, chat_id, month)
        months = await _month_choices(repo, chat_id, current, key)
    else:
        settings_row = await repo.get_user_settings(target.tg_id)
        tz = settings_row.tz_offset_min if settings_row else None
        parsed = parse_month_key(_calendar_month_key(tz))
        if parsed is None:
            raise ValueError("bad month")
        month_since, month_until = month_window_utc(parsed[0], parsed[1], tz)
        key = current = f"{parsed[0]:04d}-{parsed[1]:02d}"
        months = [key]
    month_count, month_score = await repo.achievement_counts_for_person(
        target.tg_id, month_since, month_until
    )
    month_xbox, month_steam, month_psn = await repo.achievement_platform_breakdown(
        target.tg_id, month_since, until=month_until
    )
    platforms: list[dict[str, Any]] = []
    if target.xuid:
        xbox_count = await repo.xbox_achievement_count(target.tg_id)
        xbox_completed = await repo.xbox_completed_games_count(target.xuid)
        platforms.append(
            {
                "platform": Platform.XBOX_MODERN,
                "name": xbox_nickname(
                    gamertag_modern=target.gamertag_modern, gamertag=target.gamertag
                ),
                "achievement_count": xbox_count,
                "completed_games": xbox_completed,
                "gamerscore": target.gamerscore or 0,
            }
        )
    steam = next((link for link in links if link.platform == Platform.STEAM), None)
    psn = next((link for link in links if link.platform == Platform.PSN), None)
    if psn is not None:
        bronze, silver, gold, platinum = await repo.psn_trophy_tier_counts(target.tg_id)
        platforms.append(
            {
                "platform": Platform.PSN,
                "name": psn.display_name,
                "trophy_count": await repo.platform_achievement_count(
                    target.tg_id, Platform.PSN
                ),
                "bronze": bronze,
                "silver": silver,
                "gold": gold,
                "platinum_count": platinum,
                "trophy_level": psn.psn_trophy_level,
            }
        )
    if steam is not None:
        platforms.append(
            {
                "platform": Platform.STEAM,
                "name": steam.display_name,
                "achievement_count": await repo.platform_achievement_count(
                    target.tg_id, Platform.STEAM
                ),
                "completed_games": await repo.steam_completed_games_count(target.tg_id),
            }
        )

    games_limit = await repo.get_int_setting(
        SettingKey.STATS_GAMES_LIMIT, DEFAULT_STATS_GAMES_LIMIT
    )
    external_ids = [target.xuid] if target.xuid else []
    external_ids += [link.external_id for link in links]
    games: list[dict[str, Any]] = []
    if external_ids:
        per_source = await asyncio.gather(
            *(
                repo.recent_games(external_id, month_since, limit=games_limit, until=month_until)
                for external_id in external_ids
            )
        )
        merged = sorted(
            (game for source in per_source for game in source),
            key=lambda g: (g.gamerscore or 0, g.unlocked or 0),
            reverse=True,
        )[: games_limit or None]
        games = [
            {
                "name": g.name,
                "unlocked": g.unlocked,
                "gamerscore": g.gamerscore,
                "platform": g.platform,
            }
            for g in merged
        ]

    feed_rows = await repo.person_recent(
        target.tg_id, FEED_DEFAULT, since=month_since, until=month_until
    )
    descriptions = await _localized_feed_descriptions(repo, feed_rows, locale)

    return {
        "tg_id": target.tg_id,
        "name": person_label(
            tg_id=target.tg_id,
            first_name=target.first_name,
            last_name=target.last_name,
            username=target.username,
            gamertag=target.gamertag,
            gamertag_modern=target.gamertag_modern,
            steam_name=next(
                (link.display_name for link in links if link.platform == Platform.STEAM), None
            ),
            psn_name=next(
                (link.display_name for link in links if link.platform == Platform.PSN), None
            ),
        ),
        "platforms": platforms,
        "today": {
            "count": counters.today,
            "score": counters.today_score,
            "xbox": counters.today_xbox,
            "steam": counters.today_steam,
            "psn": counters.today_psn,
        },
        "month": {
            "count": month_count,
            "score": month_score,
            "xbox": month_xbox,
            "steam": month_steam,
            "psn": month_psn,
        },
        "week": {
            "count": week_xbox + week_steam + week_psn,
            "xbox": week_xbox,
            "steam": week_steam,
            "psn": week_psn,
        },
        "month_key": key,
        "current_month": current,
        "months": months,
        "games": games,
        "feed": [_feed_item_json(row, descriptions) for row in feed_rows],
    }


def _feed_item_json(
    row: RecentAchievement, descriptions: dict[tuple[str, str, str], str | None]
) -> dict[str, Any]:
    return {
        "tg_id": row.tg_id,
        "person": person_label(
            tg_id=row.tg_id,
            first_name=row.first_name,
            last_name=row.last_name,
            username=row.username,
            gamertag=row.gamertag,
            gamertag_modern=row.gamertag_modern,
            steam_name=row.steam_name,
            psn_name=row.psn_name,
        ),
        "name": row.name,
        "game": row.game,
        "gamerscore": row.gamerscore,
        "rarity_percent": row.rarity_percent,
        "platform": row.platform,
        "unlocked_at": row.unlocked_at,
        "is_secret": row.is_secret,
        "title_id": row.title_id,
        "achievement_id": row.achievement_id,
        "icon_url": row.icon_url,
        "game_icon_url": row.game_icon_url,
        "description": descriptions.get(
            (row.platform, row.title_id, row.achievement_id), row.description
        ),
        "trophy_type": row.trophy_type,
        "tier_badge": trophy_tier_badge(row.trophy_type) or None,
    }


async def _localized_feed_descriptions(
    repo: Repo, rows: list[RecentAchievement], locale: str
) -> dict[tuple[str, str, str], str | None]:
    keys = [
        (row.platform, row.title_id, row.achievement_id)
        for row in rows
        if row.title_id and row.achievement_id
    ]
    if not keys:
        return {}
    cached = await repo.cached_descriptions(keys)
    out: dict[tuple[str, str, str], str | None] = {}
    for key in keys:
        entry = cached.get(key)
        text = _description_for_locale(entry, locale) if entry is not None else None
        if text:
            out[key] = text
    return out


def _description_for_locale(cached: CachedDescription, locale: str) -> str | None:
    text = cached.description_en if locale == "en" else cached.description_ru
    return text if text and text.strip() else None


def _presence_json(row: ChatPresenceRow, locale: str) -> dict[str, Any]:
    online = row.state == PresenceState.ONLINE
    if online:
        icon = PLATFORM_ICON.get(row.platform, PLATFORM_ICON_UNKNOWN)
    else:
        icon = PLATFORM_ICON_UNKNOWN
    return {
        "tg_id": row.tg_id,
        "name": presence_display_name(row),
        "state": row.state,
        "platform": row.platform,
        "title_name": row.title_name if online else None,
        "playing": bool(online and row.title_id),
        "status": presence_text(row, locale),
        "icon": icon,
    }


def _stat_json(row: ChatMemberStat) -> dict[str, Any]:
    return {
        "tg_id": row.tg_id,
        "name": person_label(
            tg_id=row.tg_id,
            first_name=row.first_name,
            last_name=row.last_name,
            username=row.username,
            gamertag=row.gamertag,
            gamertag_modern=row.gamertag_modern,
            steam_name=row.steam_name,
            psn_name=row.psn_name,
        ),
        "count": row.count,
        "score": row.score,
        "rare": row.rare,
        "xbox": row.xbox_count,
        "steam": row.steam_count,
        "psn": row.psn_count,
    }
