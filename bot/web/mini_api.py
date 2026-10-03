"""JSON API for the Telegram Mini App.

Mounted on the same aiohttp app as the Microsoft OAuth callback. Every
authenticated route requires ``X-Telegram-Init-Data`` (or ``Authorization:
tma …``).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

from aiohttp import web

from bot.config import Settings
from bot.constants import MAX_PSN_ACCOUNTS, AccountPlatform, Platform, RarityMode
from bot.db.repo import HandleInvalid, HandleTooSoon, Repo, User
from bot.db.repo._sql import MEMBERS_CHAT
from bot.handlers.connect import REVOKE_URL
from bot.i18n import AVAILABLE_LOCALES, normalize_locale
from bot.poller.fetcher import Fetcher
from bot.poller.psn_fetcher import PsnFetcher
from bot.poller.steam_fetcher import SteamFetcher
from bot.services import achievement_icons, avatars
from bot.services.connect import ConnectService
from bot.services.hltb import HltbError, ensure_title_match
from bot.services.hltb import resolve as hltb_resolve
from bot.services.naming import person_name_of
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
from bot.services.steam_extras import SteamExtras
from bot.services.steam_guides import has_prose
from bot.services.title_catalog import TitleCatalogService
from bot.util import parse_iso
from bot.web import mini_people, mini_session
from bot.web.mini_admin import setup_admin_routes
from bot.web.mini_auth import InitDataError, MiniAppUser, validate_init_data
from bot.web.mini_avatars import _mime, forget_avatar, load_avatar_bytes
from bot.web.mini_chat import (
    _https_url,
    build_feed_payload,
    build_online_payload,
    build_person_payload,
    build_summary_payload,
    chat_of_user,
)
from bot.web.mini_hltb import hltb_payload, setup_hltb_routes
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
    steam_extras: SteamExtras | None = None,
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
    app["mini_steam_extras"] = steam_extras or SteamExtras(repo, steam_auth, anthropic_auth)

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
    mini_people.register(app, _require_user)
    mini_session.register(app)
    app.router.add_get("/api/mini/me", handle_me)
    app.router.add_delete("/api/mini/me", handle_delete_me)
    app.router.add_post("/api/mini/me/delete", handle_delete_me)
    app.router.add_patch("/api/mini/settings", handle_patch_settings)
    app.router.add_put("/api/mini/me/handle", handle_put_handle)
    app.router.add_post("/api/mini/me/handle/confirm", handle_confirm_handle)
    app.router.add_put("/api/mini/me/avatar", handle_put_avatar)
    app.router.add_delete("/api/mini/me/avatar", handle_delete_avatar)
    app.router.add_post("/api/mini/connect/xbox", handle_connect_xbox)
    app.router.add_post("/api/mini/disconnect/xbox", handle_disconnect_xbox)
    app.router.add_post("/api/mini/connect/steam", handle_connect_steam)
    app.router.add_post("/api/mini/disconnect/steam", handle_disconnect_steam)
    app.router.add_post("/api/mini/connect/psn", handle_connect_psn)
    app.router.add_post("/api/mini/disconnect/psn", handle_disconnect_psn)
    app.router.add_post("/api/mini/sync", handle_sync)
    app.router.add_patch("/api/mini/accounts/{platform}", handle_patch_account)
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
    app.router.add_get("/api/mini/x360-icon/{title_hex}/{image_hex}", handle_x360_icon)
    app.router.add_get(
        "/api/mini/ach-icon/{platform}/{title_id}/{achievement_id:.+}",
        handle_achievement_icon,
    )
    app.router.add_get("/api/mini/games/{platform}/{title_id}", handle_game_details)
    app.router.add_get("/api/mini/games/{platform}/{title_id}/achievements", handle_game_details)
    app.router.add_get("/api/mini/games/{platform}/{title_id}/hltb", handle_game_hltb)
    app.router.add_get("/api/mini/games/{platform}/{title_id}/patches", handle_game_patches)
    app.router.add_get("/api/mini/games/{platform}/{title_id}/guides", handle_game_guides)
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


async def handle_put_handle(request: web.Request) -> web.Response:
    """Choose or change the nickname (#157). A refusal is a JSON `error` the
    Mini App words itself: `invalid`, or `too_soon` with `available_at`."""
    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    body = await _json_body(request)
    await repo.ensure_user(user.tg_id, user.username)
    try:
        await repo.change_handle(user.tg_id, str(body.get("handle", "")))
    except HandleInvalid:
        return web.json_response({"error": "invalid"}, status=400)
    except HandleTooSoon as exc:
        return web.json_response(
            {"error": "too_soon", "available_at": exc.available_at}, status=409
        )
    return await handle_me(request)


async def handle_confirm_handle(request: web.Request) -> web.Response:
    """ "Keep it" on the first-visit nickname screen."""
    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    await repo.ensure_user(user.tg_id, user.username)
    await repo.confirm_handle(user.tg_id)
    return await handle_me(request)


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
    if "show_secrets" in body:
        fields["show_secrets"] = 1 if body["show_secrets"] else 0
    if "notify_followers" in body:
        fields["notify_followers"] = 1 if body["notify_followers"] else 0
    if "rarity_mode" in body:
        mode = str(body["rarity_mode"])
        if mode not in {RarityMode.ALL, RarityMode.RARE, RarityMode.HIDDEN}:
            raise web.HTTPBadRequest(text="bad rarity_mode")
        fields["rarity_mode"] = mode

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
    cooldown = await repo.check_platform_cooldown(user.tg_id, Platform.STEAM, profile.steam_id)
    if cooldown.is_blocked:
        return web.json_response(
            {
                "ok": False,
                "error": "cooldown",
                "cooldown_seconds": cooldown.remaining_seconds,
            },
            status=400,
        )

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

    # Up to MAX_PSN_ACCOUNTS accounts (#10); the limit is checked again
    # below once the Online ID is resolved, since relinking one already held
    # is not an addition.
    held = await repo.platform_links_for(user.tg_id, Platform.PSN)

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
    if (
        all(link.external_id != profile.account_id for link in held)
        and len(held) >= MAX_PSN_ACCOUNTS
    ):
        return web.json_response(
            {"ok": False, "error": "limit", "max": MAX_PSN_ACCOUNTS}, status=409
        )

    await repo.ensure_user(user.tg_id, user.username)
    cooldown = await repo.check_platform_cooldown(user.tg_id, Platform.PSN, profile.account_id)
    if cooldown.is_blocked:
        return web.json_response(
            {
                "ok": False,
                "error": "cooldown",
                "cooldown_seconds": cooldown.remaining_seconds,
            },
            status=400,
        )

    await repo.link_platform_account(
        user.tg_id, Platform.PSN, profile.account_id, profile.online_id
    )
    await repo.set_achievements_visible(
        user.tg_id, Platform.PSN, True, external_id=profile.account_id
    )
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
    """Every PSN account, or the one `account_id` names (#10)."""
    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    body = await _json_body(request) if request.can_read_body else {}
    account_id = str(body.get("account_id") or "").strip() or None
    links = await repo.platform_links_for(user.tg_id, Platform.PSN)
    if account_id is not None:
        links = [link for link in links if link.external_id == account_id]
    for link in links:
        # `psn_poll_state` stays: it is #21's gate, and a relink through the
        # bot skips backfill (see handlers/psn.py::disconnect_psn_confirm).
        await repo.unlink_account(user.tg_id, Platform.PSN, link.external_id)
    return web.json_response({"ok": True, "already": not links})


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


async def handle_patch_account(request: web.Request) -> web.Response:
    """The owner's switch for one linked account's posts (#20)."""
    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    platform = request.match_info.get("platform", "")
    if platform not in (AccountPlatform.XBOX, AccountPlatform.PSN, AccountPlatform.STEAM):
        raise web.HTTPBadRequest(text="bad platform")
    body = await _json_body(request)
    if "publishes" not in body:
        raise web.HTTPBadRequest(text="no publishes")
    publishes = bool(body["publishes"])
    account_id = str(body.get("account_id") or "").strip() or None
    if account_id is None:
        # The whole platform — every PSN account at once (#10).
        if await repo.get_platform_link(user.tg_id, platform) is None:
            raise web.HTTPNotFound(text="not linked")
        await repo.set_platform_publishes(user.tg_id, platform, publishes)
        return await handle_me(request)
    links = await repo.platform_links_for(user.tg_id, platform)
    if all(link.external_id != account_id for link in links):
        raise web.HTTPNotFound(text="not linked")
    await repo.set_account_publishes(user.tg_id, platform, account_id, publishes)
    return await handle_me(request)


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

    # The rarity mode is the person's and the digest size the chat's since
    # #126 — settings (`PATCH /settings`) and the admin's chat card own them.
    if action == "subscribe":
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
            },
        }
    )


