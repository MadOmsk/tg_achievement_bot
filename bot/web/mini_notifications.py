"""The Mini App's side of the app's own notifications (#164): the list, and the
browsers that allow push.

- `GET /api/mini/notifications` — the latest notices, worded in the reader's
  language, and how many are unread; `POST /api/mini/notifications/read` marks
  them all read.
- `GET /api/mini/push/key` — the server's public key, for the browser to
  subscribe with (`available` is false when push is not set up);
  `POST /api/mini/push/subscription` keeps a browser's subscription for the
  person, `DELETE` forgets it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

from aiohttp import web

from bot.db.repo import Repo
from bot.services.notifier import KINDS, UNKNOWN, Notifier, listed, wording
from bot.web.mini_auth import MiniAppUser

RequireUser = Callable[[web.Request], Awaitable[MiniAppUser]]
MAX_ENDPOINT_LENGTH = 1024
# The push services browsers subscribe through (Chrome and every Chromium
# browser, Firefox, Safari, Edge). The server posts to whatever address is
# stored here, so an arbitrary one would make it call any host a person
# names — an internal one included.
PUSH_HOSTS = (
    "fcm.googleapis.com",
    "android.googleapis.com",
    "updates.push.services.mozilla.com",
    "push.services.mozilla.com",
    "web.push.apple.com",
    "push.apple.com",
    "notify.windows.com",
)


def is_push_service(endpoint: str) -> bool:
    """An https address on one of the known push services' hosts."""
    try:
        parts = urlsplit(endpoint)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return (
        parts.scheme == "https"
        and parts.port in (None, 443)
        and any(host == known or host.endswith("." + known) for known in PUSH_HOSTS)
    )


async def _body(request: web.Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as exc:
        raise web.HTTPBadRequest(text="invalid json") from exc
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(text="invalid json")
    return body


def register(app: web.Application, require_user: RequireUser) -> None:
    async def listing(request: web.Request) -> web.Response:
        user = await require_user(request)
        repo: Repo = request.app["mini_repo"]
        locale = await repo.user_locale(user.person_id)
        rows = await repo.notifications_of(user.person_id)

        async def _cover(title_id: str | None) -> str | None:
            if not title_id:
                return None
            if title_id not in covers:
                covers[title_id] = await repo.title_icon_url(title_id)
            return covers[title_id]

        items = []
        covers: dict[str, str | None] = {}
        for row in rows:
            spec = KINDS.get(row.kind, UNKNOWN)
            field = spec.person_field
            game = (
                {
                    "platform": row.data["platform"],
                    "title_id": row.data["title_id"],
                    "name": row.data.get("game"),
                }
                if spec.game and row.data.get("platform") and row.data.get("title_id")
                else None
            )
            items.append(
                {
                    "id": row.id,
                    "kind": row.kind,
                    "text": wording(row.kind, row.data, locale),
                    **listed(row.kind, row.data, locale),
                    "created_at": row.created_at,
                    "read": row.read_at is not None,
                    # Whom a tap opens, when the notice is about somebody.
                    "person_id": row.data.get(field) if field else None,
                    "name": row.data.get("name"),
                    # The game a tap opens, on that person's progress.
                    "game": game,
                    # A game's post a tap opens over its game (owner, 2026-10-08).
                    "news": {"appid": row.data["appid"], "gid": row.data["gid"]}
                    if row.kind == "game_news" and row.data.get("appid") and row.data.get("gid")
                    else None,
                    # The game's picture, for a notice about a game (its news).
                    "cover": await _cover(row.data.get("title_id"))
                    if row.kind == "game_news"
                    else None,
                }
            )
        return web.json_response(
            {"items": items, "unread": await repo.unread_notifications(user.person_id)}
        )

    async def mark_read(request: web.Request) -> web.Response:
        user = await require_user(request)
        repo: Repo = request.app["mini_repo"]
        # One notice (a tap on it) or, with no ids, all of them.
        body = await _body(request) if request.can_read_body else {}
        raw = body.get("ids")
        ids = [int(i) for i in raw if isinstance(i, int)] if isinstance(raw, list) else None
        await repo.mark_notifications_read(user.person_id, ids)
        return web.json_response(
            {"ok": True, "unread": await repo.unread_notifications(user.person_id)}
        )

    async def push_key(request: web.Request) -> web.Response:
        await require_user(request)
        notifier: Notifier | None = request.app.get("mini_notifications")
        if notifier is None or not notifier.push_available:
            return web.json_response({"available": False, "public_key": None})
        keys = await notifier.vapid_keys()
        return web.json_response({"available": True, "public_key": keys.public_b64})

    async def subscribe(request: web.Request) -> web.Response:
        user = await require_user(request)
        repo: Repo = request.app["mini_repo"]
        body = await _body(request)
        endpoint = str(body.get("endpoint") or "")
        keys = body.get("keys") if isinstance(body.get("keys"), dict) else {}
        p256dh, auth = str(keys.get("p256dh") or ""), str(keys.get("auth") or "")
        if len(endpoint) > MAX_ENDPOINT_LENGTH or not is_push_service(endpoint):
            raise web.HTTPBadRequest(text="bad endpoint")
        if not p256dh or not auth:
            raise web.HTTPBadRequest(text="bad keys")
        await repo.save_push_subscription(
            user.person_id, endpoint, p256dh, auth, request.headers.get("User-Agent")
        )
        return web.json_response({"ok": True})

    async def unsubscribe(request: web.Request) -> web.Response:
        user = await require_user(request)
        repo: Repo = request.app["mini_repo"]
        body = await _body(request)
        await repo.delete_push_subscription(str(body.get("endpoint") or ""), user.person_id)
        return web.json_response({"ok": True})

    app.router.add_get("/api/mini/notifications", listing)
    app.router.add_post("/api/mini/notifications/read", mark_read)
    app.router.add_get("/api/mini/push/key", push_key)
    app.router.add_post("/api/mini/push/subscription", subscribe)
    app.router.add_delete("/api/mini/push/subscription", unsubscribe)
