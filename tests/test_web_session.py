"""Browser sign-in through Telegram Login and the session cookie (#157)."""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.db.repo import Repo
from bot.web.mini_api import cors_middleware, setup_mini_api
from bot.web.mini_auth import InitDataError, validate_login_widget


def _widget(token: str, tg_id: int = 42, age: int = 5, **extra: str) -> dict[str, str]:
    fields = {
        "id": str(tg_id),
        "first_name": "Test",
        "username": "tester",
        "auth_date": str(int(time.time()) - age),
        **extra,
    }
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hashlib.sha256(token.encode()).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return fields


def test_the_login_widget_signature_is_checked() -> None:
    user = validate_login_widget(_widget("123:abc"), "123:abc")
    assert (user.tg_id, user.username) == (42, "tester")
    tampered = {**_widget("123:abc"), "id": "43"}
    with pytest.raises(InitDataError):
        validate_login_widget(tampered, "123:abc")
    with pytest.raises(InitDataError):
        validate_login_widget(_widget("123:abc"), "999:other")
    with pytest.raises(InitDataError):
        validate_login_widget(_widget("123:abc", age=3600), "123:abc")
    with pytest.raises(InitDataError):
        validate_login_widget({"id": "1", "auth_date": "1"}, "123:abc")


async def test_sign_in_sets_a_cookie_that_signs_later_requests(repo: Repo, settings) -> None:
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)
    token = settings.bot_token.get_secret_value()
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        # Without anything, the app says who is missing.
        assert (await client.get("/api/mini/me")).status == 401

        bad = await client.post("/api/mini/auth/telegram", json={**_widget(token), "id": "7"})
        assert bad.status == 401

        ok = await client.post("/api/mini/auth/telegram", json=_widget(token))
        assert ok.status == 200
        cookie = ok.cookies["ab_session"]
        assert cookie["httponly"]

        me = await client.get("/api/mini/me")  # the client keeps the cookie
        assert me.status == 200
        assert (await me.json())["tg_id"] == 42

        # A bad Init Data header is not rescued by the cookie.
        assert (
            await client.get("/api/mini/me", headers={"X-Telegram-Init-Data": "x"})
        ).status == 401

        out = await client.post("/api/mini/auth/logout")
        assert out.status == 200
        client.session.cookie_jar.clear()
        assert (await client.get("/api/mini/me")).status == 401
    finally:
        await client.close()


async def test_an_ended_or_unknown_session_signs_nobody_in(repo: Repo, settings) -> None:
    await repo.ensure_user(5, "five")
    person = await repo.person_id(5)
    token = await repo.create_session(person, "test")
    assert await repo.session_tg_id(token) == 5
    await repo.end_session(token)
    assert await repo.session_tg_id(token) is None
    assert await repo.session_tg_id("not-a-token") is None
