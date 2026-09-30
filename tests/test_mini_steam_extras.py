"""The game page's tips and patches come from the database; a game not filled
yet is filled on the visit, a filled one costs no request to Steam."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.config import Settings
from bot.db.repo import Repo, TitleAchievementRow
from bot.services import steam_extras as se
from bot.services.steam.auth import SteamAuth
from bot.services.steam_guides import GuideSet, make_guide
from bot.services.steam_news import Patch
from bot.web.mini_api import cors_middleware, setup_mini_api

TITLE = "1924130173"


def _init_data(bot_token: str, user_id: int) -> str:
    user = json.dumps({"id": user_id, "first_name": "T", "username": "t"}, separators=(",", ":"))
    pairs = {"auth_date": str(int(time.time())), "user": user}
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


async def test_tips_and_patches_are_filled_once_and_then_read_from_the_database(
    repo: Repo, settings: Settings, steam_auth: SteamAuth, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"appid": 0, "patches": 0, "guides": 0}

    async def find_appid(names, hltb_id):
        calls["appid"] += 1
        return 983970

    async def fetch_patches(appid):
        calls["patches"] += 1
        return [Patch(gid="p1", title="Small patch", date="2022-03-08", text="Fixes.")]

    async def guides_of(appid, api_key):
        calls["guides"] += 1
        lines = ["Intro"] * 8 + [
            "Hidden Room",
            "Behind the bookcase on the second floor; push it twice to open the passage.",
        ]
        return GuideSet([make_guide("g1", "Guide", lines)], True)

    monkeypatch.setattr(se, "find_appid", find_appid)
    monkeypatch.setattr(se, "fetch_patches", fetch_patches)
    monkeypatch.setattr(se, "guides_of", guides_of)

    await repo.ensure_user(42, "me")
    await repo.upsert_title(TITLE, "Haven", "xbox_modern")
    await repo.upsert_title_achievements(
        [
            TitleAchievementRow(
                platform="xbox_modern", title_id=TITLE, achievement_id="2", name_en="Hidden Room"
            )
        ],
        complete=True,
    )

    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo, steam_auth=steam_auth)
    headers = {"X-Telegram-Init-Data": _init_data(settings.bot_token.get_secret_value(), 42)}
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        for _ in range(2):
            resp = await client.get(f"/api/mini/games/xbox_modern/{TITLE}/guides", headers=headers)
            body = await resp.json()
            assert body["complete"] is True
            assert body["tips"]["2"]["text"].startswith("Behind the bookcase")

            resp = await client.get(f"/api/mini/games/xbox_modern/{TITLE}/patches", headers=headers)
            body = await resp.json()
            assert [p["title"] for p in body["patches"]] == ["Small patch"]
        assert calls == {"appid": 1, "patches": 1, "guides": 1}
    finally:
        await client.close()