async def _following_scope(request: web.Request) -> tuple[Any, Repo, list[int], int | None] | None:
    """`?scope=following` (#157): the feed and ranking of the people the viewer
    follows (and themself), instead of one chat. Returns the viewer, the repo, the
    Telegram ids to read and the viewer's timezone; None for an ordinary chat."""
    if request.query.get("scope") != "following":
        return None
    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    await repo.ensure_user(user.tg_id, user.username)
    person = await repo.person_id(user.tg_id)
    if person is None:
        raise web.HTTPNotFound(text="no person")
    settings_row = await repo.get_user_settings(user.tg_id)
    tz = settings_row.tz_offset_min if settings_row else None
    return user, repo, await repo.following_members(person), tz


async def handle_chat_feed(request: web.Request) -> web.Response:
    scoped = await _following_scope(request)
    if scoped is not None:
        user, repo, members, tz = scoped
        month = request.query.get("month") or None
        try:
            payload = await build_feed_payload(
                repo,
                MEMBERS_CHAT,
                locale=await _user_locale(repo, user.tg_id),
                limit=int(request.query.get("limit") or 500),
                month=month,
                members=members,
                tz_of=tz,
            )
        except ValueError as exc:
            raise web.HTTPBadRequest(text="bad month or limit") from exc
        return web.json_response(payload)
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
    scoped = await _following_scope(request)
    if scoped is not None:
        user, repo, members, _tz = scoped
        locale = await _user_locale(repo, user.tg_id)
        payload = await build_online_payload(repo, MEMBERS_CHAT, locale=locale, members=members)
        return web.json_response(payload)
    user, chat_id, repo = await _require_chat_member(request)
    locale = await _user_locale(repo, user.tg_id)
    payload = await build_online_payload(repo, chat_id, locale=locale)
    return web.json_response(payload)


