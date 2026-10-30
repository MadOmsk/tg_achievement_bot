"""The Mini App's side of a player's own PSN token (#233): add, refuse,
remove, link by token; /me says the state, never the token."""

from __future__ import annotations

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.constants import Platform
from bot.db.repo import Repo
from bot.services.crypto import TokenCipher
from bot.services.psn import personal
from bot.services.psn.auth import PsnAuth
from bot.services.psn.client import PsnProfile
from bot.services.psn.personal import PsnPersonalAuth
from bot.web import mini_psn_token
from bot.web.mini_auth import MiniAppUser

GOOD = "A" * 64
OTHER = "B" * 64
KEY = "jDzMk1H4D8_uG2bZqv0O1c0JxQb5ZQ0w6m3pX1Yf4kE="


async def _shared_set(self: object) -> str:
    return "active"


@pytest.fixture
def sony(monkeypatch: pytest.MonkeyPatch) -> None:
    accounts = {GOOD: PsnProfile("111", "Me"), OTHER: PsnProfile("222", "Them")}

    async def build_client(npsso: str, **_: object) -> str:
        return npsso

    async def own_profile(client: str) -> PsnProfile:
        return accounts[client]

    monkeypatch.setattr(personal, "build_client", build_client)
    monkeypatch.setattr(personal, "own_profile", own_profile)
    # A shared token is set: linking by a token needs the poller to run.
    monkeypatch.setattr(PsnAuth, "status", _shared_set)


async def _client(repo: Repo, person: int, tg_id: int, monkeypatch) -> TestClient:
    from bot.web import mini_api

    async def require_user(request: web.Request) -> MiniAppUser:
        return MiniAppUser(tg_id, None, None, None, None, False, person_id=person)

    async def no_backfill(*_: object) -> None:
        return None

    monkeypatch.setattr(mini_api, "_require_user", require_user)
    monkeypatch.setattr(mini_api, "_psn_backfill", no_backfill)
    cipher = TokenCipher(KEY)
    psn_auth = PsnAuth(repo, cipher)
    psn_auth.personal = PsnPersonalAuth(repo, cipher)
    app = web.Application()
    app["mini_repo"] = repo
    app["mini_psn_auth"] = psn_auth
    app["mini_psn_fetcher"] = object()
    mini_psn_token.setup(app)
    app.router.add_post("/api/mini/connect/psn", mini_api.handle_connect_psn)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


async def test_add_refuse_and_remove(repo: Repo, sony, monkeypatch) -> None:
    person = await repo.ensure_user(5, None)
    await repo.link_platform_account(person, Platform.PSN, "111", "Me")
    client = await _client(repo, person, 5, monkeypatch)
    try:
        wrong = await client.put("/api/mini/psn/token", json={"account_id": "111", "token": OTHER})
        assert wrong.status == 400
        assert await wrong.json() == {"ok": False, "error": "mismatch", "other": "Them"}
        bad = await client.put("/api/mini/psn/token", json={"account_id": "111", "token": "x"})
        assert (await bad.json())["error"] == "format"
        ok = await client.put("/api/mini/psn/token", json={"account_id": "111", "token": GOOD})
        body = await ok.json()
        assert body == {"ok": True, "online_id": "Me"}
        assert GOOD not in str(body)
        assert (await repo.psn_token("111")) is not None
        gone = await client.delete("/api/mini/psn/token", json={"account_id": "111"})
        assert gone.status == 200
        assert await repo.psn_token("111") is None
    finally:
        await client.close()


async def test_link_by_token(repo: Repo, sony, monkeypatch) -> None:
    person = await repo.ensure_user(6, None)
    client = await _client(repo, person, 6, monkeypatch)
    try:
        res = await client.post("/api/mini/connect/psn-token", json={"token": GOOD})
        assert (await res.json())["online_id"] == "Me"
    finally:
        await client.close()
    [link] = await repo.platform_links_for(person, Platform.PSN)
    assert link.external_id == "111"
    assert (await repo.psn_token("111")).status == "active"  # type: ignore[union-attr]


async def test_a_token_in_the_nickname_field_is_linked_as_a_token(
    repo: Repo, sony, monkeypatch
) -> None:
    from bot.web import mini_api

    async def searched(*_: object) -> None:
        raise AssertionError("a token went to Sony's search")

    monkeypatch.setattr(mini_api, "resolve_profile", searched)
    person = await repo.ensure_user(7, None)
    client = await _client(repo, person, 7, monkeypatch)
    try:
        res = await client.post("/api/mini/connect/psn", json={"online_id": GOOD})
        assert (await res.json())["online_id"] == "Me"
    finally:
        await client.close()
    assert (await repo.psn_token("111")).status == "active"  # type: ignore[union-attr]
