"""Super-admin JSON for the Mini App. Secrets never leave this module.

What it shows and changes comes from the same services as the bot's /admin
(#176): `admin_status` for the home, `admin_credentials` for the keys,
`admin_settings` for the numbers — this module only serializes them."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

from bot.constants import Platform, RarityMode, TokenStatus
from bot.db.repo import Repo
from bot.i18n import AVAILABLE_LOCALES, normalize_locale, translator
from bot.services import admin_cleanup
from bot.services.admin_accounts import AdminAccounts
from bot.services.admin_cleanup import Wipe
from bot.services.admin_credentials import (
    AdminCredentials,
    CredentialInvalid,
    CredentialSetupError,
    CredentialState,
)
from bot.services.admin_settings import (
    DEFAULT_RARITY_MODE_DEFAULT,
    DEFAULT_RARITY_MODE_KEY,
    FLOOD_WINDOW_MAX,
    FLOOD_WINDOW_MIN,
    NUMERIC_SETTINGS,
    SHOW_LINKS_DEFAULT,
    SHOW_LINKS_KEY,
    SettingValueError,
    numeric_values,
    rare_threshold,
    set_numeric_setting,
    set_rare_threshold,
)
from bot.services.admin_status import admin_status
from bot.services.logins import logins_of
from bot.services.naming import person_name, xbox_nickname
from bot.services.stats import month_cutoff_utc, today_cutoff_utc
from bot.views.admin import login_value
from bot.views.admin_home import format_api_usage
from bot.views.keyboards import DIGEST_CHOICES, next_rarity_mode

log = logging.getLogger(__name__)


async def build_admin_home(
    repo: Repo, credentials: AdminCredentials, *, xbox: Any, steam: Any, locale: str
) -> dict[str, Any]:
    """`services/admin_status.py`'s AdminStatus as JSON — what the bot's
    /admin home words as text (#176)."""
    status = await admin_status(
        repo,
        credentials=credentials,
        xbox_usage=xbox.api_usage() if xbox is not None else [],
        steam_usage=steam.api_usage() if steam is not None else [],
    )
    return {
        "users": status.users,
        "excluded": status.excluded,
        "xbox_linked": status.xbox_linked,
        "xbox_active": status.xbox_active,
        "xbox_broken": status.xbox_broken,
        "steam_linked": status.steam_linked,
        "psn_linked": status.psn_linked,
        "chats": status.chats,
        "xbox_usage": format_api_usage(status.xbox_usage, locale=locale),
        "steam_usage": format_api_usage(status.steam_usage, locale=locale),
        "steam_key": _key_word(status.credential("steam")),
        "psn_key": _key_word(status.credential("psn")),
        "psn_requests": status.psn_requests,
        "mail": {
            "hour": status.mail.hour,
            "hour_limit": status.mail.hour_limit,
            "day": status.mail.day,
            "day_limit": status.mail.day_limit,
        },
        "credentials": _credentials_json(status.credentials, locale=locale),
    }


def _key_word(state: CredentialState | None) -> str:
    if state is None or not state.configured:
        return "not_configured"
    return state.status or TokenStatus.ACTIVE


def _credentials_json(states: list[CredentialState], *, locale: str) -> list[dict[str, Any]]:
    """Each credential with its label and a one-line hint in the reader's
    language — the Mini App draws whatever the registry holds."""
    _ = translator("admin", locale)
    return [
        {
            "name": state.name,
            "label": _(f"admin-keys-{state.name}-label"),
            "hint": _(f"admin-keys-{state.name}-hint"),
            "configured": state.configured,
            "status": state.status,
            "checked_at": state.checked_at,
        }
        for state in states
    ]


async def build_admin_limits(repo: Repo, *, locale: str) -> dict[str, Any]:
    _ = translator("admin", locale)
    return {
        "items": [
            {
                "key": key,
                "label": _(spec.label),
                "value": value,
                "min": spec.min,
                "max": spec.max,
                "zero_means": spec.zero_means,
            }
            for key, spec, value in await numeric_values(repo)
        ]
    }


async def build_admin_defaults(repo: Repo) -> dict[str, Any]:
    rarity = await repo.get_app_setting(DEFAULT_RARITY_MODE_KEY, DEFAULT_RARITY_MODE_DEFAULT)
    links = await repo.get_int_setting(SHOW_LINKS_KEY, int(SHOW_LINKS_DEFAULT))
    return {
        "rarity_mode": rarity or RarityMode.ALL,
        "show_profile_links": bool(links),
        # One for every chat (owner, 2026-10-01) — set here, not on a chat's card.
        "rare_threshold_percent": await rare_threshold(repo),
    }


async def build_admin_users(repo: Repo) -> dict[str, Any]:
    users = await repo.admin_users()
    today = await repo.achievement_counts_by_person(today_cutoff_utc())
    month = await repo.achievement_counts_by_person(month_cutoff_utc(180))
    chats = await repo.admin_chats()
    by_chat = await repo.admin_user_chat_ids()
    rows = []
    for user in users:
        rows.append(
            {
                "person_id": user.person_id,
                "tg_id": user.tg_id,
                "name": person_name(person_id=user.person_id, handle=user.handle),
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_excluded": user.is_excluded,
                "last_online_at": user.last_online_at,
                "today": today.get(user.person_id, (0, 0))[0],
                "month": month.get(user.person_id, (0, 0))[0],
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


async def build_admin_user(repo: Repo, person: int, *, locale: str = "ru") -> dict[str, Any] | None:
    user = await repo.get_user(person)
    if user is None:
        return None
    steam = await repo.get_platform_link(person, Platform.STEAM)
    psn_links = await repo.platform_links_for(person, Platform.PSN)
    psn = psn_links[0] if psn_links else None
    if user is None or (not user.xuid and steam is None and psn is None):
        return None
    chats = await repo.chats_of_user(person)
    xbox_block = None
    if user.xuid:
        xbox_block = {
            "name": xbox_nickname(gamertag_modern=user.gamertag_modern, gamertag=user.gamertag),
            "xuid": user.xuid,
            "gamerscore": user.gamerscore,
            "achievement_count": await repo.xbox_achievement_count(person),
            "token_status": None,
        }
        token = await repo.get_token(person)
        if token is not None:
            xbox_block["token_status"] = token.status
    steam_block = None
    if steam is not None:
        steam_block = {
            "name": steam.display_name,
            "external_id": steam.external_id,
            "achievement_count": await repo.platform_achievement_count(person, Platform.STEAM),
        }
    psn_block = None
    if psn is not None:
        # The first account's fields, the person's sum, and every account
        # on its own (#10) for the per-account refresh/reset.
        psn_block = {
            "name": psn.display_name,
            "external_id": psn.external_id,
            "trophy_count": await repo.platform_achievement_count(person, Platform.PSN),
            "trophy_level": psn.psn_trophy_level,
            "accounts": [
                {
                    "name": link.display_name,
                    "external_id": link.external_id,
                    "trophy_count": await repo.account_achievement_count(
                        Platform.PSN, link.external_id
                    ),
                    "trophy_level": link.psn_trophy_level,
                    "publishes": link.publishes,
                }
                for link in psn_links
            ],
        }
    return {
        "person_id": person,
        "tg_id": user.tg_id,
        "email": user.email,
        "name": person_name(person_id=person, handle=user.handle),
        # Every way in, linked or not (owner, 2026-10-07) — the list the bot's
        # card shows too (`services/logins.py`).
        "logins": _logins_json(user, locale=locale),
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_excluded": user.is_excluded,
        "chats": list(chats),
        "xbox": xbox_block,
        "steam": steam_block,
        "psn": psn_block,
    }


def _logins_json(user: Any, *, locale: str) -> list[dict[str, Any]]:
    _ = translator("admin", locale)
    return [
        {
            "kind": login.kind,
            "label": _(f"admin-logins-{login.kind}"),
            "linked": login.linked,
            "value": login_value(login, locale=locale) if login.linked else None,
        }
        for login in logins_of(user)
    ]


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
        "digest_threshold": chat.digest_threshold,
        "locale": chat.locale,
    }


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
    app.router.add_get("/api/mini/admin/users/{ref}", handle_admin_user)
    app.router.add_patch("/api/mini/admin/users/{ref}", handle_admin_user_patch)
    app.router.add_delete("/api/mini/admin/users/{ref}", handle_admin_user_delete)
    app.router.add_post("/api/mini/admin/users/{ref}/delete", handle_admin_user_delete)
    app.router.add_get("/api/mini/admin/chats", handle_admin_chats)
    app.router.add_patch("/api/mini/admin/chats/{chat_id}", handle_admin_chat_patch)
    app.router.add_post("/api/mini/admin/chats/{chat_id}/actions", handle_admin_chat_action)


async def handle_admin_home(request: web.Request) -> web.Response:
    admin = await _require_superadmin(request)
    repo: Repo = request.app["mini_repo"]
    payload = await build_admin_home(
        repo,
        request.app["mini_admin_credentials"],
        xbox=request.app.get("mini_xbox_fetcher"),
        steam=request.app.get("mini_steam_fetcher"),
        locale=await repo.user_locale(admin.person_id),
    )
    return web.json_response(payload)


async def handle_admin_keys(request: web.Request) -> web.Response:
    admin = await _require_superadmin(request)
    return web.json_response(await _keys_payload(request, admin))


async def handle_admin_key_put(request: web.Request) -> web.Response:
    admin = await _require_superadmin(request)
    credentials: AdminCredentials = request.app["mini_admin_credentials"]
    name = request.match_info["name"]
    if name not in credentials:
        raise web.HTTPNotFound()
    body = await request.json()
    value = str(body.get("value") or "").strip()
    if not value:
        raise web.HTTPBadRequest(text="missing value")
    try:
        await credentials.set(name, value, admin.tg_id)
    except CredentialInvalid:
        return web.json_response({"ok": False, "error": "invalid"}, status=400)
    except CredentialSetupError:
        log.exception("mini admin set key %s: could not set up the client", name)
        return web.json_response({"ok": False, "error": "setup"}, status=400)
    return web.json_response(await _keys_payload(request, admin))


async def handle_admin_key_delete(request: web.Request) -> web.Response:
    admin = await _require_superadmin(request)
    credentials: AdminCredentials = request.app["mini_admin_credentials"]
    name = request.match_info["name"]
    if name not in credentials:
        raise web.HTTPNotFound()
    await credentials.clear(name, admin.tg_id)
    return web.json_response(await _keys_payload(request, admin))


async def handle_admin_limits(request: web.Request) -> web.Response:
    admin = await _require_superadmin(request)
    repo: Repo = request.app["mini_repo"]
    locale = await repo.user_locale(admin.person_id)
    return web.json_response(await build_admin_limits(repo, locale=locale))


async def handle_admin_limits_patch(request: web.Request) -> web.Response:
    admin = await _require_superadmin(request)
    repo: Repo = request.app["mini_repo"]
    body = await request.json()
    key = str(body.get("key") or "")
    if key not in NUMERIC_SETTINGS:
        raise web.HTTPBadRequest(text="unknown limit")
    try:
        await set_numeric_setting(repo, key, body.get("value"), admin.tg_id)
    except SettingValueError as exc:
        raise web.HTTPBadRequest(text=f"bad value: {exc.reason}") from exc
    locale = await repo.user_locale(admin.person_id)
    return web.json_response(await build_admin_limits(repo, locale=locale))


async def handle_admin_defaults(request: web.Request) -> web.Response:
    await _require_superadmin(request)
    repo: Repo = request.app["mini_repo"]
    return web.json_response(await build_admin_defaults(repo))


async def handle_admin_defaults_patch(request: web.Request) -> web.Response:
    admin = await _require_superadmin(request)
    repo: Repo = request.app["mini_repo"]
    body = await request.json()
    if "rarity_mode" in body:
        mode = str(body["rarity_mode"])
        if mode not in (RarityMode.ALL, RarityMode.RARE, RarityMode.HIDDEN):
            current = await repo.get_app_setting(
                DEFAULT_RARITY_MODE_KEY, DEFAULT_RARITY_MODE_DEFAULT
            )
            mode = next_rarity_mode(current or RarityMode.ALL)
        await repo.set_app_setting(DEFAULT_RARITY_MODE_KEY, mode, admin.tg_id)
    if "rare_threshold_percent" in body:
        try:
            await set_rare_threshold(repo, body["rare_threshold_percent"], admin.tg_id)
        except SettingValueError as exc:
            raise web.HTTPBadRequest(text="bad threshold") from exc
    if "show_profile_links" in body:
        await repo.set_app_setting(
            SHOW_LINKS_KEY,
            "1" if body["show_profile_links"] else "0",
            admin.tg_id,
        )
    return web.json_response(await build_admin_defaults(repo))


async def handle_admin_users(request: web.Request) -> web.Response:
    await _require_superadmin(request)
    repo: Repo = request.app["mini_repo"]
    return web.json_response(await build_admin_users(repo))


async def _person_of(request: web.Request) -> int:
    """The person a user route is about: `p<person id>` (#156), or the bare
    Telegram id older screens sent."""
    repo: Repo = request.app["mini_repo"]
    raw = request.match_info["ref"]
    try:
        person = int(raw[1:]) if raw.startswith("p") else await repo.person_id(int(raw))
    except ValueError as exc:
        raise web.HTTPBadRequest(text="bad person") from exc
    if person is None:
        raise web.HTTPNotFound()
    return person


async def handle_admin_user(request: web.Request) -> web.Response:
    admin = await _require_superadmin(request)
    repo: Repo = request.app["mini_repo"]
    payload = await build_admin_user(
        repo, await _person_of(request), locale=await repo.user_locale(admin.person_id)
    )
    if payload is None:
        raise web.HTTPNotFound()
    return web.json_response(payload)


async def handle_admin_user_patch(request: web.Request) -> web.Response:
    admin = await _require_superadmin(request)
    repo: Repo = request.app["mini_repo"]
    person = await _person_of(request)
    body = await request.json()
    if "excluded" in body:
        await repo.set_excluded(person, bool(body["excluded"]), admin.tg_id)
    action = body.get("action")
    platform = str(body.get("platform") or "")
    message = None
    if action in ("sync", "reset") and platform in ("xbox", "steam", "psn"):
        account_id = str(body.get("account_id") or "").strip() or None
        message = await _admin_platform_action(request, person, platform, action, account_id)
    payload = await build_admin_user(repo, person, locale=await repo.user_locale(admin.person_id))
    if payload is None:
        raise web.HTTPNotFound()
    # What a refresh found, worded as the bot's card words it.
    payload["message"] = message
    return web.json_response(payload)


async def handle_admin_user_delete(request: web.Request) -> web.Response:
    await _require_superadmin(request)
    repo: Repo = request.app["mini_repo"]
    deleted = await repo.delete_person(await _person_of(request), is_superadmin=True)
    if not deleted:
        raise web.HTTPNotFound()
    return web.json_response({"ok": True})


async def handle_admin_chats(request: web.Request) -> web.Response:
    await _require_superadmin(request)
    repo: Repo = request.app["mini_repo"]
    chats = await repo.admin_chats()
    return web.json_response({"chats": [serialize_admin_chat(c) for c in chats]})


async def handle_admin_chat_patch(request: web.Request) -> web.Response:
    admin = await _require_superadmin(request)
    repo: Repo = request.app["mini_repo"]
    chat_id = int(request.match_info["chat_id"])
    body = await request.json()
    fields: dict[str, Any] = {}
    if "rare_threshold_percent" in body:
        # One for every chat (owner, 2026-10-01): a chat card that still sends
        # it sets the global value.
        try:
            await set_rare_threshold(repo, body["rare_threshold_percent"], admin.tg_id)
        except SettingValueError as exc:
            raise web.HTTPBadRequest(text="bad threshold") from exc
    if "flood_limit" in body:
        fields["flood_limit"] = int(body["flood_limit"])
    if "flood_window_minutes" in body:
        window = int(body["flood_window_minutes"])
        if not (FLOOD_WINDOW_MIN <= window <= FLOOD_WINDOW_MAX):
            raise web.HTTPBadRequest(text="bad window")
        fields["flood_window_minutes"] = window
    if "min_gamerscore" in body:
        fields["min_gamerscore"] = int(body["min_gamerscore"])
    if "digest_threshold" in body:
        digest = int(body["digest_threshold"])
        if digest not in DIGEST_CHOICES:
            raise web.HTTPBadRequest(text="bad digest_threshold")
        fields["digest_threshold"] = digest
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
    await _require_superadmin(request)
    repo: Repo = request.app["mini_repo"]
    bot = request.app.get("mini_bot")
    if bot is None:
        raise web.HTTPServiceUnavailable(text="bot unavailable")
    chat_id = int(request.match_info["chat_id"])
    body = await request.json()
    action = str(body.get("action") or "")
    # The bot's chat card does the same (`services/admin_cleanup.py`).
    if action == "delete_last":
        result = await admin_cleanup.delete_last(bot, repo, chat_id)
        if result is None:
            return web.json_response({"ok": True, "deleted": 0})
        if not result.deleted:
            return web.json_response({"ok": False, "deleted": 0}, status=400)
        return web.json_response({"ok": True, "deleted": 1, "preview": result.preview})
    try:
        kind = Wipe(action)
    except ValueError as exc:
        raise web.HTTPBadRequest(text="unknown action") from exc
    ids = await admin_cleanup.messages_to_wipe(repo, chat_id, kind)
    ok = await admin_cleanup.wipe(bot, repo, chat_id, ids)
    return web.json_response({"ok": ok, "deleted": len(ids)})


async def _admin_platform_action(
    request: web.Request, person: int, platform: str, action: str, account_id: str | None = None
) -> str | None:
    """The bot's "🔄 Обновить" / "🗑 Сброс", the same code
    (`services/admin_accounts.py`). The words a refresh ends with, if any."""
    repo: Repo = request.app["mini_repo"]
    accounts = AdminAccounts(
        repo,
        request.app["mini_settings"],
        xbox=request.app.get("mini_xbox_fetcher"),
        steam=request.app.get("mini_steam_fetcher"),
        psn=request.app.get("mini_psn_fetcher"),
    )
    locale = await repo.user_locale(person)
    if action == "reset":
        if not await accounts.reset(platform, person, account_id):
            raise web.HTTPBadRequest(text=f"{platform} not linked")
        return None
    summary = await accounts.refresh(platform, person, locale=locale, account_id=account_id)
    if summary is None:
        raise web.HTTPBadRequest(text=f"{platform} not linked")
    return summary


async def _keys_payload(request: web.Request, admin: Any) -> dict[str, Any]:
    repo: Repo = request.app["mini_repo"]
    credentials: AdminCredentials = request.app["mini_admin_credentials"]
    return {
        "keys": _credentials_json(
            await credentials.states(), locale=await repo.user_locale(admin.person_id)
        )
    }


async def _require_superadmin(request: web.Request):
    from bot.web.mini_api import _require_user

    user = await _require_user(request)
    settings = request.app["mini_settings"]
    if not settings.is_superadmin(user.tg_id):
        raise web.HTTPForbidden(text="admin only")
    return user