async def handle_chat_summary(request: web.Request) -> web.Response:
    scoped = await _following_scope(request)
    if scoped is not None:
        user, repo, members, tz = scoped
        try:
            payload = await build_summary_payload(
                repo,
                MEMBERS_CHAT,
                locale=await _user_locale(repo, user.tg_id),
                month=request.query.get("month") or None,
                members=members,
                tz_of=tz,
            )
        except ValueError as exc:
            raise web.HTTPBadRequest(text="bad month") from exc
        return web.json_response(payload)
    user, chat_id, repo = await _require_chat_member(request)
    locale = await _user_locale(repo, user.tg_id)
    month = request.query.get("month") or None
    try:
        payload = await build_summary_payload(repo, chat_id, locale=locale, month=month)
    except ValueError as exc:
        raise web.HTTPBadRequest(text="bad month") from exc
    return web.json_response(payload)


# A chosen picture: the Mini App sends it already cropped and shrunk; the server
# only checks that it is one of three image formats and not oversized.
AVATAR_MAX_BYTES = 2 * 1024 * 1024
_IMAGE_KINDS = (("jpg", b"\xff\xd8\xff"), ("png", b"\x89PNG"), ("webp", b"RIFF"))


def _image_kind(body: bytes) -> str | None:
    for ext, magic in _IMAGE_KINDS:
        if body.startswith(magic) and (ext != "webp" or b"WEBP" in body[:16]):
            return ext
    return None


