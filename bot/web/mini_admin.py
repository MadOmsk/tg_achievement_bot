"""Super-admin JSON for the Mini App. Secrets never leave this module.

What it shows and changes comes from the same services as the bot's /admin
(#176): `admin_status` for the home, `admin_credentials` for the keys,
`admin_settings` for the numbers — this module only serializes them."""

from __future__ import annotations

import html
import json
import logging
import re
from typing import Any

from aiohttp import web

from bot.constants import Platform, TokenStatus
from bot.db.repo import Repo
from bot.handlers.delivery import send_picture_samples, send_promo, tell_new_chat_admin
from bot.i18n import translator
from bot.services import roles
from bot.services.admin_actions import AdminContext, Confirm, Target, perform
from bot.services.admin_actions import available as available_actions
from bot.services.admin_credentials import (
    AdminCredentials,
    CredentialInvalid,
    CredentialSetupError,
    CredentialState,
)
from bot.services.admin_registry import GROUPS, Kind, Scope, group_label, settings_of, value_label
from bot.services.admin_registry import hint as registry_hint
from bot.services.admin_registry import label as registry_label
from bot.services.admin_registry import set_value as set_setting
from bot.services.admin_registry import values as registry_values
from bot.services.admin_settings import (
    SettingValueError,
)
from bot.services.admin_status import admin_status
from bot.services.logins import logins_of
from bot.services.naming import person_name, xbox_nickname
from bot.services.stats import month_cutoff_utc, today_cutoff_utc
from bot.views.admin import login_value, rarity_label, tg_name
from bot.views.admin_home import usage_by_credential, usage_rows

log = logging.getLogger(__name__)


