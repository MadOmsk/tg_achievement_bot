"""Test Mini App chat settings endpoints."""

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


async def test_patch_chat_without_action_infers_rarity_and_digest(
    repo: Repo, settings: Settings
) -> None:
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)

    bot_token = settings.bot_token.get_secret_value()
    user_id = 42
    chat_id = -100123456789

    await repo.ensure_user(user_id, "testuser")
    await repo.upsert_chat(chat_id, "Test Chat", user_id)
    await repo.subscribe(chat_id, user_id)

    init_data = _signed_init_data(bot_token, user_id)
    headers = {"X-Telegram-Init-Data": init_data}

    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        # Patch rarity_mode without explicit action (#98)
        resp = await client.patch(
            f"/api/mini/chats/{chat_id}",
            json={"rarity_mode": "rare"},
            headers=headers,
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["ok"] is True
        assert data["chat"]["rarity_mode"] == "rare"

        # Patch digest_threshold without explicit action (#98)
        resp = await client.patch(
            f"/api/mini/chats/{chat_id}",
            json={"digest_threshold": 5},
            headers=headers,
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["ok"] is True
        assert data["chat"]["digest_threshold"] == 5
    finally:
        await client.close()