async def handle_put_avatar(request: web.Request) -> web.Response:
    """Set the person's own picture (#157). The body is the image bytes."""
    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    body = await request.read()
    kind = _image_kind(body)
    if not body or len(body) > AVATAR_MAX_BYTES or kind is None:
        return web.json_response({"error": "invalid"}, status=400)
    await repo.ensure_user(user.tg_id, user.username)
    # A new name every time, so no cache anywhere keeps the old face.
    name = f"custom-{user.tg_id}-{hashlib.sha256(body).hexdigest()[:12]}.{kind}"
    path, _digest = avatars.write(body, name)
    previous = await repo.custom_avatar_path(user.tg_id)
    await repo.set_custom_avatar_path(user.tg_id, path)
    if previous and previous != path:
        (avatars.avatar_dir() / previous).unlink(missing_ok=True)
    forget_avatar(user.tg_id)
    return await handle_me(request)


async def handle_delete_avatar(request: web.Request) -> web.Response:
    """Back to the Telegram photo."""
    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    previous = await repo.custom_avatar_path(user.tg_id)
    if previous:
        await repo.set_custom_avatar_path(user.tg_id, None)
        (avatars.avatar_dir() / previous).unlink(missing_ok=True)
    forget_avatar(user.tg_id)
    return await handle_me(request)


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
    custom = await repo.custom_avatar_path(tg_id)
    if custom:
        file = avatars.avatar_dir() / custom
        if file.is_file():
            body = file.read_bytes()
            return _picture(request, body, _mime(body))
    bot = request.app.get("mini_bot")
    if bot is None:
        raise web.HTTPNotFound(text="no photo")
    result = await load_avatar_bytes(bot, tg_id, file_id=target.photo_file_id if target else None)
    if result is None:
        raise web.HTTPNotFound(text="no photo")
    body, mime = result
    return _picture(request, body, mime)


def _picture(request: web.Request, body: bytes, mime: str) -> web.Response:
    """A face, revalidated on every show: a person can change theirs at any
    moment, and an hour of a browser's cache kept showing the old one. An
    unchanged picture costs a 304 and no bytes."""
    etag = '"' + hashlib.sha256(body).hexdigest()[:20] + '"'
    headers = {"Cache-Control": "private, no-cache", "ETag": etag}
    if request.headers.get("If-None-Match") == etag:
        return web.Response(status=304, headers=headers)
    return web.Response(body=body, content_type=mime, headers=headers)


_X360_ICON_CACHE: dict[str, bytes] = {}
_HEX_CHARS = set("0123456789abcdefABCDEF")


async def handle_x360_icon(request: web.Request) -> web.Response:
    title_hex = request.match_info.get("title_hex", "").lower()
    image_hex = request.match_info.get("image_hex", "").lower()
    if not (title_hex and image_hex):
        raise web.HTTPBadRequest(text="missing parameters")
    if not (set(title_hex).issubset(_HEX_CHARS) and set(image_hex).issubset(_HEX_CHARS)):
        raise web.HTTPBadRequest(text="invalid hex")

    cache_key = f"{title_hex}/{image_hex}"
    if cache_key in _X360_ICON_CACHE:
        return web.Response(
            body=_X360_ICON_CACHE[cache_key],
            content_type="image/png",
            headers={"Cache-Control": "public, max-age=604800, immutable"},
        )

    result = await achievement_icons.get_or_download_x360_icon(title_hex, image_hex)
    if result is None:
        raise web.HTTPNotFound(text="icon not found")
    data, mime = result
    if len(_X360_ICON_CACHE) < 5000:
        _X360_ICON_CACHE[cache_key] = data
    return web.Response(
        body=data,
        content_type=mime,
        headers={"Cache-Control": "public, max-age=604800, immutable"},
    )


