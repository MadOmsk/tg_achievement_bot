"""Mini App account deletion endpoints.

Covers DELETE /api/mini/me and DELETE /api/mini/admin/users/{tg_id}.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.config import Settings
from bot.db.repo import Repo
from bot.web.mini_api import cors_middleware, setup_mini_api


def _signed_init_data(bot_token: str, user_id: int) -> str:
    user = json.dumps(
        {"id": user_id, "first_name": "Test", "username": "test"},
        separators=(",", ":"),
    )
    pairs = {
        "auth_date": str(int(time.time())),
        "user": user,
    }
    data_check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


async def test_mini_me_delete_removes_account(repo: Repo, settings: Settings) -> None:
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)

    bot_token = settings.bot_token.get_secret_value()
    user_id = 42
    await repo.ensure_user(user_id, "testuser")
    assert await repo.get_user(user_id) is not None

    init_data = _signed_init_data(bot_token, user_id)
    headers = {"X-Telegram-Init-Data": init_data}

    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        resp = await client.delete("/api/mini/me", headers=headers)
        assert resp.status == 200
        body = await resp.json()
        assert body == {"ok": True}
        assert await repo.get_user(user_id) is None
    finally:
        await client.close()


async def test_mini_me_post_delete_endpoint(repo: Repo, settings: Settings) -> None:
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)

    bot_token = settings.bot_token.get_secret_value()
    user_id = 43
    await repo.ensure_user(user_id, "testuser2")
    assert await repo.get_user(user_id) is not None

    init_data = _signed_init_data(bot_token, user_id)
    headers = {"X-Telegram-Init-Data": init_data}

    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        resp = await client.post("/api/mini/me/delete", headers=headers)
        assert resp.status == 200
        body = await resp.json()
        assert body == {"ok": True}
        assert await repo.get_user(user_id) is None
    finally:
        await client.close()


async def test_mini_admin_delete_user(repo: Repo, settings: Settings) -> None:
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)

    bot_token = settings.bot_token.get_secret_value()
    admin_id = 1
    target_id = 99
    non_admin_id = 50

    await repo.ensure_user(admin_id, "admin")
    await repo.ensure_user(target_id, "target")
    await repo.ensure_user(non_admin_id, "regular")

    admin_headers = {"X-Telegram-Init-Data": _signed_init_data(bot_token, admin_id)}
    non_admin_headers = {"X-Telegram-Init-Data": _signed_init_data(bot_token, non_admin_id)}

    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        # 1. Non-admin forbidden
        resp_forbidden = await client.delete(
            f"/api/mini/admin/users/{target_id}", headers=non_admin_headers
        )
        assert resp_forbidden.status == 403
        assert await repo.get_user(target_id) is not None

        # 2. Admin deletes non-existent -> 404
        resp_not_found = await client.delete("/api/mini/admin/users/99999", headers=admin_headers)
        assert resp_not_found.status == 404

        # 3. Admin deletes target user -> 200 ok
        resp_ok = await client.delete(f"/api/mini/admin/users/{target_id}", headers=admin_headers)
        assert resp_ok.status == 200
        assert await resp_ok.json() == {"ok": True}
        assert await repo.get_user(target_id) is None
    finally:
        await client.close()
