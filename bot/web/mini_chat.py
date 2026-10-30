"""Cache-only JSON for Mini App chat screens (feed, online, summary, person)."""

from __future__ import annotations

import dataclasses
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
from bot.db.repo._sql import MEMBERS_CHAT, pick_name
from bot.i18n import translator
from bot.services import game_page, time_zones
from bot.services.achievement_icons import format_achievement_icon_url
from bot.services.naming import person_name, xbox_nickname
from bot.services.presence_view import pick_presence
from bot.services.stats import counters_for, month_window_utc, week_cutoff_utc
from bot.services.time_zones import Tz
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


def person_label(*, person_id: int | None, handle: str | None = None) -> str:
    return person_name(person_id=person_id, handle=handle)


def parse_month_key(value: str) -> tuple[int, int] | None:
    match = _MONTH_KEY.fullmatch(value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _calendar_month_key(tz: Tz) -> str:
    local = time_zones.local_now(tz)
    return f"{local.year:04d}-{local.month:02d}"


def _month_label(month_num: int, locale: str) -> str:
    _ = translator("daily", locale)
    return _("daily-window-month", month=_(_MONTH_KEYS[month_num - 1]))


async def _club_month(
    repo: Repo, chat_id: int, month: str | None, *, tz_of: Tz = None, scoped: bool = False
) -> tuple[str, datetime, datetime, str, int]:
    # A hand-picked scope has no chat settings: it reads in the viewer's timezone.
    tz = tz_of if scoped else (await repo.get_chat_daily_settings(chat_id)).tz
    current = _calendar_month_key(tz)
    parsed = parse_month_key(month or current)
    if parsed is None:
        raise ValueError("bad month")
    since, until = month_window_utc(parsed[0], parsed[1], tz)
    key = f"{parsed[0]:04d}-{parsed[1]:02d}"
    return key, since, until, current, parsed[1]


async def _month_choices(
    repo: Repo, chat_id: int, *extra: str, members: list[int] | None = None
) -> list[str]:
    months = await repo.chat_unlock_months(chat_id, members=members)
    ordered: list[str] = []
    for ym in [*extra, *months]:
        if ym and ym not in ordered:
            ordered.append(ym)
    ordered.sort(reverse=True)
    return ordered


async def _person_month(
    repo: Repo, person_id: int, month: str | None
) -> tuple[str, datetime, datetime, str, int]:
    """Calendar month in this person's timezone (not a chat's)."""
    settings_row = await repo.get_user_settings(person_id)
    tz = settings_row.tz if settings_row else None
    current = _calendar_month_key(tz)
    parsed = parse_month_key(month or current)
    if parsed is None:
        raise ValueError("bad month")
    since, until = month_window_utc(parsed[0], parsed[1], tz)
    key = f"{parsed[0]:04d}-{parsed[1]:02d}"
    return key, since, until, current, parsed[1]


async def _person_month_choices(repo: Repo, person_id: int, *extra: str) -> list[str]:
    months = await repo.person_unlock_months(person_id)
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
    members: list[int] | None = None,
    tz_of: Tz = None,
) -> dict[str, Any]:
    limit = max(1, min(limit, FEED_MAX))
    key, since, until, current, _month_num = await _club_month(
        repo, chat_id, month, tz_of=tz_of, scoped=members is not None
    )
    rows = await repo.chat_recent(
        chat_id, limit, locale=locale, since=since, until=until, members=members
    )
    descriptions = await _localized_feed_descriptions(repo, rows, locale)
    progress = await _feed_progress(repo, rows)
    return {
        "items": await _feed_json(repo, rows, descriptions, progress, locale),
        "month": key,
        "current_month": current,
        "months": await _month_choices(repo, chat_id, current, key, members=members),
    }


async def build_online_payload(
    repo: Repo, chat_id: int, *, locale: str, members: list[int] | None = None
) -> dict[str, Any]:
    rows = await repo.chat_member_presence(chat_id, members=members)
    shown = []
    for row in rows:
        # What they play, as the catalog names it; the platform's word stands in.
        if row.state == PresenceState.ONLINE and row.title_id:
            name = await game_page.playing_name(repo, row.platform, row.title_id, locale)
            if name:
                row = dataclasses.replace(row, title_name=name)
        shown.append(_presence_json(row, locale))
    return {"members": shown}


