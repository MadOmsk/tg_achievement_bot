"""Super-admin JSON for the Mini App. Secrets never leave this module."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from aiohttp import web

from bot.constants import Platform, TokenStatus, RarityMode
from bot.db.repo import Repo
from bot.handlers.admin import (
    DEFAULT_RARITY_MODE_DEFAULT,
    DEFAULT_RARITY_MODE_KEY,
    DEFAULT_SHOW_LINKS_DEFAULT,
    DEFAULT_SHOW_LINKS_KEY,
    FLOOD_WINDOW_MAX,
    FLOOD_WINDOW_MIN,
    NUMERIC_SETTINGS,
    RARE_THRESHOLD_MAX,
    RARE_THRESHOLD_MIN,
    WIPE_WINDOW_HOURS,
)
from bot.handlers.keyboards import next_rarity_mode
from bot.i18n import AVAILABLE_LOCALES, normalize_locale, translator
from bot.services.naming import person_name, xbox_nickname
from bot.services.psn.auth import STATUS_NOT_CONFIGURED as PSN_NOT_CONFIGURED
from bot.services.psn.auth import PsnAuth
from bot.services.psn.client import request_count_today
from bot.services.stats import month_cutoff_utc, today_cutoff_utc
from bot.services.steam.auth import STATUS_NOT_CONFIGURED as STEAM_NOT_CONFIGURED
from bot.services.steam.auth import SteamAuth, SteamKeyInvalidError
from bot.services.translate.auth import STATUS_NOT_CONFIGURED as ANTHROPIC_NOT_CONFIGURED
from bot.services.translate.auth import AnthropicAuth, AnthropicKeyInvalidError
from bot.util import utcnow

log = logging.getLogger(__name__)

_KEY_NAMES = ("steam", "psn", "anthropic")


def _usage_text(windows: list[tuple[int, int, float]]) -> str:
    if not windows:
        return "—"
    return " · ".join(f"{used}/{limit}" for used, limit, _span in windows)


async def build_admin_home(
    repo: Repo,
    *,
    xbox_usage: list[tuple[int, int, float]],
    steam_usage: list[tuple[int, int, float]],
    steam_status: str,
    psn_status: str,
) -> dict[str, Any]:
    users = await repo.admin_users()
    chats = await repo.admin_chats()
    xbox_linked = [u for u in users if u.xuid]
    return {
        "users": len(users),
        "excluded": sum(1 for u in users if u.is_excluded),
        "xbox_linked": len(xbox_linked),
        "xbox_active": sum(
            1 for u in xbox_linked if u.token_status == TokenStatus.ACTIVE and not u.is_excluded
        ),
        "xbox_broken": sum(1 for u in xbox_linked if u.token_status != TokenStatus.ACTIVE),
        "steam_linked": sum(1 for u in users if u.steam_id),
        "psn_linked": sum(1 for u in users if u.psn_account_id),
        "chats": sum(1 for c in chats if c.is_active),
        "xbox_usage": _usage_text(xbox_usage),
        "steam_usage": _usage_text(steam_usage),
        "steam_key": steam_status,
        "psn_key": psn_status,
        "psn_requests": request_count_today(),
    }


async def build_admin_keys(
    steam_auth: SteamAuth | None, psn_auth: PsnAuth | None, anthropic_auth: AnthropicAuth | None
) -> dict[str, bool]:
    steam = False
    psn = False
    anthropic = False
    if steam_auth is not None:
        steam = await steam_auth.status() != STEAM_NOT_CONFIGURED
    if psn_auth is not None:
        psn = await psn_auth.status() != PSN_NOT_CONFIGURED
    if anthropic_auth is not None:
        anthropic = await anthropic_auth.status() != ANTHROPIC_NOT_CONFIGURED
    return {"steam": steam, "psn": psn, "anthropic": anthropic}


async def build_admin_limits(repo: Repo, *, locale: str) -> dict[str, Any]:
    _ = translator("admin", locale)
    items = []
    for key, spec in NUMERIC_SETTINGS.items():
        raw = await repo.get_app_setting(key, str(spec.default))
        try:
            value = int(raw or spec.default)
        except ValueError:
            value = spec.default
        zero: str | None = None
        if spec.min == 0:
            zero = "off" if spec.zero_label == "admin-disabled" else "unlimited"
        items.append(
            {
                "key": key,
                "label": _(spec.label),
                "value": value,
                "min": spec.min,
                "max": spec.max,
                "zero_means": zero,
            }
        )
    return {"items": items}


async def build_admin_defaults(repo: Repo) -> dict[str, Any]:
    rarity = await repo.get_app_setting(DEFAULT_RARITY_MODE_KEY, DEFAULT_RARITY_MODE_DEFAULT)
    links = await repo.get_int_setting(DEFAULT_SHOW_LINKS_KEY, int(DEFAULT_SHOW_LINKS_DEFAULT))
    return {"rarity_mode": rarity or RarityMode.ALL, "show_profile_links": bool(links)}


async def build_admin_users(repo: Repo) -> dict[str, Any]:
    users = await repo.admin_users()
    today = await repo.achievement_counts_by_tg_id(today_cutoff_utc())
    month = await repo.achievement_counts_by_tg_id(month_cutoff_utc(180))
    chats = await repo.admin_chats()
    by_chat = await repo.admin_user_chat_ids()
    rows = []
    for user in users:
        rows.append(
            {
                "tg_id": user.tg_id,
                "name": person_name(
                    tg_id=user.tg_id,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    username=user.username,
                    xbox=xbox_nickname(
                        gamertag_modern=user.gamertag_modern, gamertag=user.gamertag
                    ),
                    steam=user.steam_name,
                    psn=user.psn_online_id,
                ),
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_excluded": user.is_excluded,
                "last_online_at": user.last_online_at,
                "today": today.get(user.tg_id, (0, 0))[0],
                "month": month.get(user.tg_id, (0, 0))[0],
                "xbox": bool(user.xuid),
                "steam": bool(user.steam_id),
                "psn": bool(user.psn_account_id),
                "chat_ids": by_chat.get(user.tg_id, []),
            }
        )
    return {
        "users": rows,
        "chats": [{"chat_id": chat.chat_id, "title": chat.title} for chat in chats],
    }


async def build_admin_user(repo: Repo, tg_id: int) -> dict[str, Any] | None:
    user = await repo.get_user(tg_id)
    steam = await repo.get_platform_link(tg_id, Platform.STEAM)
    psn = await repo.get_platform_link(tg_id, Platform.PSN)
    if user is None or (not user.xuid and steam is None and psn is None):
        return None
    chats = await repo.chats_of_user(tg_id)
    xbox_block = None
    if user.xuid:
        xbox_block = {
            "name": xbox_nickname(gamertag_modern=user.gamertag_modern, gamertag=user.gamertag),
            "xuid": user.xuid,
            "gamerscore": user.gamerscore,
            "achievement_count": await repo.xbox_achievement_count(tg_id),
            "token_status": None,
        }
        token = await repo.get_token(tg_id)
        if token is not None:
            xbox_block["token_status"] = token.status
    steam_block = None
    if steam is not None:
        steam_block = {
            "name": steam.display_name,
            "external_id": steam.external_id,
            "achievement_count": await repo.platform_achievement_count(tg_id, Platform.STEAM),
        }
    psn_block = None
    if psn is not None:
        psn_block = {
            "name": psn.display_name,
            "external_id": psn.external_id,
            "trophy_count": await repo.platform_achievement_count(tg_id, Platform.PSN),
            "trophy_level": psn.psn_trophy_level,
        }
    return {
        "tg_id": tg_id,
        "name": person_name(
            tg_id=tg_id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            xbox=xbox_nickname(gamertag_modern=user.gamertag_modern, gamertag=user.gamertag),
            steam=steam.display_name if steam else None,
            psn=psn.display_name if psn else None,
        ),
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_excluded": user.is_excluded,
        "chats": list(chats),
        "xbox": xbox_block,
        "steam": steam_block,
        "psn": psn_block,
    }


def serialize_admin_chat(chat: Any) -> dict[str, Any]:
    return {
        "chat_id": chat.chat_id,
        "title": chat.title,
        "is_active": chat.is_active,
        "subscribers": chat.subscribers,
        "rare_threshold_percent": chat.rare_threshold_percent,
        "daily_summary": chat.daily_summary,
        "daily_summary_time": chat.daily_summary_time,
        "tz_offset_min": chat.tz_offset_min,
        "min_gamerscore": chat.min_gamerscore,
        "flood_limit": chat.flood_limit,
        "flood_window_minutes": chat.flood_window_minutes,
        "locale": chat.locale,
    }


async def _bulk_delete(bot: Any, chat_id: int, ids: list[int]) -> bool:
    ok = True
    for start in range(0, len(ids), 100):
        try:
            await bot.delete_messages(chat_id, ids[start : start + 100])
        except Exception:
            log.info("mini admin bulk delete failed chat=%s chunk=%s", chat_id, start)
            ok = False
    return ok


def setup_admin_routes(app: web.Application) -> None:
    app.router.add_get("/api/mini/admin", handle_admin_home)
    app.router.add_get("/api/mini/admin/keys", handle_admin_keys)
    app.router.add_put("/api/mini/admin/keys/{name}", handle_admin_key_put)
    app.router.add_delete("/api/mini/admin/keys/{name}", handle_admin_key_delete)
    app.router.add_get("/api/mini/admin/limits", handle_admin_limits)
    app.router.add_patch("/api/mini/admin/limits", handle_admin_limits_patch)
    app.router.add_get("/api/mini/admin/defaults", handle_admin_defaults)
    app.router.add_patch("/api/mini/admin/defaults", handle_admin_defaults_patch)
    app.router.add_get("/api/mini/admin/users", handle_admin_users)
    app.router.add_get("/api/mini/admin/users/{tg_id}", handle_admin_user)
    app.router.add_patch("/api/mini/admin/users/{tg_id}", handle_admin_user_patch)
    app.router.add_get("/api/mini/admin/chats", handle_admin_chats)
    app.router.add_patch("/api/mini/admin/chats/{chat_id}", handle_admin_chat_patch)
    app.router.add_post("/api/mini/admin/chats/{chat_id}/actions", handle_admin_chat_action)


async def handle_admin_home(request: web.Request) -> web.Response:
    await _require_admin(request)
    repo: Repo = request.app["mini_repo"]
    xbox = request.app.get("mini_xbox_fetcher")
    steam = request.app.get("mini_steam_fetcher")
    steam_auth: SteamAuth | None = request.app.get("mini_steam_auth")
    psn_auth: PsnAuth | None = request.app.get("mini_psn_auth")
    payload = await build_admin_home(
        repo,
        xbox_usage=xbox.api_usage() if xbox is not None else [],
        steam_usage=steam.api_usage() if steam is not None else [],
        steam_status=await steam_auth.status() if steam_auth else STEAM_NOT_CONFIGURED,
        psn_status=await psn_auth.status() if psn_auth else PSN_NOT_CONFIGURED,
    )
    return web.json_response(payload)


async def handle_admin_keys(request: web.Request) -> web.Response:
    await _require_admin(request)
    return web.json_response(await _keys_payload(request))


async def handle_admin_key_put(request: web.Request) -> web.Response:
    admin = await _require_admin(request)
    name = request.match_info["name"]
    if name not in _KEY_NAMES:
        raise web.HTTPNotFound()
    body = await request.json()
    value = str(body.get("value") or "").strip()
    if not value:
        raise web.HTTPBadRequest(text="missing value")
    steam_auth: SteamAuth | None = request.app.get("mini_steam_auth")
    psn_auth: PsnAuth | None = request.app.get("mini_psn_auth")
    anthropic_auth: AnthropicAuth | None = request.app.get("mini_anthropic_auth")
    try:
        if name == "steam":
            if steam_auth is None:
                raise web.HTTPServiceUnavailable(text="steam unavailable")
            await steam_auth.set_key(value, admin.tg_id)
        elif name == "psn":
            if psn_auth is None:
                raise web.HTTPServiceUnavailable(text="psn unavailable")
            await psn_auth.set_npsso(value, admin.tg_id)
        else:
            if anthropic_auth is None:
                raise web.HTTPServiceUnavailable(text="anthropic unavailable")
            await anthropic_auth.set_key(value, admin.tg_id)
    except (SteamKeyInvalidError, AnthropicKeyInvalidError):
        return web.json_response({"ok": False, "error": "invalid"}, status=400)
    except Exception:
        log.exception("mini admin set key %s failed", name)
        return web.json_response({"ok": False, "error": "invalid"}, status=400)
    return web.json_response(await _keys_payload(request))


async def handle_admin_key_delete(request: web.Request) -> web.Response:
    admin = await _require_admin(request)
    name = request.match_info["name"]
    if name not in _KEY_NAMES:
        raise web.HTTPNotFound()
    auth = {
        "steam": request.app.get("mini_steam_auth"),
        "psn": request.app.get("mini_psn_auth"),
        "anthropic": request.app.get("mini_anthropic_auth"),
    }[name]
    if auth is None:
        raise web.HTTPServiceUnavailable()
    await auth.clear(admin.tg_id)
    return web.json_response(await _keys_payload(request))


async def handle_admin_limits(request: web.Request) -> web.Response:
    admin = await _require_admin(request)
    repo: Repo = request.app["mini_repo"]
    locale = await repo.user_locale(admin.tg_id)
    return web.json_response(await build_admin_limits(repo, locale=locale))


async def handle_admin_limits_patch(request: web.Request) -> web.Response:
    admin = await _require_admin(request)
    repo: Repo = request.app["mini_repo"]
    body = await request.json()
    key = str(body.get("key") or "")
    if key not in NUMERIC_SETTINGS:
        raise web.HTTPBadRequest(text="unknown limit")
    spec = NUMERIC_SETTINGS[key]
    try:
        value = int(body["value"])
    except (KeyError, TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(text="bad value") from exc
    if not (spec.min <= value <= spec.max):
        raise web.HTTPBadRequest(text="out of range")
    await repo.set_app_setting(key, str(value), admin.tg_id)
    locale = await repo.user_locale(admin.tg_id)
    return web.json_response(await build_admin_limits(repo, locale=locale))


async def handle_admin_defaults(request: web.Request) -> web.Response:
    await _require_admin(request)
    repo: Repo = request.app["mini_repo"]
    return web.json_response(await build_admin_defaults(repo))


async def handle_admin_defaults_patch(request: web.Request) -> web.Response:
    admin = await _require_admin(request)
    repo: Repo = request.app["mini_repo"]
    body = await request.json()
    if "rarity_mode" in body:
        mode = str(body["rarity_mode"])
        if mode not in (RarityMode.ALL, RarityMode.RARE, RarityMode.HIDDEN):
            current = await repo.get_app_setting(DEFAULT_RARITY_MODE_KEY, DEFAULT_RARITY_MODE_DEFAULT)
            mode = next_rarity_mode(current or RarityMode.ALL)
        await repo.set_app_setting(DEFAULT_RARITY_MODE_KEY, mode, admin.tg_id)
    if "show_profile_links" in body:
        await repo.set_app_setting(
            DEFAULT_SHOW_LINKS_KEY,
            "1" if body["show_profile_links"] else "0",
            admin.tg_id,
        )
    return web.json_response(await build_admin_defaults(repo))


async def handle_admin_users(request: web.Request) -> web.Response:
    await _require_admin(request)
    repo: Repo = request.app["mini_repo"]
    return web.json_response(await build_admin_users(repo))


async def handle_admin_user(request: web.Request) -> web.Response:
    await _require_admin(request)
    repo: Repo = request.app["mini_repo"]
    payload = await build_admin_user(repo, int(request.match_info["tg_id"]))
    if payload is None:
        raise web.HTTPNotFound()
    return web.json_response(payload)


async def handle_admin_user_patch(request: web.Request) -> web.Response:
    admin = await _require_admin(request)
    repo: Repo = request.app["mini_repo"]
    tg_id = int(request.match_info["tg_id"])
    body = await request.json()
    if "excluded" in body:
        await repo.set_excluded(tg_id, bool(body["excluded"]), admin.tg_id)
    action = body.get("action")
    platform = str(body.get("platform") or "")
    if action in ("sync", "reset") and platform in ("xbox", "steam", "psn"):
        await _admin_platform_action(request, tg_id, platform, action)
    payload = await build_admin_user(repo, tg_id)
    if payload is None:
        raise web.HTTPNotFound()
    return web.json_response(payload)


async def handle_admin_chats(request: web.Request) -> web.Response:
    await _require_admin(request)
    repo: Repo = request.app["mini_repo"]
    chats = await repo.admin_chats()
    return web.json_response({"chats": [serialize_admin_chat(c) for c in chats]})


async def handle_admin_chat_patch(request: web.Request) -> web.Response:
    await _require_admin(request)
    repo: Repo = request.app["mini_repo"]
    chat_id = int(request.match_info["chat_id"])
    body = await request.json()
    fields: dict[str, Any] = {}
    if "rare_threshold_percent" in body:
        value = float(body["rare_threshold_percent"])
        if not (RARE_THRESHOLD_MIN <= value <= RARE_THRESHOLD_MAX):
            raise web.HTTPBadRequest(text="bad threshold")
        fields["rare_threshold_percent"] = value
    if "flood_limit" in body:
        fields["flood_limit"] = int(body["flood_limit"])
    if "flood_window_minutes" in body:
        window = int(body["flood_window_minutes"])
        if not (FLOOD_WINDOW_MIN <= window <= FLOOD_WINDOW_MAX):
            raise web.HTTPBadRequest(text="bad window")
        fields["flood_window_minutes"] = window
    if "min_gamerscore" in body:
        fields["min_gamerscore"] = int(body["min_gamerscore"])
    if "daily_summary" in body:
        fields["daily_summary"] = 1 if body["daily_summary"] else 0
    if "daily_summary_time" in body:
        fields["daily_summary_time"] = str(body["daily_summary_time"])
    if "tz_offset_min" in body:
        fields["tz_offset_min"] = int(body["tz_offset_min"])
    if "locale" in body:
        locale = normalize_locale(str(body["locale"]))
        if locale not in AVAILABLE_LOCALES:
            raise web.HTTPBadRequest(text="bad locale")
        fields["locale"] = locale
    if fields:
        await repo.update_chat_settings(chat_id, **fields)
    if "is_active" in body:
        await repo.set_chat_active(chat_id, bool(body["is_active"]))
    chats = {c.chat_id: c for c in await repo.admin_chats()}
    chat = chats.get(chat_id)
    if chat is None:
        raise web.HTTPNotFound()
    return web.json_response(serialize_admin_chat(chat))


async def handle_admin_chat_action(request: web.Request) -> web.Response:
    await _require_admin(request)
    repo: Repo = request.app["mini_repo"]
    bot = request.app.get("mini_bot")
    if bot is None:
        raise web.HTTPServiceUnavailable(text="bot unavailable")
    chat_id = int(request.match_info["chat_id"])
    body = await request.json()
    action = str(body.get("action") or "")
    since = utcnow() - timedelta(hours=WIPE_WINDOW_HOURS)
    if action == "delete_last":
        target = await repo.last_non_system_bot_message(chat_id)
        if target is None:
            return web.json_response({"ok": True, "deleted": 0})
        try:
            await bot.delete_message(chat_id, target.message_id)
        except Exception:
            await repo.forget_bot_messages(chat_id, [target.message_id])
            return web.json_response({"ok": False, "deleted": 0}, status=400)
        await repo.forget_bot_messages(chat_id, [target.message_id])
        return web.json_response({"ok": True, "deleted": 1, "preview": target.preview})
    if action == "wipe_24h":
        ids = await repo.bot_messages_since(chat_id, since)
    elif action == "wipe_system_24h":
        ids = await repo.system_bot_messages_since(chat_id, since)
    elif action == "wipe_system_all":
        ids = await repo.system_bot_messages_since(chat_id, utcnow() - timedelta(days=3650))
    else:
        raise web.HTTPBadRequest(text="unknown action")
    ok = await _bulk_delete(bot, chat_id, ids)
    await repo.forget_bot_messages(chat_id, ids)
    return web.json_response({"ok": ok, "deleted": len(ids)})


async def _admin_platform_action(request: web.Request, tg_id: int, platform: str, action: str) -> None:
    repo: Repo = request.app["mini_repo"]
    xbox = request.app.get("mini_xbox_fetcher")
    steam_fetcher = request.app.get("mini_steam_fetcher")
    psn_fetcher = request.app.get("mini_psn_fetcher")
    locale = await repo.user_locale(tg_id)
    if platform == "xbox":
        user = await repo.get_user(tg_id)
        if user is None or not user.xuid or xbox is None:
            raise web.HTTPBadRequest(text="xbox not linked")
        if action == "reset":
            await repo.reset_xbox_data(tg_id, user.xuid)
            await xbox.backfill(tg_id, user.xuid)
        else:
            await xbox.refresh_user(tg_id, user.xuid, user.gamertag or f"id{tg_id}", locale)
        return
    if platform == "steam":
        link = await repo.get_platform_link(tg_id, Platform.STEAM)
        if link is None or steam_fetcher is None:
            raise web.HTTPBadRequest(text="steam not linked")
        if action == "reset":
            await repo.reset_steam_data(link.external_id)
            await steam_fetcher.backfill(tg_id, link.external_id)
        else:
            await steam_fetcher.refresh_user(
                tg_id, link.external_id, link.display_name or link.external_id, locale
            )
        return
    link = await repo.get_platform_link(tg_id, Platform.PSN)
    if link is None or psn_fetcher is None:
        raise web.HTTPBadRequest(text="psn not linked")
    if action == "reset":
        await repo.reset_psn_data(tg_id, link.external_id)
        await psn_fetcher.backfill(tg_id, link.external_id)
    else:
        await psn_fetcher.refresh_user(
            tg_id, link.external_id, link.display_name or link.external_id, locale
        )


async def _keys_payload(request: web.Request) -> dict[str, bool]:
    return await build_admin_keys(
        request.app.get("mini_steam_auth"),
        request.app.get("mini_psn_auth"),
        request.app.get("mini_anthropic_auth"),
    )


async def _require_admin(request: web.Request):
    from bot.web.mini_api import _require_user

    user = await _require_user(request)
    settings = request.app["mini_settings"]
    if not settings.is_admin(user.tg_id):
        raise web.HTTPForbidden(text="admin only")
    return user
