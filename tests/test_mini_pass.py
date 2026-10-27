"""The season pass is judged by the server (owner, 2026-10-27): a theme is
claimed only with the month's points."""

from __future__ import annotations

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.config import Settings
from bot.db.repo import Repo
from bot.web.mini_api import cors_middleware, setup_mini_api
from tests.test_mini_game_person import _signed_init_data


async def test_claim_needs_the_points(repo: Repo, settings: Settings, monkeypatch) -> None:
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)
    me = 42
    await repo.ensure_user(me, "me")
    person = await repo.person_id(me)
    headers = {"X-Telegram-Init-Data": _signed_init_data(settings.bot_token.get_secret_value(), me)}
    points = {"n": 0}

    async def fake_points(person_id, since, until=None):
        return points["n"]

    monkeypatch.setattr(repo, "points_for_person", fake_points)

    client = TestClient(TestServer(app))
    await client.start_server()

    def claim(palette: str):
        return client.post("/api/mini/pass/claim", json={"palette": palette}, headers=headers)

    try:
        resp = await client.get("/api/mini/pass", headers=headers)
        state = await resp.json()
        assert [t["claimed"] for t in state["tiers"]] == [False] * len(state["tiers"])

        resp = await claim("graphite")
        assert resp.status == 403
        assert await repo.pass_claims(person) == set()

        points["n"] = 160
        resp = await claim("graphite")
        assert resp.status == 200
        assert await repo.pass_claims(person) == {"graphite"}

        # Not the next level's theme, nor one that is no reward.
        resp = await claim("rose")
        assert resp.status == 403
        resp = await claim("violet")
        assert resp.status == 400
    finally:
        await client.close()
