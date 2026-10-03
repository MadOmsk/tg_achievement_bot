"""Nicknames (#157): what is allowed, how a taken one gets its digits, the
once-a-day change, and the first one made for people who never chose."""

from __future__ import annotations

import pytest

from bot.db.repo import HandleInvalid, HandleTooSoon, Repo
from bot.services import handles


def test_only_latin_letters_and_digits_three_to_twenty() -> None:
    assert handles.is_valid("RideTheSun")
    assert handles.is_valid("abc")
    assert handles.is_valid("a" * 20)
    for bad in ("ab", "a" * 21, "Привет", "with space", "under_score", "ник1", "abc\n", ""):
        assert not handles.is_valid(bad), bad


def test_first_nickname_comes_from_the_first_usable_name() -> None:
    assert handles.from_text(None, "Мад", "mad_omsk", "other") == "madomsk"
    assert handles.from_text("ab", "Иван") == handles.FALLBACK_HANDLE
    assert handles.from_text("x" * 40) == "x" * 20


def test_digits_are_shown_only_when_there_are_some() -> None:
    assert handles.Handle("Bob").display == "Bob"
    assert handles.Handle("Bob", 4821).display == "Bob#4821"


async def test_a_new_person_gets_a_nickname_from_their_username(repo: Repo) -> None:
    await repo.ensure_user(1, "mad_omsk")
    state = await repo.handle_state(1)
    assert state.handle == handles.Handle("madomsk")
    assert not state.confirmed


async def test_a_taken_nickname_gets_four_digits_ignoring_case(repo: Repo) -> None:
    await repo.ensure_user(1, "Bobby")
    await repo.ensure_user(2, "bobby")
    first = (await repo.handle_state(1)).handle
    second = (await repo.handle_state(2)).handle
    assert first.number == 0
    assert 1000 <= second.number <= 9999
    assert second.display.startswith("bobby#")


async def test_digits_drop_when_the_new_nickname_is_free(repo: Repo) -> None:
    await repo.ensure_user(1, "Bobby")
    await repo.ensure_user(2, "bobby")
    assert (await repo.handle_state(2)).handle.number != 0
    # The first choice is free and unconfirmed people may pick anything.
    chosen = await repo.change_handle(2, "Unique2")
    assert chosen == handles.Handle("Unique2", 0)


async def test_invalid_nickname_is_refused(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    with pytest.raises(HandleInvalid):
        await repo.change_handle(1, "Иван")


async def test_a_change_waits_a_day_after_the_first_real_one(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    await repo.change_handle(1, "FirstPick")  # first choice: free
    await repo.change_handle(1, "SecondPick")  # first real change: allowed
    with pytest.raises(HandleTooSoon):
        await repo.change_handle(1, "ThirdPick")
    # Only the letters' case may change at any time, keeping the digits.
    again = await repo.change_handle(1, "secondpick")
    assert again.name == "secondpick"


async def test_everybody_without_a_nickname_gets_one_at_startup(repo: Repo) -> None:
    await repo.ensure_user(1, "alpha")
    await repo.ensure_user(2, None)
    await repo._conn.execute(
        "UPDATE users SET handle = NULL, handle_norm = NULL, handle_number = 0"
    )
    await repo._conn.commit()
    assert await repo.give_everyone_a_handle() == 2
    assert (await repo.handle_state(1)).handle.name == "alpha"
    assert (await repo.handle_state(2)).handle.name == handles.FALLBACK_HANDLE
    assert await repo.give_everyone_a_handle() == 0


async def test_mini_api_handle_flow(repo: Repo, settings) -> None:
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    from bot.web.mini_api import cors_middleware, setup_mini_api
    from tests.test_mini_delete import _signed_init_data

    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)
    headers = {"X-Telegram-Init-Data": _signed_init_data(settings.bot_token.get_secret_value(), 42)}
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        me = await (await client.get("/api/mini/me", headers=headers)).json()
        assert me["handle"]["name"] == "test"
        assert me["handle"]["confirmed"] is False

        bad = await client.put("/api/mini/me/handle", json={"handle": "Иван"}, headers=headers)
        assert (bad.status, (await bad.json())["error"]) == (400, "invalid")

        ok = await client.put("/api/mini/me/handle", json={"handle": "RideTheSun"}, headers=headers)
        assert ok.status == 200
        handle = (await ok.json())["handle"]
        assert handle["display"] == "RideTheSun" and handle["confirmed"] is True

        await client.put("/api/mini/me/handle", json={"handle": "Another1"}, headers=headers)
        late = await client.put("/api/mini/me/handle", json={"handle": "Third33"}, headers=headers)
        body = await late.json()
        assert (late.status, body["error"]) == (409, "too_soon")
        assert body["available_at"]
    finally:
        await client.close()