async def build_admin_home(
    repo: Repo, credentials: AdminCredentials, *, locale: str
) -> dict[str, Any]:
    """`services/admin_status.py`'s AdminStatus as JSON — what the bot's
    /admin home words as text (#176). `usage` is the bot's own lines,
    label and value: a new one shows in the Mini App with no change there."""
    status = await admin_status(repo, credentials=credentials)
    return {
        "users": status.users,
        "excluded": status.excluded,
        "xbox_linked": status.xbox_linked,
        "xbox_active": status.xbox_active,
        "xbox_broken": status.xbox_broken,
        "steam_linked": status.steam_linked,
        "psn_linked": status.psn_linked,
        "chats": status.chats,
        "usage": [
            {"label": label, "value": value} for label, value in usage_rows(status, locale=locale)
        ],
        "steam_key": _key_word(status.credential("steam")),
        "psn_key": _key_word(status.credential("psn")),
        "mail": {
            "hour": status.mail.hour,
            "hour_limit": status.mail.hour_limit,
            "day": status.mail.day,
            "day_limit": status.mail.day_limit,
            "server": status.mail.server,
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


async def build_admin_settings(
    repo: Repo, scope: Scope, *, locale: str, chat: Any = None
) -> dict[str, Any]:
    """The registry's settings of a scope, grouped, with their values,
    bounds, choices and labels in the reader's language (#176) — the Mini App
    draws whatever this lists, so a new setting needs no change there."""
    current = await registry_values(repo, scope, chat)
    groups = []
    for group in GROUPS[scope]:
        items = [
            {
                "key": str(setting.key),
                "label": registry_label(setting, locale=locale),
                "hint": registry_hint(setting, locale=locale),
                "kind": str(setting.kind),
                "value": current[setting.key],
                "min": setting.min,
                "max": setting.max,
                "zero_means": setting.zero_means,
                "options": [
                    {
                        "value": option,
                        "label": value_label(setting, option, locale=locale, place=True),
                    }
                    for option in setting.options()
                    if setting.kind is not Kind.BOOL
                ],
            }
            for setting in settings_of(scope, group)
        ]
        if items:
            groups.append(
                {
                    "id": group,
                    "title": group_label(scope, group, locale=locale),
                    "items": items,
                }
            )
    return {"groups": groups}


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
                "role": roles.stored(user.role),
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
    tokens = {token.account_id: token for token in await repo.psn_tokens_of(person)}
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
                    # Which token reads it (#233) — never the token.
                    "token": tokens[link.external_id].status
                    if link.external_id in tokens
                    else None,
                    "token_checked_at": tokens[link.external_id].checked_at
                    if link.external_id in tokens
                    else None,
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
        # The rarity mode, worded as the bot's card words it.
        "rarity": {
            "title": translator("admin", locale)("admin-rarity-title"),
            "value": await rarity_label(repo, person, locale=locale),
        },
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
    """A chat in the list; its settings are `/chats/{id}/settings`."""
    return {
        "chat_id": chat.chat_id,
        "title": chat.title,
        "is_active": chat.is_active,
        "subscribers": chat.subscribers,
    }


def setup_admin_routes(app: web.Application) -> None:
    app.router.add_get("/api/mini/admin", handle_admin_home)
    app.router.add_get("/api/mini/admin/keys", handle_admin_keys)
    app.router.add_put("/api/mini/admin/keys/{name}", handle_admin_key_put)
    app.router.add_delete("/api/mini/admin/keys/{name}", handle_admin_key_delete)
    app.router.add_get("/api/mini/admin/settings", handle_admin_settings)
    app.router.add_patch("/api/mini/admin/settings", handle_admin_settings_patch)
    app.router.add_get("/api/mini/admin/users", handle_admin_users)
    app.router.add_get("/api/mini/admin/users/{ref}", handle_admin_user)
    app.router.add_get("/api/mini/admin/users/{ref}/role", handle_role_get)
    app.router.add_get("/api/mini/admin/chats", handle_admin_chats)
    app.router.add_get("/api/mini/admin/chats/{chat_id}/settings", handle_admin_chat_settings)
    app.router.add_patch(
        "/api/mini/admin/chats/{chat_id}/settings", handle_admin_chat_settings_patch
    )
    app.router.add_get("/api/mini/admin/chats/{chat_id}/admin", handle_chat_admin_get)
    app.router.add_put("/api/mini/admin/chats/{chat_id}/admin", handle_chat_admin_put)
    app.router.add_delete("/api/mini/admin/chats/{chat_id}/admin", handle_chat_admin_delete)
    app.router.add_get("/api/mini/admin/actions", handle_admin_actions)
    app.router.add_post("/api/mini/admin/actions", handle_admin_action)


async def handle_admin_home(request: web.Request) -> web.Response:
    admin, _access = await _require(request, "admin")
    repo: Repo = request.app["mini_repo"]
    payload = await build_admin_home(
        repo,
        request.app["mini_admin_credentials"],
        locale=await repo.user_locale(admin.person_id),
    )
    return web.json_response(payload)


async def handle_admin_keys(request: web.Request) -> web.Response:
    admin, _access = await _require(request, "superadmin")
    return web.json_response(await _keys_payload(request, admin))


async def handle_admin_key_put(request: web.Request) -> web.Response:
    admin, _access = await _require(request, "superadmin")
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
    admin, _access = await _require(request, "superadmin")
    credentials: AdminCredentials = request.app["mini_admin_credentials"]
    name = request.match_info["name"]
    if name not in credentials:
        raise web.HTTPNotFound()
    await credentials.clear(name, admin.tg_id)
    return web.json_response(await _keys_payload(request, admin))


async def handle_admin_settings(request: web.Request) -> web.Response:
    admin, _access = await _require(request, "admin")
    repo: Repo = request.app["mini_repo"]
    locale = await repo.user_locale(admin.person_id)
    return web.json_response(await build_admin_settings(repo, "global", locale=locale))


async def handle_admin_settings_patch(request: web.Request) -> web.Response:
    admin, _access = await _require(request, "admin")
    repo: Repo = request.app["mini_repo"]
    body = await request.json()
    await _set(repo, "global", body, admin.tg_id)
    locale = await repo.user_locale(admin.person_id)
    return web.json_response(await build_admin_settings(repo, "global", locale=locale))


async def _set(
    repo: Repo, scope: Scope, body: dict[str, Any], admin_id: int | None, chat_id: int | None = None
) -> None:
    """The bot's own check (`admin_registry.set_value`): an unknown key or a
    value out of bounds is a 400 that says which."""
    key = str(body.get("key") or "")
    try:
        await set_setting(repo, scope, key, body.get("value"), admin_id, chat_id=chat_id)
    except KeyError as exc:
        raise web.HTTPBadRequest(text="unknown setting") from exc
    except SettingValueError as exc:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": exc.reason, "min": exc.minimum, "max": exc.maximum}),
            content_type="application/json",
        ) from exc


async def handle_admin_users(request: web.Request) -> web.Response:
    await _require(request, "admin")
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
    admin, _access = await _require(request, "admin")
    repo: Repo = request.app["mini_repo"]
    payload = await build_admin_user(
        repo, await _person_of(request), locale=await repo.user_locale(admin.person_id)
    )
    if payload is None:
        raise web.HTTPNotFound()
    return web.json_response(payload)


async def handle_admin_chats(request: web.Request) -> web.Response:
    """Every chat for an app admin; a chat admin's own (#232)."""
    _admin, access = await _require(request, "chat")
    repo: Repo = request.app["mini_repo"]
    chats = [c for c in await repo.admin_chats() if access.chat(c.chat_id)]
    return web.json_response({"chats": [serialize_admin_chat(c) for c in chats]})


async def _chat_of(request: web.Request, access: roles.Access | None = None) -> Any:
    repo: Repo = request.app["mini_repo"]
    try:
        chat_id = int(request.match_info["chat_id"])
    except ValueError as exc:
        raise web.HTTPBadRequest(text="bad chat") from exc
    if access is not None and not access.chat(chat_id):
        raise web.HTTPForbidden(text="not your chat")
    chat = next((c for c in await repo.admin_chats() if c.chat_id == chat_id), None)
    if chat is None:
        raise web.HTTPNotFound()
    return chat


async def handle_admin_chat_settings(request: web.Request) -> web.Response:
    admin, access = await _require(request, "chat")
    repo: Repo = request.app["mini_repo"]
    chat = await _chat_of(request, access)
    locale = await repo.user_locale(admin.person_id)
    return web.json_response(await build_admin_settings(repo, "chat", locale=locale, chat=chat))


async def handle_admin_chat_settings_patch(request: web.Request) -> web.Response:
    admin, access = await _require(request, "chat")
    repo: Repo = request.app["mini_repo"]
    chat = await _chat_of(request, access)
    await _set(repo, "chat", await request.json(), admin.tg_id, chat_id=chat.chat_id)
    chat = await _chat_of(request)
    locale = await repo.user_locale(admin.person_id)
    return web.json_response(await build_admin_settings(repo, "chat", locale=locale, chat=chat))


def _action_context(request: web.Request, admin: Any, access: roles.Access) -> AdminContext:
    settings = request.app["mini_settings"]
    bot = request.app.get("mini_bot")

    async def promo(chat: Any) -> None:
        if bot is None:
            raise RuntimeError("bot unavailable")
        await send_promo(bot, chat.chat_id, chat.locale, settings.mini_app_url)

    async def samples() -> int:
        if bot is None or admin.tg_id is None:
            raise RuntimeError("bot unavailable")
        repo: Repo = request.app["mini_repo"]
        locale = await repo.user_locale(admin.person_id)
        return await send_picture_samples(bot, repo, settings, admin.tg_id, locale=locale)

    return AdminContext(
        request.app["mini_repo"],
        settings,
        bot=bot,
        xbox=request.app.get("mini_xbox_fetcher"),
        steam=request.app.get("mini_steam_fetcher"),
        psn=request.app.get("mini_psn_fetcher"),
        admin_id=admin.tg_id,
        admin_person=admin.person_id,
        send_promo=promo,
        send_picture_samples=samples,
        access=access,
    )


def _action_target(scope: str, raw: str) -> Target:
    try:
        return Target.decode(scope, raw)  # type: ignore[arg-type]
    except ValueError as exc:
        raise web.HTTPBadRequest(text="bad target") from exc


async def handle_admin_actions(request: web.Request) -> web.Response:
    """A card's actions, from the registry the bot's card draws
    (`services/admin_actions.py`)."""
    admin, access = await _require(request, "chat")
    scope = request.query.get("scope", "")
    if scope not in ("user", "chat", "global"):
        raise web.HTTPBadRequest(text="bad scope")
    target = _action_target(scope, request.query.get("target", ""))
    repo: Repo = request.app["mini_repo"]
    locale = await repo.user_locale(admin.person_id)
    _ = translator("admin", locale)
    views = await available_actions(
        _action_context(request, admin, access),
        scope,  # type: ignore[arg-type]
        target,
        locale=locale,
    )
    return web.json_response(
        {
            "actions": [
                {
                    "id": v.id,
                    "scope": v.scope,
                    "target": v.target,
                    "label": v.label,
                    "danger": v.danger,
                    "section": v.section,
                    "section_title": (
                        _(f"admin-action-section-{v.section}") if v.section else None
                    ),
                }
                for v in views
            ]
        }
    )


async def handle_admin_action(request: web.Request) -> web.Response:
    """One step of an action: the next confirmation to ask, or what it did —
    the same steps and words as the bot's."""
    admin, access = await _require(request, "chat")
    body = await request.json()
    scope = str(body.get("scope") or "")
    if scope not in ("user", "account", "chat", "global"):
        raise web.HTTPBadRequest(text="bad scope")
    target = _action_target(scope, str(body.get("target") or ""))
    try:
        step = int(body.get("step") or 0)
    except (TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(text="bad step") from exc
    repo: Repo = request.app["mini_repo"]
    result = await perform(
        _action_context(request, admin, access),
        scope,  # type: ignore[arg-type]
        target,
        str(body.get("action") or ""),
        step,
        locale=await repo.user_locale(admin.person_id),
    )
    if isinstance(result, Confirm):
        return web.json_response(
            {"confirm": {"text": _plain(result.text), "yes": result.yes, "step": result.step}}
        )
    return web.json_response(
        {
            "done": {
                "ok": result.ok,
                "text": _plain(result.text) if result.text else None,
                "gone": result.gone,
            }
        }
    )


def _plain(text: str) -> str:
    """The bot's words without its HTML: the Mini App shows plain text."""
    return html.unescape(re.sub(r"<[^>]+>", "", text))


async def _keys_payload(request: web.Request, admin: Any) -> dict[str, Any]:
    """Every credential with its state, check, load and hint, and the players'
    own PSN tokens (#233) — the bot's keys screens, as data."""
    repo: Repo = request.app["mini_repo"]
    credentials: AdminCredentials = request.app["mini_admin_credentials"]
    locale = await repo.user_locale(admin.person_id)
    keys = _credentials_json(await credentials.states(), locale=locale)
    usage = usage_by_credential(await admin_status(repo, credentials=credentials), locale=locale)
    for key in keys:
        key["usage"] = usage.get(key["name"])
    alive, dead = await repo.psn_token_counts()
    return {
        "keys": keys,
        "psn_tokens": {
            "alive": alive,
            "dead": dead,
            "shared": await repo.psn_accounts_without_token(),
            "accounts": [
                {
                    "account_id": row["account_id"],
                    "name": row["display_name"] or row["account_id"],
                    "person_id": row["person_id"],
                    "who": person_name(person_id=row["person_id"], handle=row["handle"]),
                    "status": row["status"],
                    "checked_at": row["checked_at"],
                    "dead_at": row["dead_at"],
                }
                for row in await repo.psn_token_overview()
            ],
        },
    }


async def _require(request: web.Request, need: roles.Need) -> tuple[Any, roles.Access]:
    """Who is asking and what they may do (#232). `chat` lets in anybody
    with a chat to administer; the route checks which chat."""
    from bot.web.mini_api import _require_user

    user = await _require_user(request)
    access = await roles.access_of_person(
        request.app["mini_repo"], request.app["mini_settings"], user.person_id, user.tg_id
    )
    allowed = access.any if need == "chat" else access.allows(need)
    if not allowed:
        raise web.HTTPForbidden(text=f"{need} only")
    return user, access


async def _role_giver(request: web.Request):
    """Giving roles is a super-admin's alone (owner, 2026-10-28)."""
    from bot.web.mini_api import _require_user

    user = await _require_user(request)
    repo: Repo = request.app["mini_repo"]
    if not request.app["mini_settings"].is_superadmin(user.tg_id) and not roles.gives_roles(
        await repo.person_role(user.person_id)
    ):
        raise web.HTTPForbidden(text="superadmin only")
    return user


async def handle_role_get(request: web.Request) -> web.Response:
    user = await _role_giver(request)
    repo: Repo = request.app["mini_repo"]
    person = await _person_of(request)
    settings = request.app["mini_settings"]
    tg_id = await repo.tg_id_of(person)
    return web.json_response(
        {
            "ok": True,
            "role": roles.stored(await repo.person_role(person)),
            # Named in SUPERADMIN_TG_IDS (a super-admin whatever the app
            # says), or oneself: the role actions are not offered for them.
            "fixed": settings.is_superadmin(tg_id) or person == user.person_id,
        }
    )


# ----------------------------------------------------------------- chat admin

# One per chat (#232): an app admin appoints and removes; the chat admin
# hands their own role on, and loses it. The candidates are the chat's known
# members — subscribed, or seen writing there — as in the bot.


async def _chat_admin_payload(repo: Repo, chat_id: int, access: roles.Access, me: int | None):
    current = await repo.chat_admin(chat_id)
    candidates = [
        {"tg_id": tg_id, "person_id": person, "name": person_name(person_id=person, handle=handle)}
        for tg_id, person, handle in await repo.chat_admin_candidates(chat_id)
        if tg_id != current
    ]
    return {
        "admin": None
        if current is None
        else {"tg_id": current, "name": await tg_name(repo, current)},
        "candidates": candidates,
        # The chat admin themselves hands the role on; an app admin appoints.
        "hand_on": not access.app,
        "can_remove": access.app and current is not None,
    }


async def handle_chat_admin_get(request: web.Request) -> web.Response:
    admin, access = await _require(request, "chat")
    chat = await _chat_of(request, access)
    repo: Repo = request.app["mini_repo"]
    return web.json_response(await _chat_admin_payload(repo, chat.chat_id, access, admin.tg_id))


async def handle_chat_admin_put(request: web.Request) -> web.Response:
    admin, access = await _require(request, "chat")
    chat = await _chat_of(request, access)
    repo: Repo = request.app["mini_repo"]
    try:
        tg_id = int(((await request.json()) or {}).get("tg_id"))
    except (TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(text="bad tg_id") from exc
    if tg_id not in {row[0] for row in await repo.chat_admin_candidates(chat.chat_id)}:
        return web.json_response({"ok": False, "error": "not_a_member"}, status=400)
    await repo.set_chat_admin(chat.chat_id, tg_id, admin.tg_id)
    bot = request.app.get("mini_bot")
    if bot is not None:
        await tell_new_chat_admin(bot, repo, tg_id, chat)
    after = await roles.access_of_person(
        repo, request.app["mini_settings"], admin.person_id, admin.tg_id
    )
    return web.json_response({"ok": True, "still": after.chat(chat.chat_id)})


async def handle_chat_admin_delete(request: web.Request) -> web.Response:
    admin, access = await _require(request, "admin")
    chat = await _chat_of(request, access)
    repo: Repo = request.app["mini_repo"]
    await repo.set_chat_admin(chat.chat_id, None, admin.tg_id)
    return web.json_response(await _chat_admin_payload(repo, chat.chat_id, access, admin.tg_id))
