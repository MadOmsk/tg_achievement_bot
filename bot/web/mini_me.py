"""JSON payload for ``GET /api/mini/me`` — panel-shaped, cache-only."""

from __future__ import annotations

from typing import Any

from bot.constants import Platform, PresenceState, TokenStatus
from bot.db.repo import PlatformLink, Repo, User
from bot.services.profile_links import (
    psn_profile_url,
    steam_profile_url,
    xbox_profile_url,
)
from bot.services.stats import counters_for, week_cutoff_utc
from bot.views.parts import visibility_status_text


async def build_me_payload(
    repo: Repo,
    *,
    tg_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    is_admin: bool,
) -> dict[str, Any]:
    await repo.ensure_user(tg_id, username, first_name=first_name, last_name=last_name)
    user = await repo.get_user(tg_id)
    settings_row = await repo.get_user_settings(tg_id)
    steam = await repo.get_platform_link(tg_id, Platform.STEAM)
    psn = await repo.get_platform_link(tg_id, Platform.PSN)
    token = await repo.get_token(tg_id) if user and user.xuid else None
    chats = await repo.user_chats(tg_id)

    locale = (settings_row.locale if settings_row else None) or "ru"
    tz_offset = settings_row.tz_offset_min if settings_row else None
    show_links = bool(settings_row and settings_row.show_profile_links)
    show_secrets = bool(settings_row and settings_row.show_secrets)

    xbox_count = await repo.xbox_achievement_count(tg_id) if user and user.xuid else 0
    xbox_completed = await repo.xbox_completed_games_count(user.xuid) if user and user.xuid else 0
    steam_count = await repo.platform_achievement_count(tg_id, Platform.STEAM) if steam else 0
    steam_completed = await repo.steam_completed_games_count(tg_id) if steam else 0
    psn_count = await repo.platform_achievement_count(tg_id, Platform.PSN) if psn else 0
    psn_tiers = await repo.psn_trophy_tier_counts(tg_id) if psn else (0, 0, 0, 0)
    psn_platinum = psn_tiers[3]
    counters = await counters_for(repo, tg_id)
    week_xbox, week_steam, week_psn = await repo.achievement_platform_breakdown(
        tg_id, week_cutoff_utc()
    )

    return {
        "tg_id": tg_id,
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
        "is_admin": is_admin,
        "is_excluded": bool(user and user.is_excluded),
        "settings": {
            "locale": locale,
            "tz_offset_min": tz_offset,
            "show_profile_links": show_links,
            "show_secrets": show_secrets,
            # Which achievements go out, in every chat (#126).
            "rarity_mode": settings_row.rarity_mode if settings_row else "all",
        },
        "xbox": await _xbox_block(
            repo,
            user,
            token,
            xbox_count,
            xbox_completed,
            day=counters.today_xbox,
            week=week_xbox,
            month=counters.month_xbox,
        ),
        "steam": await _steam_block(
            repo,
            steam,
            steam_count,
            steam_completed,
            locale,
            day=counters.today_steam,
            week=week_steam,
            month=counters.month_steam,
        ),
        "psn": await _psn_block(
            repo,
            psn,
            psn_count,
            psn_platinum,
            psn_tiers,
            locale,
            day=counters.today_psn,
            week=week_psn,
            month=counters.month_psn,
        ),
        "chats": [
            {
                "chat_id": c.chat_id,
                "title": c.title,
                "is_subscribed": c.is_subscribed,
            }
            for c in chats
        ],
        "publication": await _publication(repo, user),
    }


async def _xbox_block(
    repo: Repo,
    user: User | None,
    token: Any,
    count: int,
    completed: int,
    day: int,
    week: int,
    month: int,
) -> dict[str, Any]:
    linked = bool(user and user.xuid)
    gamertag = user.gamertag if user else None
    status = token.status if token else None
    presence = None
    if linked and user and user.xuid:
        presence = await _xbox_presence(repo, user.xuid)
    return {
        "linked": linked,
        "gamertag": gamertag,
        "gamertag_modern": user.gamertag_modern if user else None,
        "xuid": user.xuid if user else None,
        "gamerscore": user.gamerscore if user else None,
        "achievement_count": count,
        "completed_games": completed,
        "day": day,
        "week": week,
        "month": month,
        "token_status": status,
        "needs_reconnect": status == TokenStatus.INVALID,
        "profile_url": xbox_profile_url(gamertag) if gamertag else None,
        "presence": presence,
    }


async def _steam_block(
    repo: Repo,
    link: PlatformLink | None,
    count: int,
    completed: int,
    locale: str,
    day: int,
    week: int,
    month: int,
) -> dict[str, Any]:
    if link is None:
        return {"linked": False}
    presence = await _steam_presence(repo, link.external_id)
    return {
        "linked": True,
        "steam_id": link.external_id,
        "display_name": link.display_name,
        "secondary_name": link.secondary_name,
        "achievement_count": count,
        "completed_games": completed,
        "day": day,
        "week": week,
        "month": month,
        "visibility": visibility_status_text(link, locale),
        "achievements_visible": link.achievements_visible,
        "profile_url": steam_profile_url(link.external_id),
        "presence": presence,
    }


async def _psn_block(
    repo: Repo,
    link: PlatformLink | None,
    count: int,
    platinum: int,
    tiers: tuple[int, int, int, int],
    locale: str,
    day: int,
    week: int,
    month: int,
) -> dict[str, Any]:
    if link is None:
        return {"linked": False}
    presence = await _psn_presence(repo, link.external_id)
    name = link.display_name
    return {
        "linked": True,
        "account_id": link.external_id,
        "online_id": name,
        "secondary_name": link.secondary_name,
        "trophy_count": count,
        "platinum_count": platinum,
        "bronze": tiers[0],
        "silver": tiers[1],
        "gold": tiers[2],
        "day": day,
        "week": week,
        "month": month,
        "trophy_level": link.psn_trophy_level,
        "visibility": visibility_status_text(link, locale),
        "achievements_visible": link.achievements_visible,
        "profile_url": psn_profile_url(name) if name else None,
        "presence": presence,
    }


async def _xbox_presence(repo: Repo, xuid: str) -> dict[str, Any] | None:
    row = await repo.presence_of(xuid)
    if row is None:
        return None
    game = None
    if row.state == PresenceState.ONLINE and row.title_id:
        game = row.title_name or await repo.title_name(row.title_id) or row.title_id
    return {
        "state": row.state,
        "title_id": row.title_id,
        "title_name": game,
        "updated_at": row.updated_at,
    }


async def _steam_presence(repo: Repo, steam_id: str) -> dict[str, Any] | None:
    row = await repo.steam_presence_of(steam_id)
    if row is None:
        return None
    online = bool(row.gameid) or (row.persona_state is not None and row.persona_state > 0)
    return {
        "state": "Online" if online else "Offline",
        "game_name": row.game_name,
        "persona_state": row.persona_state,
        "updated_at": row.updated_at,
    }


async def _psn_presence(repo: Repo, account_id: str) -> dict[str, Any] | None:
    row = await repo.psn_presence_of(account_id)
    if row is None:
        return None
    return {
        "state": row.state,
        "game_name": row.title_name,
        "updated_at": row.updated_at,
    }


async def _publication(repo: Repo, user: User | None) -> dict[str, Any]:
    if user is None:
        return {"excluded": False, "chat_titles": []}
    if user.is_excluded:
        return {"excluded": True, "chat_titles": []}
    titles = await repo.chats_of_user(user.tg_id)
    return {"excluded": False, "chat_titles": titles}
