"""JSON API for the Telegram Mini App.

Mounted on the same aiohttp app as the Microsoft OAuth callback. Every
authenticated route requires ``X-Telegram-Init-Data`` (or ``Authorization:
tma …``).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from aiohttp import web

from bot.config import Settings
from bot.constants import Platform, RarityMode
from bot.db.repo import Repo
from bot.handlers.connect import REVOKE_URL
from bot.i18n import AVAILABLE_LOCALES, normalize_locale
from bot.poller.fetcher import Fetcher
from bot.poller.psn_fetcher import PsnFetcher
from bot.poller.steam_fetcher import SteamFetcher
from bot.services.connect import ConnectService
from bot.services.notify import AdminNotifier
from bot.services.psn.auth import STATUS_NOT_CONFIGURED, PsnAuth, PsnNotConfiguredError
from bot.services.psn.client import (
    PsnApiError,
    PsnTokenDeadError,
    is_trophy_visible,
    resolve_profile,
)
from bot.services.steam.auth import SteamAuth
from bot.services.steam.client import (
    SteamApiError,
    SteamGameDetailsPrivateError,
    get_profile,
    resolve_steam_id,
)
from bot.services.title_catalog import TitleCatalogService
from bot.util import parse_iso
from bot.views.keyboards import DIGEST_CHOICES, next_rarity_mode
from bot.web.mini_admin import setup_admin_routes
from bot.web.mini_auth import InitDataError, MiniAppUser, validate_init_data
from bot.web.mini_avatars import load_avatar_bytes
from bot.web.mini_chat import (
    build_feed_payload,
    build_online_payload,
    build_person_payload,
    build_summary_payload,
    chat_of_user,
)
from bot.web.mini_hltb import setup_hltb_routes
from bot.web.mini_me import build_me_payload

log = logging.getLogger(__name__)

AUTH_HEADER_PREFIX = "tma "
INIT_DATA_HEADER = "X-Telegram-Init-Data"
SYNC_COOLDOWN_SECONDS = 600

_last_sync: dict[int, float] = {}


def setup_mini_api(
    app: web.Application,
    settings: Settings,
    repo: Repo,
    *,
    connect: ConnectService | None = None,
    steam_auth: SteamAuth | None = None,
    steam_fetcher: SteamFetcher | None = None,
    psn_auth: PsnAuth | None = None,
    psn_fetcher: PsnFetcher | None = None,
    xbox_fetcher: Fetcher | None = None,
    notifier: AdminNotifier | None = None,
    anthropic_auth: Any = None,
    bot: Any = None,
    title_catalog: TitleCatalogService | None = None,
) -> None:
    app["mini_settings"] = settings
    app["mini_repo"] = repo
    app["mini_connect"] = connect
    app["mini_steam_auth"] = steam_auth
    app["mini_steam_fetcher"] = steam_fetcher
    app["mini_psn_auth"] = psn_auth
    app["mini_psn_fetcher"] = psn_fetcher
    app["mini_xbox_fetcher"] = xbox_fetcher
    app["mini_notifier"] = notifier
    app["mini_anthropic_auth"] = anthropic_auth
    app["mini_bot"] = bot

    if title_catalog is None:
        title_catalog = TitleCatalogService(
            repo,
            xbox_client=getattr(xbox_fetcher, "_client", None),
            psn_auth=psn_auth,
            steam_auth=steam_auth,
            anthropic_auth=anthropic_auth,
        )
    app["mini_title_catalog"] = title_catalog

    app.router.add_get("/api/mini/health", handle_health)
    app.router.add_get("/api/mini/me", handle_me)
    app.router.add_delete("/api/mini/me", handle_delete_me)
    app.router.add_post("/api/mini/me/delete", handle_delete_me)
    app.router.add_patch("/api/mini/settings", handle_patch_settings)
    app.router.add_post("/api/mini/connect/xbox", handle_connect_xbox)
    app.router.add_post("/api/mini/disconnect/xbox", handle_disconnect_xbox)
    app.router.add_post("/api/mini/connect/steam", handle_connect_steam)
    app.router.add_post("/api/mini/disconnect/steam", handle_disconnect_steam)
    app.router.add_post("/api/mini/connect/psn", handle_connect_psn)
    app.router.add_post("/api/mini/disconnect/psn", handle_disconnect_psn)
    app.router.add_post("/api/mini/sync", handle_sync)
    app.router.add_get("/api/mini/chats", handle_chats)
    app.router.add_patch("/api/mini/chats/{chat_id}", handle_patch_chat)
    app.router.add_get("/api/mini/chats/{chat_id}/feed", handle_chat_feed)
    app.router.add_get("/api/mini/chats/{chat_id}/online", handle_chat_online)
    app.router.add_get("/api/mini/chats/{chat_id}/summary", handle_chat_summary)
    app.router.add_get("/api/mini/chats/{chat_id}/people/{tg_id}", handle_chat_person)
    # Query-string twins: Telegram group ids are negative, and a path
    # segment starting with `-` 404s on some aiohttp/proxy stacks.
    app.router.add_get("/api/mini/club/feed", handle_chat_feed)
    app.router.add_get("/api/mini/club/online", handle_chat_online)
    app.router.add_get("/api/mini/club/summary", handle_chat_summary)
    app.router.add_get("/api/mini/club/people", handle_chat_person)
    app.router.add_patch("/api/mini/club", handle_patch_chat)
    app.router.add_get("/api/mini/avatar/{tg_id}", handle_avatar)
    app.router.add_get("/api/mini/games/{platform}/{title_id}", handle_game_details)
    app.router.add_get("/api/mini/games/{platform}/{title_id}/achievements", handle_game_details)
    setup_admin_routes(app)
    setup_hltb_routes(app)


async def handle_health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def handle_me(request: web.Request) -> web.Response:
    user = await _require_user(request)
    settings: Settings = request.app["mini_settings"]
    repo: Repo = request.app["mini_repo"]
    payload = await build_me_payload(
        repo,
        tg_id=user.tg_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        is_admin=settings.is_admin(user.tg_id),
    )
    return web.json_response(payload)


async def handle_delete_me(request: web.Request) -> web.Response:
    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    await repo.delete_user(user.tg_id)
    return web.json_response({"ok": True})


async def handle_patch_settings(request: web.Request) -> web.Response:
    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    body = await _json_body(request)
    fields: dict[str, Any] = {}

    if "locale" in body:
        locale = normalize_locale(str(body["locale"]))
        if locale not in AVAILABLE_LOCALES:
            raise web.HTTPBadRequest(text="bad locale")
        fields["locale"] = locale
    if "tz_offset_min" in body:
        raw = body["tz_offset_min"]
        if raw is None:
            fields["tz_offset_min"] = None
        else:
            try:
                fields["tz_offset_min"] = int(raw)
            except (TypeError, ValueError) as exc:
                raise web.HTTPBadRequest(text="bad tz_offset_min") from exc
    if "show_profile_links" in body:
        fields["show_profile_links"] = 1 if body["show_profile_links"] else 0
    if "show_secrets" in body:
        fields["show_secrets"] = 1 if body["show_secrets"] else 0

    if not fields:
        raise web.HTTPBadRequest(text="no settings")

    await repo.ensure_user(user.tg_id, user.username)
    await repo.update_user_settings(user.tg_id, **fields)
    return await handle_me(request)


async def handle_connect_xbox(request: web.Request) -> web.Response:
    user = await _require_user(request)
    connect: ConnectService | None = request.app["mini_connect"]
    if connect is None:
        raise web.HTTPServiceUnavailable(text="connect unavailable")
    url = connect.start_login(user.tg_id)
    return web.json_response({"authorize_url": url})


async def handle_disconnect_xbox(request: web.Request) -> web.Response:
    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    notifier: AdminNotifier | None = request.app["mini_notifier"]
    db_user = await repo.get_user(user.tg_id)
    if db_user is None or not db_user.xuid:
        return web.json_response({"ok": True, "already": True, "revoke_url": REVOKE_URL})
    gamertag = db_user.gamertag or f"id{user.tg_id}"
    await repo.delete_presence_state(db_user.xuid)
    await repo.delete_token(user.tg_id)
    await repo.delete_subscriptions_of_user(user.tg_id)
    await repo.unlink_xbox_account(user.tg_id)
    if notifier is not None:
        await notifier.user_disconnected(user.tg_id, gamertag, "mini-app")
    return web.json_response({"ok": True, "revoke_url": REVOKE_URL})


async def handle_connect_steam(request: web.Request) -> web.Response:
    user = await _require_user(request)
    steam_auth: SteamAuth | None = request.app["mini_steam_auth"]
    steam_fetcher: SteamFetcher | None = request.app["mini_steam_fetcher"]
    repo: Repo = request.app["mini_repo"]
    if steam_auth is None or steam_fetcher is None:
        raise web.HTTPServiceUnavailable(text="steam unavailable")
    if await steam_auth.get_key() is None:
        return web.json_response({"ok": False, "error": "not_configured"}, status=400)

    body = await _json_body(request)
    raw = str(body.get("identity") or "").strip()
    if not raw:
        return web.json_response({"ok": False, "error": "missing_identity"}, status=400)

    existing = await repo.get_platform_link(user.tg_id, Platform.STEAM)
    if existing is not None:
        return web.json_response(
            {"ok": False, "error": "already_linked", "display_name": existing.display_name},
            status=409,
        )

    api_key = await steam_auth.require_key()
    try:
        steam_id = await resolve_steam_id(api_key, raw)
        profile = await get_profile(api_key, steam_id)
    except SteamApiError as exc:
        log.info("mini connect_steam: resolve failed tg_id=%s raw=%r: %s", user.tg_id, raw, exc)
        return web.json_response({"ok": False, "error": "not_found"}, status=404)

    if not profile.is_public:
        return web.json_response({"ok": False, "error": "private"}, status=400)

    await repo.ensure_user(user.tg_id, user.username)
    await repo.link_platform_account(
        user.tg_id, Platform.STEAM, profile.steam_id, profile.persona_name
    )
    log.info("mini connect_steam: tg_id=%s steam_id=%s", user.tg_id, profile.steam_id)
    asyncio.create_task(  # noqa: RUF006
        _steam_backfill(steam_fetcher, user.tg_id, profile.steam_id)
    )
    return web.json_response(
        {
            "ok": True,
            "steam_id": profile.steam_id,
            "display_name": profile.persona_name,
            "backfill": "started",
        }
    )


async def handle_disconnect_steam(request: web.Request) -> web.Response:
    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    link = await repo.get_platform_link(user.tg_id, Platform.STEAM)
    await repo.unlink_platform_account(user.tg_id, Platform.STEAM)
    if link is not None:
        await repo.delete_steam_presence_state(link.external_id)
    return web.json_response({"ok": True, "already": link is None})


async def handle_connect_psn(request: web.Request) -> web.Response:
    user = await _require_user(request)
    psn_auth: PsnAuth | None = request.app["mini_psn_auth"]
    psn_fetcher: PsnFetcher | None = request.app["mini_psn_fetcher"]
    repo: Repo = request.app["mini_repo"]
    if psn_auth is None or psn_fetcher is None:
        raise web.HTTPServiceUnavailable(text="psn unavailable")
    if await psn_auth.status() == STATUS_NOT_CONFIGURED:
        return web.json_response({"ok": False, "error": "not_configured"}, status=400)

    body = await _json_body(request)
    raw = str(body.get("online_id") or body.get("identity") or "").strip()
    if not raw:
        return web.json_response({"ok": False, "error": "missing_identity"}, status=400)

    existing = await repo.get_platform_link(user.tg_id, Platform.PSN)
    if existing is not None:
        return web.json_response(
            {"ok": False, "error": "already_linked", "display_name": existing.display_name},
            status=409,
        )

    try:
        client = await psn_auth.get_client()
        profile = await resolve_profile(client, raw)
    except PsnNotConfiguredError:
        return web.json_response({"ok": False, "error": "not_configured"}, status=400)
    except PsnTokenDeadError:
        return web.json_response({"ok": False, "error": "service_dead"}, status=503)
    except PsnApiError as exc:
        log.info("mini connect_psn: resolve failed tg_id=%s raw=%r: %s", user.tg_id, raw, exc)
        return web.json_response({"ok": False, "error": "not_found"}, status=404)

    if not await is_trophy_visible(client, profile.account_id):
        return web.json_response({"ok": False, "error": "private"}, status=400)

    await repo.ensure_user(user.tg_id, user.username)
    await repo.link_platform_account(
        user.tg_id, Platform.PSN, profile.account_id, profile.online_id
    )
    await repo.set_achievements_visible(user.tg_id, Platform.PSN, True)
    log.info("mini connect_psn: tg_id=%s account_id=%s", user.tg_id, profile.account_id)
    asyncio.create_task(  # noqa: RUF006
        _psn_backfill(psn_fetcher, user.tg_id, profile.account_id)
    )
    return web.json_response(
        {
            "ok": True,
            "account_id": profile.account_id,
            "online_id": profile.online_id,
            "backfill": "started",
        }
    )


async def handle_disconnect_psn(request: web.Request) -> web.Response:
    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    link = await repo.get_platform_link(user.tg_id, Platform.PSN)
    await repo.unlink_platform_account(user.tg_id, Platform.PSN)
    if link is not None:
        await repo.delete_psn_poll_state(link.external_id)
    return web.json_response({"ok": True, "already": link is None})


async def handle_sync(request: web.Request) -> web.Response:
    user = await _require_user(request)
    settings: Settings = request.app["mini_settings"]
    repo: Repo = request.app["mini_repo"]
    fetcher: Fetcher | None = request.app["mini_xbox_fetcher"]
    if fetcher is None:
        raise web.HTTPServiceUnavailable(text="sync unavailable")

    db_user = await repo.get_user(user.tg_id)
    if db_user is None or not db_user.xuid:
        return web.json_response({"ok": False, "error": "xbox_not_linked"}, status=400)

    now = time.monotonic()
    last = _last_sync.get(user.tg_id)
    if last is not None:
        left = SYNC_COOLDOWN_SECONDS - (now - last)
        if left > 0:
            return web.json_response(
                {"ok": False, "error": "cooldown", "minutes_left": max(1, int(left // 60) or 1)},
                status=429,
            )

    _last_sync[user.tg_id] = now
    target = next((t for t in await repo.pollable_users() if t.tg_id == user.tg_id), None)
    try:
        titles, published = await fetcher.catch_up(
            user.tg_id,
            db_user.xuid,
            db_user.gamertag or f"id{user.tg_id}",
            parse_iso(target.updated_at) if target and target.updated_at else None,
            settings.catchup_publish_window_hours,
            settings.catchup_max_titles,
        )
    except Exception:
        log.exception("mini sync failed tg_id=%s", user.tg_id)
        return web.json_response({"ok": False, "error": "sync_failed"}, status=502)

    return web.json_response({"ok": True, "titles": titles, "published": published})


async def handle_chats(request: web.Request) -> web.Response:
    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    chats = await repo.user_chats(user.tg_id)
    return web.json_response(
        {
            "chats": [
                {
                    "chat_id": c.chat_id,
                    "title": c.title,
                    "is_subscribed": c.is_subscribed,
                    "rarity_mode": c.rarity_mode,
                    "digest_threshold": c.digest_threshold,
                }
                for c in chats
            ]
        }
    )


async def handle_patch_chat(request: web.Request) -> web.Response:
    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    try:
        chat_id = int(request.match_info.get("chat_id") or request.query.get("chat_id") or "")
    except ValueError as exc:
        raise web.HTTPBadRequest(text="bad chat_id") from exc

    chats = await repo.user_chats(user.tg_id)
    chat = next((c for c in chats if c.chat_id == chat_id), None)
    if chat is None:
        raise web.HTTPNotFound(text="chat not found")

    body = await _json_body(request)
    action = str(body.get("action") or "").strip()

    if action == "cycle_rarity":
        if not chat.is_subscribed:
            return web.json_response({"ok": False, "error": "not_subscribed"}, status=400)
        mode = next_rarity_mode(chat.rarity_mode or RarityMode.ALL)
        await repo.update_subscription_rarity_mode(chat_id, user.tg_id, mode)
    elif action == "set_rarity":
        if not chat.is_subscribed:
            return web.json_response({"ok": False, "error": "not_subscribed"}, status=400)
        mode = str(body.get("rarity_mode") or "").strip()
        if mode not in {RarityMode.ALL, RarityMode.RARE, RarityMode.HIDDEN}:
            raise web.HTTPBadRequest(text="bad rarity_mode")
        await repo.update_subscription_rarity_mode(chat_id, user.tg_id, mode)
    elif action == "set_digest":
        if not chat.is_subscribed:
            return web.json_response({"ok": False, "error": "not_subscribed"}, status=400)
        try:
            value = int(body["digest_threshold"])
        except (KeyError, TypeError, ValueError) as exc:
            raise web.HTTPBadRequest(text="bad digest_threshold") from exc
        if value not in DIGEST_CHOICES:
            raise web.HTTPBadRequest(text="bad digest_threshold")
        await repo.update_subscription_digest_threshold(chat_id, user.tg_id, value)
    elif action == "subscribe":
        # Needs at least one linked platform — same rule as /subscribe.
        db_user = await repo.get_user(user.tg_id)
        steam = await repo.get_platform_link(user.tg_id, Platform.STEAM)
        psn = await repo.get_platform_link(user.tg_id, Platform.PSN)
        has_platform = bool((db_user and db_user.xuid) or steam or psn)
        if not has_platform:
            return web.json_response({"ok": False, "error": "no_platform"}, status=400)
        await repo.subscribe(chat_id, user.tg_id)
    elif action == "unsubscribe":
        await repo.unsubscribe(chat_id, user.tg_id)
    elif action == "forget":
        await repo.forget_chat_membership(chat_id, user.tg_id)
        return web.json_response({"ok": True, "forgotten": True})
    else:
        raise web.HTTPBadRequest(text="bad action")

    refreshed = next((c for c in await repo.user_chats(user.tg_id) if c.chat_id == chat_id), None)
    return web.json_response(
        {
            "ok": True,
            "chat": None
            if refreshed is None
            else {
                "chat_id": refreshed.chat_id,
                "title": refreshed.title,
                "is_subscribed": refreshed.is_subscribed,
                "rarity_mode": refreshed.rarity_mode,
                "digest_threshold": refreshed.digest_threshold,
            },
        }
    )


async def handle_chat_feed(request: web.Request) -> web.Response:
    user, chat_id, repo = await _require_chat_member(request)
    locale = await _user_locale(repo, user.tg_id)
    try:
        limit = int(request.query.get("limit") or 500)
    except ValueError as exc:
        raise web.HTTPBadRequest(text="bad limit") from exc
    month = request.query.get("month") or None
    try:
        payload = await build_feed_payload(repo, chat_id, locale=locale, limit=limit, month=month)
    except ValueError as exc:
        raise web.HTTPBadRequest(text="bad month") from exc
    return web.json_response(payload)


async def handle_chat_online(request: web.Request) -> web.Response:
    user, chat_id, repo = await _require_chat_member(request)
    locale = await _user_locale(repo, user.tg_id)
    payload = await build_online_payload(repo, chat_id, locale=locale)
    return web.json_response(payload)


async def handle_chat_summary(request: web.Request) -> web.Response:
    user, chat_id, repo = await _require_chat_member(request)
    locale = await _user_locale(repo, user.tg_id)
    month = request.query.get("month") or None
    try:
        payload = await build_summary_payload(repo, chat_id, locale=locale, month=month)
    except ValueError as exc:
        raise web.HTTPBadRequest(text="bad month") from exc
    return web.json_response(payload)


async def handle_avatar(request: web.Request) -> web.Response:
    # Other people's photos are not in initData — only Bot API can fetch
    # them. Bytes go through here so the SPA never sees the bot token.
    user = await _require_user(request)
    try:
        tg_id = int(request.match_info["tg_id"])
    except ValueError as exc:
        raise web.HTTPBadRequest(text="bad tg_id") from exc
    repo: Repo = request.app["mini_repo"]
    target = await repo.get_user(tg_id)
    if tg_id != user.tg_id and target is None:
        raise web.HTTPNotFound(text="no photo")
    bot = request.app.get("mini_bot")
    if bot is None:
        raise web.HTTPNotFound(text="no photo")
    result = await load_avatar_bytes(bot, tg_id, file_id=target.photo_file_id if target else None)
    if result is None:
        raise web.HTTPNotFound(text="no photo")
    body, mime = result
    return web.Response(
        body=body,
        content_type=mime,
        headers={"Cache-Control": "private, max-age=3600"},
    )


async def handle_chat_person(request: web.Request) -> web.Response:
    user, chat_id, repo = await _require_chat_member(request)
    raw_target = request.match_info.get("tg_id") or request.query.get("tg_id") or ""
    try:
        target_id = int(raw_target)
    except ValueError as exc:
        raise web.HTTPBadRequest(text="bad tg_id") from exc
    target = await repo.get_user(target_id)
    if target is None:
        raise web.HTTPNotFound(text="person not found")
    locale = await _user_locale(repo, user.tg_id)
    month = request.query.get("month") or None
    try:
        payload = await build_person_payload(
            repo, target, locale=locale, chat_id=chat_id, month=month
        )
    except ValueError as exc:
        raise web.HTTPBadRequest(text="bad month") from exc
    return web.json_response(payload)


async def _require_chat_member(request: web.Request) -> tuple[MiniAppUser, int, Repo]:
    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    raw = request.match_info.get("chat_id") or request.query.get("chat_id") or ""
    try:
        chat_id = int(raw)
    except ValueError as exc:
        raise web.HTTPBadRequest(text="bad chat_id") from exc
    if await chat_of_user(repo, user.tg_id, chat_id) is None:
        raise web.HTTPForbidden(text="not a member")
    return user, chat_id, repo


async def _user_locale(repo: Repo, tg_id: int) -> str:
    settings_row = await repo.get_user_settings(tg_id)
    return (settings_row.locale if settings_row else None) or "ru"


async def _steam_backfill(fetcher: SteamFetcher, tg_id: int, steam_id: str) -> None:
    try:
        await fetcher.backfill(tg_id, steam_id)
    except SteamGameDetailsPrivateError:
        log.info("mini steam backfill: game details private tg_id=%s", tg_id)
    except Exception:
        log.exception("mini steam backfill failed tg_id=%s", tg_id)


async def _psn_backfill(fetcher: PsnFetcher, tg_id: int, account_id: str) -> None:
    try:
        await fetcher.backfill(tg_id, account_id)
    except Exception:
        log.exception("mini psn backfill failed tg_id=%s", tg_id)


async def handle_game_details(request: web.Request) -> web.Response:
    user = await _require_user(request)
    platform = request.match_info.get("platform", "").lower()
    title_id = request.match_info.get("title_id", "")
    force = request.query.get("force", "").lower() in ("1", "true", "yes")

    repo: Repo = request.app["mini_repo"]
    catalog_service: TitleCatalogService = request.app["mini_title_catalog"]

    checklist = await catalog_service.get_title_checklist_for_user(
        platform, title_id, tg_id=user.tg_id, force=force
    )
    title_info = await repo.title_record(title_id) or {}

    total = len(checklist)
    unlocked = sum(1 for item in checklist if item.is_unlocked)
    percent = round((unlocked / total) * 100, 1) if total > 0 else 0.0

    groups = await repo.get_title_groups(title_id) if platform == Platform.PSN else []

    return web.json_response(
        {
            "ok": True,
            "platform": platform,
            "title_id": title_id,
            "name": title_info.get("name"),
            "name_ru": title_info.get("name_ru"),
            "name_en": title_info.get("name_en"),
            "icon_url": title_info.get("icon_url"),
            "cover_path": title_info.get("cover_path"),
            "achievements_total": total or title_info.get("achievements_total") or 0,
            "achievements_unlocked": unlocked,
            "completion_percent": percent,
            "achievements_checked_at": title_info.get("achievements_checked_at"),
            "groups": groups,
            "achievements": [
                {
                    "achievement_id": item.achievement.achievement_id,
                    "name_ru": item.achievement.name_ru,
                    "name_en": item.achievement.name_en,
                    "description_ru": item.achievement.description_ru,
                    "description_en": item.achievement.description_en,
                    "icon_url": item.achievement.icon_url,
                    "is_secret": item.achievement.is_secret,
                    "gamerscore": item.achievement.gamerscore,
                    "trophy_type": item.achievement.trophy_type,
                    "trophy_group_id": item.achievement.trophy_group_id,
                    "rarity_percent": item.achievement.rarity_percent,
                    "is_unlocked": item.is_unlocked,
                    "unlocked_at": item.unlocked_at,
                }
                for item in checklist
            ],
        }
    )


def _extract_init_data(request: web.Request) -> str:
    dedicated = request.headers.get(INIT_DATA_HEADER, "").strip()
    if dedicated:
        return dedicated
    header = request.headers.get("Authorization", "")
    if header.startswith(AUTH_HEADER_PREFIX):
        return header[len(AUTH_HEADER_PREFIX) :].strip()
    raise web.HTTPUnauthorized(text="missing initData")


async def _require_user(request: web.Request) -> MiniAppUser:
    init_data = _extract_init_data(request)
    settings: Settings = request.app["mini_settings"]
    try:
        return validate_init_data(init_data, settings.bot_token.get_secret_value())
    except InitDataError as exc:
        log.info("mini initData rejected: %s (len=%s)", exc, len(init_data))
        raise web.HTTPUnauthorized(text="invalid initData") from exc


async def _json_body(request: web.Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception as exc:
        raise web.HTTPBadRequest(text="invalid json") from exc
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text="json object required")
    return data


def cors_middleware() -> Any:
    @web.middleware
    async def middleware(request: web.Request, handler):  # type: ignore[no-untyped-def]
        if request.method == "OPTIONS":
            response = web.Response(status=204)
        else:
            response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin", "*")
        response.headers["Access-Control-Allow-Headers"] = (
            "Authorization, Content-Type, X-Telegram-Init-Data"
        )
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, PUT, DELETE, OPTIONS"
        return response

    return middleware