async def build_summary_payload(
    repo: Repo,
    chat_id: int,
    *,
    locale: str,
    month: str | None = None,
    members: list[int] | None = None,
    tz_of: Tz = None,
) -> dict[str, Any]:
    scoped = members is not None
    if scoped:
        # The threshold is global (Publication rules); only the timezone is the viewer's.
        threshold = (await repo.get_chat_daily_settings(chat_id)).rare_threshold_percent
        tz = tz_of
    else:
        settings = await repo.get_chat_daily_settings(chat_id)
        threshold = settings.rare_threshold_percent
        tz = settings.tz
    key, since, until, current, month_num = await _club_month(
        repo, chat_id, month, tz_of=tz_of, scoped=scoped
    )
    day_rows = await repo.chat_member_stats(
        chat_id, utcnow() - timedelta(hours=DAY_WINDOW_HOURS), threshold, members=members
    )
    month_rows = await repo.chat_member_stats(
        chat_id, since, threshold, until=until, members=members
    )
    # The year of the month shown, from its first day in the same timezone up
    # to that month's end (owner, 2026-10-07).
    year = int(key[:4])
    year_since, _ = month_window_utc(year, 1, tz)
    year_rows = await repo.chat_member_stats(
        chat_id, year_since, threshold, until=until, members=members
    )
    if members is None:
        subscribers = await repo.chat_subscribers(chat_id)
        people = [s.person_id for s in subscribers]
    else:
        people = members
    games = await repo.users_games_achievements(
        people,
        since,
        rare_threshold=threshold,
        limit=0,
        locale=locale,
        until=until,
        # The month's games newest first, wherever the app lists them (owner,
        # 2026-10-27).
        order="recent",
    )
    # Same calendar-month window as games/month leaders — finds and
    # "hunting together" on the Mini App stats tab read this list, not a
    # separate feed fetch that can drift to another month.
    recent_rows = await repo.chat_recent(
        chat_id, FEED_DEFAULT, locale=locale, since=since, until=until, members=members
    )
    rare_rows = await repo.chat_ultra_rares(
        chat_id, since=since, until=until, max_percent=0.5, locale=locale, members=members
    )
    descriptions = await _localized_feed_descriptions(repo, [*recent_rows, *rare_rows], locale)
    progress = await _feed_progress(repo, [*recent_rows, *rare_rows])
    icons = {g.title_id: g.icon_url for g in games}
    label = _month_label(month_num, locale) if key != current else month_window_label(tz, locale)
    return {
        "month_key": key,
        "current_month": current,
        "month_label": label,
        "day": [_stat_json(row) for row in day_rows],
        "month": [_stat_json(row) for row in month_rows],
        "year": [_stat_json(row) for row in year_rows],
        "year_key": year,
        # What is played most, one card a catalog game (`month_games`).
        "games": [
            {
                **entry,
                "count": entry["unlocked"],
                "score": entry["gamerscore"],
                "icon_url": entry["poster"] or _https_url(icons.get(entry["title_id"])),
            }
            for entry in await month_games(repo, games, locale)
        ],
        "recent": await _feed_json(repo, recent_rows, descriptions, progress, locale),
        "rares": await _feed_json(repo, rare_rows, descriptions, progress, locale),
    }


