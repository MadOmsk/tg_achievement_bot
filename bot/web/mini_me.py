"""JSON payload for ``GET /api/mini/me`` — panel-shaped, cache-only."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from bot.constants import (
    MAX_PSN_ACCOUNTS,
    AccountPlatform,
    Platform,
    PresenceState,
    TokenStatus,
)
from bot.db.repo import PlatformLink, Repo, User
from bot.services.admin_settings import SHOW_LINKS_DEFAULT, SHOW_LINKS_KEY
from bot.services.handles import CHANGE_COOLDOWN_DAYS
from bot.services.naming import link_nickname
from bot.services.profile_links import (
    psn_profile_url,
    steam_profile_url,
    xbox_profile_url,
)
from bot.services.stats import counters_for, week_cutoff_utc
from bot.util import utcnow
from bot.views.parts import visibility_status_text


async def handle_block(repo: Repo, person_id: int) -> dict[str, Any] | None:
    """The person's nickname for the Mini App (#157): the parts, the displayed
    form, whether they have been asked to keep it yet, and when it may change."""
    state = await repo.handle_state(person_id)
    if state is None or state.handle is None:
        return None
    next_change = None
    if state.confirmed and state.changed_at:
        due = datetime.fromisoformat(state.changed_at) + timedelta(days=CHANGE_COOLDOWN_DAYS)
        if due > utcnow():
            next_change = due.isoformat(timespec="seconds")
    return {
        "name": state.handle.name,
        "number": state.handle.number or None,
        "display": state.handle.display,
        "confirmed": state.confirmed,
        "next_change_at": next_change,
    }


async def build_me_payload(
    repo: Repo,
    *,
    person_id: int,
    tg_id: int | None,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    is_admin: bool,
) -> dict[str, Any]:
    if tg_id is not None:
        # The app's first call on opening: keep Telegram's names fresh.
        await repo.ensure_user(tg_id, username, first_name=first_name, last_name=last_name)
    await repo.give_handle(person_id)
    user = await repo.get_user(person_id)
    settings_row = await repo.get_user_settings(person_id)
    steam = await repo.get_platform_link(person_id, Platform.STEAM)
    psn_links = await repo.platform_links_for(person_id, Platform.PSN)
    psn = psn_links[0] if psn_links else None
    token = await repo.get_token(person_id) if user and user.xuid else None
    # Chats are Telegram's: somebody who signed in another way has none.
    chats = await repo.user_chats(tg_id) if tg_id is not None else []

    locale = (settings_row.locale if settings_row else None) or "ru"
    tz_offset = settings_row.tz_offset_min if settings_row else None
    # The admin's switch for everybody (owner, 2026-09-29), no longer a person's.
    show_links = bool(await repo.get_int_setting(SHOW_LINKS_KEY, int(SHOW_LINKS_DEFAULT)))
    show_secrets = bool(settings_row and settings_row.show_secrets)

    xbox_count = await repo.xbox_achievement_count(person_id) if user and user.xuid else 0
    xbox_completed = await repo.xbox_completed_games_count(user.xuid) if user and user.xuid else 0
    steam_count = await repo.platform_achievement_count(person_id, Platform.STEAM) if steam else 0
    steam_completed = await repo.steam_completed_games_count(person_id) if steam else 0
    psn_count = await repo.platform_achievement_count(person_id, Platform.PSN) if psn else 0
    psn_tiers = await repo.psn_trophy_tier_counts(person_id) if psn else (0, 0, 0, 0)
    psn_platinum = psn_tiers[3]
    counters = await counters_for(repo, person_id)
    week_xbox, week_steam, week_psn = await repo.achievement_platform_breakdown(
        person_id, week_cutoff_utc()
    )

    return {
        "person_id": person_id,
        "tg_id": tg_id,
        "handle": await handle_block(repo, person_id),
        # A picture chosen in the app replaces the Telegram photo (#157).
        "avatar_custom": bool(await repo.custom_avatar_path(person_id)),
        "notifications_unread": await repo.unread_notifications(person_id),
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
            "notify_followers": bool(settings_row.notify_followers) if settings_row else True,
            # Where notifications go (#164); Telegram only matters with Telegram.
            "notify_push": bool(settings_row.notify_push) if settings_row else True,
            "notify_telegram": bool(settings_row.notify_telegram) if settings_row else True,
            # Whose new posts are told about: friends / following / none.
            "notify_posts": settings_row.notify_posts if settings_row else "friends",
            # A switch per kind of notice.
            "notify_new_posts": bool(settings_row.notify_new_posts) if settings_row else True,
            "notify_friends": bool(settings_row.notify_friends) if settings_row else True,
            "notify_account": bool(settings_row.notify_account) if settings_row else True,
            "notify_game_news": settings_row.notify_game_news if settings_row else "all",
            # Who sees this person's activity in the app (#157).
            "activity_visible": await repo.activity_visible(person_id),
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
            psn_links,
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
    xbox_link = (
        await repo.get_platform_link(user.id, AccountPlatform.XBOX) if linked and user else None
    )
    return {
        "linked": linked,
        # The owner's switch for this account's posts (#20).
        "publishes": xbox_link.publishes if xbox_link else True,
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
        "publishes": link.publishes,
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
    links: list[PlatformLink],
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
    # Several accounts (#10): the block's counts are the person's sum, the
    # account fields the first one linked; `accounts` lists them all.
    accounts = []
    for item in links:
        accounts.append(
            {
                "account_id": item.external_id,
                "online_id": item.display_name,
                "name": link_nickname(item),
                "publishes": item.publishes,
                "trophy_count": await repo.account_achievement_count(
                    Platform.PSN, item.external_id
                ),
                "platinum_count": await repo.account_platinum_count(item.external_id),
                "trophy_level": item.psn_trophy_level,
                "visibility": visibility_status_text(item, locale),
                "achievements_visible": item.achievements_visible,
                "profile_url": psn_profile_url(item.display_name) if item.display_name else None,
            }
        )
    return {
        "linked": True,
        "publishes": all(item.publishes for item in links),
        "accounts": accounts,
        "max_accounts": MAX_PSN_ACCOUNTS,
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
    titles = await repo.chats_of_user(user.id)
    return {"excluded": False, "chat_titles": titles}
