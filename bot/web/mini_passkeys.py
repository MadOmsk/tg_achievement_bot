"""Passkeys in the Mini App (owner, 2026-10-08): Settings → «Вход» adds and
removes them; the sign-in screen asks for one in place of an email's code.

- `GET /api/mini/me/passkeys` — one's keys, and whether keys work here at all.
- `POST /api/mini/me/passkeys/options` → what the browser needs to make one.
- `POST /api/mini/me/passkeys` `{token, credential}` — keep the new key.
- `DELETE /api/mini/me/passkeys/{id}`.
- `POST /api/mini/auth/passkey/verify` `{token, credential}` → a session.

A sign-in asks for the key from `/auth/email/start` itself (`mini_logins`):
an address with a key gets the key's options there, and no mail goes out.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web

from bot.db.repo import PasskeyRow, Repo
from bot.services.passkeys import PasskeyError, Passkeys, device_name
from bot.web.mini_auth import MiniAppUser
from bot.web.mini_session import start_session

log = logging.getLogger(__name__)

RequireUser = Callable[[web.Request], Awaitable[MiniAppUser]]


def _error(code: str, status: int) -> web.Response:
    return web.json_response({"error": code}, status=status)


async def _body(request: web.Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as exc:
        raise web.HTTPBadRequest(text="invalid json") from exc
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(text="invalid json")
    return body


def _key_json(key: PasskeyRow) -> dict[str, Any]:
    return {
        "id": key.id,
        "name": key.name,
        "created_at": key.created_at,
        "last_used_at": key.last_used_at,
    }


async def _list(repo: Repo, passkeys: Passkeys | None, person_id: int) -> dict[str, Any]:
    return {
        "available": passkeys is not None,
        "keys": [_key_json(key) for key in await repo.passkeys_of(person_id)],
    }


def register(app: web.Application, require_user: RequireUser) -> None:
    def keys_of(request: web.Request) -> Passkeys | None:
        return request.app.get("mini_passkeys")

    async def listed(request: web.Request) -> web.Response:
        user = await require_user(request)
        repo: Repo = request.app["mini_repo"]
        return web.json_response(await _list(repo, keys_of(request), user.person_id))

    async def new_options(request: web.Request) -> web.Response:
        user = await require_user(request)
        passkeys = keys_of(request)
        if passkeys is None:
            return _error("unavailable", 503)
        repo: Repo = request.app["mini_repo"]
        person = await repo.get_user(user.person_id)
        # What the phone shows under the key: the nickname, else the address.
        name = (person.handle if person else None) or (person.email if person else None)
        existing = await repo.passkeys_of(user.person_id)
        label = name or f"id{user.person_id}"
        return web.json_response(passkeys.registration_options(user.person_id, label, existing))

    async def add(request: web.Request) -> web.Response:
        user = await require_user(request)
        passkeys = keys_of(request)
        if passkeys is None:
            return _error("unavailable", 503)
        repo: Repo = request.app["mini_repo"]
        body = await _body(request)
        try:
            key = passkeys.finish_registration(
                body.get("token"), user.person_id, body.get("credential")
            )
        except PasskeyError as exc:
            return _error(str(exc), 400)
        try:
            await repo.add_passkey(
                user.person_id,
                key.id,
                key.public_key,
                key.sign_count,
                key.transports,
                device_name(request.headers.get("User-Agent")),
            )
        except sqlite3.IntegrityError:
            return _error("taken", 409)
        log.info("person_id=%s added a passkey", user.person_id)
        return web.json_response(await _list(repo, passkeys, user.person_id))

    async def remove(request: web.Request) -> web.Response:
        user = await require_user(request)
        repo: Repo = request.app["mini_repo"]
        if not await repo.delete_passkey(user.person_id, request.match_info["key_id"]):
            return _error("not_found", 404)
        return web.json_response(await _list(repo, keys_of(request), user.person_id))

    async def sign_in(request: web.Request) -> web.Response:
        passkeys = keys_of(request)
        if passkeys is None:
            return _error("unavailable", 503)
        repo: Repo = request.app["mini_repo"]
        body = await _body(request)
        credential = body.get("credential")
        key_id = passkeys.credential_id(credential)
        key = await repo.passkey(key_id) if key_id else None
        if key is None:
            # A key this app does not know (deleted here, kept on the phone).
            return _error("unknown_key", 400)
        try:
            count = passkeys.finish_sign_in(body.get("token"), credential, key)
        except PasskeyError as exc:
            return _error(str(exc), 400)
        await repo.passkey_used(key.id, count)
        return await start_session(request, repo, key.person_id)

    app.router.add_get("/api/mini/me/passkeys", listed)
    app.router.add_post("/api/mini/me/passkeys/options", new_options)
    app.router.add_post("/api/mini/me/passkeys", add)
    app.router.add_delete("/api/mini/me/passkeys/{key_id}", remove)
    app.router.add_post("/api/mini/auth/passkey/verify", sign_in)
