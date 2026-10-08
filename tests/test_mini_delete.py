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
    assert await repo.get_user(await repo.person_id(user_id)) is not None

    init_data = _signed_init_data(bot_token, user_id)
    headers = {"X-Telegram-Init-Data": init_data}

    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        resp = await client.delete("/api/mini/me", headers=headers)
        assert resp.status == 200
        body = await resp.json()
        assert body == {"ok": True}
        assert await repo.get_user(await repo.person_id(user_id)) is None
    finally:
        await client.close()


async def test_mini_me_post_delete_endpoint(repo: Repo, settings: Settings) -> None:
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)

    bot_token = settings.bot_token.get_secret_value()
    user_id = 43
    await repo.ensure_user(user_id, "testuser2")
    assert await repo.get_user(await repo.person_id(user_id)) is not None

    init_data = _signed_init_data(bot_token, user_id)
    headers = {"X-Telegram-Init-Data": init_data}

    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        resp = await client.post("/api/mini/me/delete", headers=headers)
        assert resp.status == 200
        body = await resp.json()
        assert body == {"ok": True}
        assert await repo.get_user(await repo.person_id(user_id)) is None
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
    target = f"p{await repo.person_id(target_id)}"

    async def step(headers, n: int, who: str = target):
        body = {"scope": "user", "target": who, "action": "delete", "step": n}
        return await client.post("/api/mini/admin/actions", json=body, headers=headers)

    try:
        # 1. Not a super-admin: forbidden, nothing asked
        assert (await step(non_admin_headers, 0)).status == 403
        assert await repo.get_user(await repo.person_id(target_id)) is not None

        # 2. Somebody who is not there: the action is not offered
        gone = await (await step(admin_headers, 0, "p99999")).json()
        assert gone["done"]["ok"] is False

        # 3. Two confirmations, the bot's own words, then deleted
        first = await (await step(admin_headers, 0)).json()
        assert first["confirm"]["step"] == 1 and "target" in first["confirm"]["text"]
        second = await (await step(admin_headers, 1)).json()
        assert second["confirm"]["step"] == 2
        assert await repo.get_user(await repo.person_id(target_id)) is not None  # not yet
        done = await (await step(admin_headers, 2)).json()
        assert done["done"] == {"ok": True, "text": "Пользователь удалён", "gone": True}
        assert await repo.person_id(target_id) is None
    finally:
        await client.close()
