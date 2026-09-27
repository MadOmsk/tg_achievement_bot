"""The game page can show another club member's progress (`?tg_id=`), but only
someone who shares a chat with the caller."""

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
    pairs = {"auth_date": str(int(time.time())), "user": user}
    data_check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


async def test_game_details_for_another_member(repo: Repo, settings: Settings) -> None:
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)
    bot_token = settings.bot_token.get_secret_value()

    me, friend, stranger = 42, 43, 44
    chat_id = -100123456789
    for tg_id, name in ((me, "me"), (friend, "friend"), (stranger, "stranger")):
        await repo.ensure_user(tg_id, name)
    await repo.upsert_chat(chat_id, "Club", me)
    await repo.subscribe(chat_id, me)
    await repo.subscribe(chat_id, friend)

    headers = {"X-Telegram-Init-Data": _signed_init_data(bot_token, me)}
    url = "/api/mini/games/steam/12345"

    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        # Someone in the caller's chat: fine.
        resp = await client.get(url, params={"tg_id": friend}, headers=headers)
        assert resp.status == 200
        assert (await resp.json())["ok"] is True

        # A member of no shared chat: refused.
        resp = await client.get(url, params={"tg_id": stranger}, headers=headers)
        assert resp.status == 403

        # Nobody by that id, and a malformed one.
        resp = await client.get(url, params={"tg_id": 999}, headers=headers)
        assert resp.status == 404
        resp = await client.get(url, params={"tg_id": "abc"}, headers=headers)
        assert resp.status == 400
    finally:
        await client.close()
