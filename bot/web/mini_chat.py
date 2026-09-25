"""Cache-only JSON for Mini App chat screens (feed, online, summary, person)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from bot.constants import Platform, PresenceState, SettingKey, account_platform_of
from bot.db.repo import (
    CachedDescription,
    ChatMemberStat,
    ChatPresenceRow,
    RecentAchievement,
    Repo,
    TitleProgress,
    User,
    UserChatRow,
)
from bot.i18n import translator
from bot.services.achievement_icons import format_achievement_icon_url
from bot.services.naming import person_name, xbox_nickname
from bot.services.presence_view import pick_presence
from bot.services.stats import counters_for, month_window_utc, week_cutoff_utc
from bot.util import utcnow
from bot.views.notification import _group_label
from bot.views.online import presence_display_name, presence_text
from bot.views.parts import PLATFORM_ICON, PLATFORM_ICON_UNKNOWN, trophy_tier_badge
from bot.views.summary import _MONTH_KEYS, DAY_WINDOW_HOURS, month_window_label

FEED_DEFAULT = 500
FEED_MAX = 500
_MONTH_KEY = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
DEFAULT_STATS_GAMES_LIMIT = 15


def _https_url(url: str | None) -> str | None:
    """Mini App is always HTTPS — plain http:// icon URLs are mixed content
    and the browser drops them (Xbox store-images still hand out http).
    Legacy Xbox 360 achievement icons live on http://image.xboxlive.com without SSL,
    so we proxy them through /api/mini/x360-icon/{title_hex}/{image_hex}.
    """
    if not url:
        return None
    if url.startswith("http://image.xboxlive.com/global/t."):
        parts = url.split("/")
        if len(parts) >= 8 and parts[4].startswith("t."):
            title_hex = parts[4][2:]
            image_hex = parts[7].removesuffix(".png")
            return f"/api/mini/x360-icon/{title_hex}/{image_hex}"
    if url.startswith("http://"):
        return "https://" + url[len("http://") :]
    return url


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


async def _person_month(
    repo: Repo, tg_id: int, month: str | None
) -> tuple[str, datetime, datetime, str, int]:
    """Calendar month in this person's timezone (not a chat's)."""
    settings_row = await repo.get_user_settings(tg_id)
    tz = settings_row.tz_offset_min if settings_row else None
    current = _calendar_month_key(tz)
    parsed = parse_month_key(month or current)
    if parsed is None:
        raise ValueError("bad month")
    since, until = month_window_utc(parsed[0], parsed[1], tz)
    key = f"{parsed[0]:04d}-{parsed[1]:02d}"
    return key, since, until, current, parsed[1]


async def _person_month_choices(repo: Repo, tg_id: int, *extra: str) -> list[str]:
    months = await repo.person_unlock_months(tg_id)
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
    rows = await repo.chat_recent(chat_id, limit, locale=locale, since=since, until=until)
    descriptions = await _localized_feed_descriptions(repo, rows, locale)
    progress = await _feed_progress(repo, rows)
    return {
        "items": [_feed_item_json(row, descriptions, progress, locale) for row in rows],
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
    subscribers = await repo.chat_subscribers(chat_id)
    games = await repo.users_games_achievements(
        [s.tg_id for s in subscribers],
        since,
        rare_threshold=threshold,
        limit=0,
        locale=locale,
        until=until,
        order="count",
    )
    # Same calendar-month window as games/month leaders — finds and
    # "hunting together" on the Mini App stats tab read this list, not a
    # separate feed fetch that can drift to another month.
    recent_rows = await repo.chat_recent(
        chat_id, FEED_DEFAULT, locale=locale, since=since, until=until
    )
    rare_rows = await repo.chat_ultra_rares(
        chat_id, since=since, until=until, max_percent=0.5, locale=locale
    )
    descriptions = await _localized_feed_descriptions(repo, [*recent_rows, *rare_rows], locale)
    progress = await _feed_progress(repo, [*recent_rows, *rare_rows])
    label = (
        _month_label(month_num, locale)
        if key != current
        else month_window_label(settings.tz_offset_min, locale)
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
                "icon_url": _https_url(g.icon_url),
            }
            for g in games
        ],
        "recent": [_feed_item_json(row, descriptions, progress, locale) for row in recent_rows],
        "rares": [_feed_item_json(row, descriptions, progress, locale) for row in rare_rows],
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
    key, month_since, month_until, current, _n = await _person_month(repo, target.tg_id, month)
    months = await _person_month_choices(repo, target.tg_id, current, key)
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
                "trophy_count": await repo.platform_achievement_count(target.tg_id, Platform.PSN),
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
    # Rarity diamonds on the games list: use the club's threshold when the
    # card was opened from a club (same number that chat publishes with),
    # otherwise the global default. Still never filters which games appear.
    settings = await repo.get_chat_daily_settings(chat_id) if chat_id is not None else None
    rare_threshold = settings.rare_threshold_percent if settings else 10.0
    game_rows = await repo.users_games_achievements(
        [target.tg_id],
        month_since,
        rare_threshold=rare_threshold,
        limit=games_limit,
        locale=locale,
        until=month_until,
    )
    games = [
        {
            "title_id": g.title_id,
            "name": g.name,
            "unlocked": g.count,
            "gamerscore": g.score,
            "platform": g.platform,
        }
        for g in game_rows
    ]

    feed_rows = await repo.person_recent(
        target.tg_id, FEED_DEFAULT, locale=locale, since=month_since, until=month_until
    )
    descriptions = await _localized_feed_descriptions(repo, feed_rows, locale)
    progress = await _feed_progress(repo, feed_rows)

    presence = pick_presence(
        xbox=await repo.presence_of(target.xuid) if target.xuid else None,
        steam=await repo.steam_presence_of(steam.external_id) if steam else None,
        psn=await repo.psn_presence_of(psn.external_id) if psn else None,
    )
    presence_json = None
    if presence is not None:
        presence_json = {
            "state": "Online" if presence.online else "Offline",
            "playing": bool(presence.online and presence.title_id),
            "platform": presence.platform if presence.online else None,
            "title_name": presence.game if presence.online else None,
        }

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
        "presence": presence_json,
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
        "feed": [_feed_item_json(row, descriptions, progress, locale) for row in feed_rows],
    }


def _feed_item_json(
    row: RecentAchievement,
    descriptions: dict[tuple[str, str, str], str | None],
    progress: dict[tuple[str, str, str, str | None], TitleProgress | None],
    locale: str,
) -> dict[str, Any]:
    prog = progress.get((row.platform, row.xuid, row.title_id, row.trophy_group_id))
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
        "icon_url": format_achievement_icon_url(
            row.platform, row.title_id, row.achievement_id, row.icon_url
        ),
        "game_icon_url": _https_url(row.game_icon_url),
        "description": descriptions.get(
            (row.platform, row.title_id, row.achievement_id), row.description
        ),
        "trophy_type": row.trophy_type,
        "tier_badge": trophy_tier_badge(row.trophy_type) or None,
        "progress": _progress_json(prog, row.game, locale),
    }


async def _feed_progress(
    repo: Repo, rows: list[RecentAchievement]
) -> dict[tuple[str, str, str, str | None], TitleProgress | None]:
    """Batch `title_progress` for the feed — one lookup per distinct
    (account, title, group), same numbers the Telegram card prints (#46)."""
    cache: dict[tuple[str, str, str, str | None], TitleProgress | None] = {}
    for row in rows:
        if not row.xuid or not row.title_id:
            continue
        key = (row.platform, row.xuid, row.title_id, row.trophy_group_id)
        if key in cache:
            continue
        cache[key] = await repo.title_progress(
            account_platform_of(row.platform),
            row.xuid,
            row.title_id,
            row.trophy_group_id,
        )
    return cache


def _progress_json(
    progress: TitleProgress | None,
    title: str | None,
    locale: str,
) -> dict[str, Any] | None:
    if progress is None:
        return None
    out: dict[str, Any] = {"unlocked": progress.unlocked, "total": progress.total}
    if progress.has_dlc:
        out["has_dlc"] = True
    if progress.group_total:
        out["group"] = {
            "name": _group_label(progress, title or "", locale, html=False),
            "unlocked": progress.group_unlocked,
            "total": progress.group_total,
            "is_default": progress.group_is_default,
        }
    return out


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