async def handle_achievement_icon(request: web.Request) -> web.Response:
    platform = request.match_info.get("platform", "").lower()
    title_id = request.match_info.get("title_id", "")
    achievement_id = request.match_info.get("achievement_id", "")
    if not (platform and title_id and achievement_id):
        raise web.HTTPBadRequest(text="missing parameters")

    repo: Repo = request.app["mini_repo"]
    result = await achievement_icons.get_or_download_achievement_icon(
        repo, platform, title_id, achievement_id
    )
    if result is None:
        raise web.HTTPNotFound(text="icon not found")
    body, mime = result
    return web.Response(
        body=body,
        content_type=mime,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
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
    if not await _may_see_activity(repo, user.tg_id, target_id):
        # The nickname and avatar are public; what they did is not (#157).
        return web.json_response(
            {
                "tg_id": target.tg_id,
                "name": await _public_name(repo, target),
                "hidden": True,
                "platforms": [],
                "today": {"count": 0, "score": 0, "xbox": 0, "steam": 0, "psn": 0},
                "week": {"count": 0, "xbox": 0, "steam": 0, "psn": 0},
                "month": {"count": 0, "score": 0, "xbox": 0, "steam": 0, "psn": 0},
                "games": [],
                "feed": [],
            }
        )
    month = request.query.get("month") or None
    try:
        payload = await build_person_payload(
            repo, target, locale=locale, chat_id=chat_id, month=month
        )
    except ValueError as exc:
        raise web.HTTPBadRequest(text="bad month") from exc
    return web.json_response(payload)


async def _may_see_activity(repo: Repo, viewer_tg: int, target_tg: int) -> bool:
    """The one privacy check for a person's page (#157), by Telegram id."""
    viewer = await repo.person_id(viewer_tg)
    target = await repo.person_id(target_tg)
    if viewer is None or target is None:
        return True
    return await repo.can_view_activity(viewer, target)


async def _public_name(repo: Repo, target: User) -> str:
    return person_name_of(target, await repo.platform_links_of(target.tg_id))


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

    # Whose progress: the caller's own unless somebody else is named — anybody
    # whose privacy setting lets the caller see their activity (#157), not only
    # people from a shared chat.
    viewed_id = user.tg_id
    raw_viewed = request.query.get("tg_id")
    if raw_viewed:
        try:
            viewed_id = int(raw_viewed)
        except ValueError as exc:
            raise web.HTTPBadRequest(text="bad tg_id") from exc
    if viewed_id != user.tg_id:
        if await repo.get_user(viewed_id) is None:
            raise web.HTTPNotFound(text="person not found")
        if not await _may_see_activity(repo, user.tg_id, viewed_id):
            raise web.HTTPForbidden(text="activity hidden")

    checklist = await catalog_service.get_title_checklist_for_user(
        platform, title_id, tg_id=viewed_id, force=force
    )
    title_info = await repo.title_record(title_id) or {}

    listed = len(checklist)
    unlocked = sum(1 for item in checklist if item.is_unlocked)
    # The platform's own count (from the title list) can be larger than what the
    # catalog holds: a game nobody's account could refresh yet has only the
    # achievements somebody unlocked, and "9 of 9" would be a lie about it.
    known_total = int(title_info.get("achievements_total") or 0)
    total = max(listed, known_total)
    partial = listed < total
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
            # Same https rewrite the feed applies: a plain-http cover is mixed
            # content, and the page used to swap its good picture for it.
            "icon_url": _https_url(title_info.get("icon_url")),
            "cover_path": title_info.get("cover_path"),
            "achievements_total": total,
            "catalog_partial": partial,
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
                    "icon_url": achievement_icons.format_achievement_icon_url(
                        platform,
                        title_id,
                        item.achievement.achievement_id,
                        item.achievement.icon_url,
                    ),
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


async def handle_game_hltb(request: web.Request) -> web.Response:
    """A game's HLTB hours/description, split off from `handle_game_details`
    (#131) so the achievements a person actually opened the page for are
    never held up behind it — an unmatched game's first visit costs a few
    HLTB requests (`ensure_title_match`), which used to delay the whole
    page. The Mini App calls this once the page itself has already
    rendered, and fills the "Об игре" tab in when it answers."""
    user = await _require_user(request)
    title_id = request.match_info.get("title_id", "")
    repo: Repo = request.app["mini_repo"]

    hltb_block: dict[str, Any] | None = None
    try:
        await ensure_title_match(repo, title_id)
        match = await repo.title_hltb_match(title_id)
        if match:
            hltb_id, _score = match
            anthropic = request.app.get("mini_anthropic_auth")
            result = await hltb_resolve(repo, hltb_id, anthropic_auth=anthropic)
            hltb_block = hltb_payload(result, locale=await _user_locale(repo, user.tg_id))
    except HltbError as exc:
        log.info("could not resolve HLTB for title %s: %s", title_id, exc)
    except Exception:
        # Best-effort: a bad moment here must never surface as an error the
        # Mini App has to show — the tab just stays without an answer.
        log.exception("HLTB match/resolve failed for title %s", title_id)

    return web.json_response({"ok": True, "hltb": hltb_block})


def _extract_init_data(request: web.Request) -> str:
    dedicated = request.headers.get(INIT_DATA_HEADER, "").strip()
    if dedicated:
        return dedicated
    header = request.headers.get("Authorization", "")
    if header.startswith(AUTH_HEADER_PREFIX):
        return header[len(AUTH_HEADER_PREFIX) :].strip()
    raise web.HTTPUnauthorized(text="missing initData")


# How many of a game's patches its "Обновления" tab lists.
PATCHES_SHOWN = 10


def _extras(request: web.Request) -> SteamExtras:
    return request.app["mini_steam_extras"]


async def handle_game_guides(request: web.Request) -> web.Response:
    """The tip the Steam community's guides give for each achievement of this
    game, in the reader's language where there is one. Stored when the game's
    first new achievement was published; a game still without them is filled
    in the background, never while the request waits (a read of Steam's guides
    and the model takes minutes when Steam is slow). `complete: false` until
    the fill is done — the Mini App asks again a little later and the tips
    fill in."""
    user = await _require_user(request)
    platform = request.match_info.get("platform", "").lower()
    title_id = request.match_info.get("title_id", "")
    repo: Repo = request.app["mini_repo"]
    complete = True
    extras = _extras(request)
    if await extras.tips_due(title_id):
        extras.ensure_title(title_id)
        complete = False
    locale = await _user_locale(repo, user.tg_id)
    tips: dict[str, dict[str, str]] = {}
    for achievement_id, (tip_en, tip_ru) in (await repo.title_tips(platform, title_id)).items():
        text = (tip_ru or tip_en) if locale == "ru" else (tip_en or tip_ru)
        # Tips stored before pictures stopped counting as advice are dropped here.
        if text and has_prose(text):
            tips[achievement_id] = {"text": text}
    return web.json_response({"ok": True, "tips": tips, "complete": complete})


async def handle_game_patches(request: web.Request) -> web.Response:
    """A game's latest patches, from what is stored — poller/patch_refresh.py
    keeps them fresh. A Steam app never read yet is read now; one with no Steam
    page at all answers an empty list."""
    user = await _require_user(request)
    title_id = request.match_info.get("title_id", "")
    repo: Repo = request.app["mini_repo"]
    extras = _extras(request)
    patches = []
    try:
        appid = await extras.appid(title_id)
        if appid is not None:
            _guides_at, patches_at = await repo.steam_app_checked(appid)
            if patches_at is None:
                await extras.refresh_patches(appid)
            patches = await repo.game_patches(appid, PATCHES_SHOWN)
    except Exception:
        log.exception("steam patches failed for title %s", title_id)
    ru = await _user_locale(repo, user.tg_id) == "ru"
    return web.json_response(
        {
            "ok": True,
            "patches": [
                {
                    "title": (p.title_ru if ru and p.title_ru else p.title),
                    "date": p.published_at,
                    "text": (p.text_ru if ru and p.text_ru else p.text_en) or "",
                }
                for p in patches
            ],
        }
    )


async def _require_user(request: web.Request) -> MiniAppUser:
    try:
        init_data = _extract_init_data(request)
    except web.HTTPUnauthorized:
        # Neither header: a browser signed in through Telegram Login (#157).
        signed_in = await mini_session.session_user(request)
        if signed_in is not None:
            return signed_in
        raise
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