async def build_person_payload(
    repo: Repo,
    target: User,
    *,
    locale: str,
    chat_id: int | None = None,
    month: str | None = None,
) -> dict[str, Any]:
    links = await repo.platform_links_of(target.id)
    counters = await counters_for(repo, target.id)
    week_xbox, week_steam, week_psn = await repo.achievement_platform_breakdown(
        target.id, week_cutoff_utc()
    )
    key, month_since, month_until, current, _n = await _person_month(repo, target.id, month)
    months = await _person_month_choices(repo, target.id, current, key)
    month_count, month_score = await repo.achievement_counts_for_person(
        target.id, month_since, month_until
    )
    month_points = await repo.points_for_person(target.id, month_since, month_until)
    month_xbox, month_steam, month_psn = await repo.achievement_platform_breakdown(
        target.id, month_since, until=month_until
    )
    platforms: list[dict[str, Any]] = []
    if target.xuid:
        xbox_count = await repo.xbox_achievement_count(target.id)
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
                "month_count": month_xbox,
                **await repo.account_facts(target.id, "xbox"),
            }
        )
    steam = next((link for link in links if link.platform == Platform.STEAM), None)
    psn_links = [link for link in links if link.platform == Platform.PSN]
    psn = psn_links[0] if psn_links else None
    if psn_links:
        bronze, silver, gold, platinum = await repo.psn_trophy_tier_counts(target.id)
        platforms.append(
            {
                "platform": Platform.PSN,
                # Several accounts (#10): one summed row, every nickname on it.
                "name": ", ".join(link.display_name or link.external_id for link in psn_links),
                "trophy_count": await repo.platform_achievement_count(target.id, Platform.PSN),
                "bronze": bronze,
                "silver": silver,
                "gold": gold,
                "platinum_count": platinum,
                # Summed like the counts above, not the first account's: the
                # highest level among them, and since when PSN has been linked.
                "trophy_level": max(
                    (link.psn_trophy_level for link in psn_links if link.psn_trophy_level),
                    default=None,
                ),
                "month_count": month_psn,
                "linked_at": min(
                    (link.linked_at for link in psn_links if link.linked_at), default=None
                ),
                **await repo.account_facts(target.id, Platform.PSN),
            }
        )
    if steam is not None:
        platforms.append(
            {
                "platform": Platform.STEAM,
                "name": steam.display_name,
                "achievement_count": await repo.platform_achievement_count(
                    target.id, Platform.STEAM
                ),
                "completed_games": await repo.steam_completed_games_count(target.id),
                "month_count": month_steam,
                "linked_at": steam.linked_at,
                **await repo.account_facts(target.id, Platform.STEAM),
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
        [target.id],
        month_since,
        rare_threshold=rare_threshold,
        limit=games_limit,
        locale=locale,
        until=month_until,
        order="recent",
    )
    games = await month_games(repo, game_rows, locale)

    feed_rows = await repo.person_recent(
        target.id,
        FEED_DEFAULT,
        locale=locale,
        since=month_since,
        until=month_until,
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
            "title_name": (
                await game_page.playing_name(repo, presence.platform, presence.title_id, locale)
                or presence.game
            )
            if presence.online
            else None,
        }

    return {
        "person_id": target.id,
        "tg_id": target.tg_id,
        "name": person_label(person_id=target.id, handle=target.handle),
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
            "points": month_points,
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
        "feed": await _feed_json(repo, feed_rows, descriptions, progress, locale),
    }


async def _feed_json(
    repo: Repo,
    rows: list[RecentAchievement],
    descriptions: dict[tuple[str, str, str], str | None],
    progress: dict[tuple[str, str, str, str | None], TitleProgress | None],
    locale: str,
) -> list[dict[str, Any]]:
    """Feed items, each naming and picturing its catalog's game (owner,
    2026-10-30); the progress stays its list's."""
    games = await game_page.games_of_lists(repo, [(r.platform, r.title_id) for r in rows], locale)
    return [
        _feed_item_json(
            row, descriptions, progress, locale, games.get((row.platform, row.title_id))
        )
        for row in rows
    ]


async def month_games(repo: Repo, rows: list, locale: str) -> list[dict[str, Any]]:
    """The month's games, one entry a catalog game (owner, 2026-10-30): a game
    played on several platforms is one card, its month's count summed, and
    `lists` keeps each platform's own list — whose progress is never summed.
    A list in no game yet is an entry of its own. In the rows' order."""
    found = await game_page.games_of_lists(repo, [(g.platform, g.title_id) for g in rows], locale)
    entries: dict[object, dict[str, Any]] = {}
    for g in rows:
        game = found.get((g.platform, g.title_id))
        key = game["game_id"] if game else (g.platform, g.title_id)
        entry = entries.get(key)
        if entry is None:
            entry = entries[key] = {
                "title_id": g.title_id,
                "platform": g.platform,
                "name": (game["name"] if game else None) or g.name,
                "unlocked": 0,
                "gamerscore": 0,
                "poster": game["poster"] if game else None,
                "game_id": game["game_id"] if game else None,
                "lists": [],
            }
        entry["unlocked"] += g.count
        entry["gamerscore"] += g.score or 0
        entry["lists"].append({"platform": g.platform, "title_id": g.title_id, "unlocked": g.count})
    return list(entries.values())


def _feed_item_json(
    row: RecentAchievement,
    descriptions: dict[tuple[str, str, str], str | None],
    progress: dict[tuple[str, str, str, str | None], TitleProgress | None],
    locale: str,
    game: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prog = progress.get((row.platform, row.xuid, row.title_id, row.trophy_group_id))
    return {
        "person_id": row.person_id,
        "tg_id": row.tg_id,
        "person": person_label(person_id=row.person_id, handle=row.handle),
        "name": row.name,
        # The catalog's game; a list in no game yet keeps its own name.
        "game": (game["name"] if game else None) or row.game,
        **game_page.game_fields(game),
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
        "mythic": row.mythic,
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
        "person_id": row.person_id,
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
        "person_id": row.person_id,
        "tg_id": row.tg_id,
        "name": person_label(person_id=row.person_id, handle=row.handle),
        "count": row.count,
        "score": row.score,
        "points": row.points,
        "rare": row.rare,
        "xbox": row.xbox_count,
        "steam": row.steam_count,
        "psn": row.psn_count,
    }


# Game news (owner, 2026-10-05): what the developers of the games one's circle
# plays posted on Steam that month. A game counts if somebody earned something
# in it within this long before the month ended — a patch for last month's game
# is news too.
NEWS_PLAYED_DAYS = 60
NEWS_MAX = 200
NEWS_EXCERPT = 220
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_BARE_URL = re.compile(r"^https?://\S+$")


def _news_excerpt(text: str | None) -> str:
    """The start of a post as plain words: links keep their label, a line that
    is only an address (a video, a picture) goes."""
    if not text:
        return ""
    lines = [
        _MD_LINK.sub(r"\1", line).strip()
        for line in text.splitlines()
        if not _BARE_URL.match(line.strip())
    ]
    words = " ".join(line.lstrip("- ").strip() for line in lines if line.strip())
    if len(words) <= NEWS_EXCERPT:
        return words
    return words[:NEWS_EXCERPT].rsplit(" ", 1)[0].rstrip(",;:-") + "…"


def news_game(
    game: dict[str, Any] | None,
    platform: str,
    title_id: str,
    list_name: str | None,
    list_icon: str | None,
) -> dict[str, Any]:
    """The game a developer's post is about, as the catalog has it; a list in
    no game yet keeps its own name and icon."""
    return {
        "game_id": game["game_id"] if game else None,
        "platform": platform,
        "title_id": title_id,
        "name": (game["name"] if game else None) or list_name,
        "icon_url": (game["poster"] if game else None) or list_icon,
        "hero": game["hero"] if game else None,
    }


def news_title(post: Any, locale: str) -> str:
    """A developer's post in the reader's language: our Russian once it is
    made (`poller/translations.py`), else Steam's English."""
    return post.title_ru if locale == "ru" and post.title_ru else post.title


def news_text(post: Any, locale: str) -> str:
    if locale == "ru" and post.title_ru:
        return post.text_ru or ""
    return post.text_en or ""


async def build_news_payload(
    repo: Repo,
    *,
    members: list[int],
    month: str | None,
    tz_of: int | None,
    locale: str,
    favorites_of: int | None = None,
) -> dict[str, Any]:
    """The month's developer posts: of the games the viewer's circle played, or,
    with `favorites_of`, of that person's favorite games only — what the feed
    mixes in (owner, 2026-10-26)."""
    key, _since, until, current, _month_num = await _club_month(
        repo, MEMBERS_CHAT, month, tz_of=tz_of, scoped=True
    )
    year, month_num = (int(part) for part in key.split("-"))
    first = f"{key}-01"
    after = f"{year + month_num // 12:04d}-{month_num % 12 + 1:02d}-01"
    if favorites_of is not None:
        rows = await repo.favorite_games_news(
            await repo.favorite_game_ids(favorites_of), since=first, until=after, limit=NEWS_MAX
        )
    else:
        rows = await repo.games_news(
            members,
            played_since=(until - timedelta(days=NEWS_PLAYED_DAYS)).isoformat(timespec="seconds"),
            since=first,
            until=after,
            limit=NEWS_MAX,
        )
    games = await game_page.games_of_lists(
        repo, [(row.platform, row.title_id) for row in rows], locale
    )
    return {
        "items": [
            {
                "gid": row.gid,
                "appid": row.steam_appid,
                "kind": row.kind,
                "title": news_title(row, locale),
                "date": row.published_at,
                "excerpt": _news_excerpt(news_text(row, locale)),
                # The whole post, pictures and videos as their own lines.
                "text": news_text(row, locale),
                "image": _https_url(row.image_url),
                "url": f"https://store.steampowered.com/news/app/{row.steam_appid}/view/{row.gid}",
                "game": news_game(
                    games.get((row.platform, row.title_id)),
                    row.platform,
                    row.title_id,
                    pick_name(locale, row.game_ru, row.game_en, row.game),
                    _https_url(row.game_icon_url),
                ),
            }
            for row in rows
        ],
        "month": key,
        "current_month": current,
        "months": await _month_choices(repo, MEMBERS_CHAT, current, key, members=members),
    }
