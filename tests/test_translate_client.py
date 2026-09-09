"""services/translate/client.py::check_alive — found live (2026-09-09): the
original httpx.Timeout(connect=..., read=...) call set only two of the four
fields httpx requires (either a default or all of connect/read/write/pool),
so every single call raised ValueError before a request was even attempted —
set_key() never got far enough to save a key at all. These tests exist so
that regression can't come back silently."""

from __future__ import annotations

import json

import httpx

from bot.services.translate import client as translate_client
from bot.services.translate.client import check_alive, translate_descriptions


class _FakeResponse:
    def __init__(self, status_code: int, body: object = None) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> object:
        return self._body


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient — real network calls are forbidden in
    tests, same rule every other platform client here already follows."""

    def __init__(
        self, status_code: int, *, post_body: object = None, post_status: int | None = None
    ) -> None:
        self._status_code = status_code
        self._post_body = post_body
        self._post_status = post_status if post_status is not None else status_code

    def __call__(self, *, timeout: httpx.Timeout) -> _FakeAsyncClient:
        # httpx.Timeout's own constructor is the thing that used to raise —
        # exercising it for real here (not a mock) is the actual regression
        # check, everything below just confirms check_alive still behaves.
        assert timeout.connect is not None
        assert timeout.read is not None
        assert timeout.write is not None
        assert timeout.pool is not None
        return self

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get(self, url: str, headers: dict[str, str]) -> _FakeResponse:
        return _FakeResponse(self._status_code)

    async def post(self, url: str, headers: dict[str, str], json: object) -> _FakeResponse:
        return _FakeResponse(self._post_status, self._post_body)


async def test_check_alive_does_not_raise_constructing_the_timeout(monkeypatch) -> None:
    """The exact regression: httpx.Timeout(connect=..., read=...) alone
    raises ValueError. A real key/network isn't needed to catch this — the
    crash happened before any request was sent."""
    monkeypatch.setattr(translate_client.httpx, "AsyncClient", _FakeAsyncClient(200))
    assert await check_alive("fake-key") is True


async def test_check_alive_false_on_401(monkeypatch) -> None:
    monkeypatch.setattr(translate_client.httpx, "AsyncClient", _FakeAsyncClient(401))
    assert await check_alive("bad-key") is False


async def test_check_alive_true_on_unrelated_server_error(monkeypatch) -> None:
    """A 5xx or similar isn't evidence the key itself is bad — same
    "don't punish a transient failure" reasoning Steam/PSN's own
    check_alive already follow."""
    monkeypatch.setattr(translate_client.httpx, "AsyncClient", _FakeAsyncClient(503))
    assert await check_alive("fake-key") is True


def _messages_response(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


async def test_translate_descriptions_empty_input_makes_no_call(monkeypatch) -> None:
    def _boom(**kwargs: object) -> None:
        raise AssertionError("should never construct a client for an empty batch")

    monkeypatch.setattr(translate_client.httpx, "AsyncClient", _boom)
    assert await translate_descriptions("key", {}, target_language="ru") == {}


async def test_translate_descriptions_maps_translations_back_by_id(monkeypatch) -> None:
    body = _messages_response(json.dumps(["Победи в игре", "Собери 100 монет"]))
    monkeypatch.setattr(
        translate_client.httpx, "AsyncClient", _FakeAsyncClient(200, post_body=body)
    )

    result = await translate_descriptions(
        "key",
        {"WIN": "Win the game", "COINS": "Collect 100 coins"},
        target_language="ru",
    )

    assert result == {"WIN": "Победи в игре", "COINS": "Собери 100 монет"}


async def test_translate_descriptions_returns_empty_on_non_200(monkeypatch) -> None:
    monkeypatch.setattr(
        translate_client.httpx, "AsyncClient", _FakeAsyncClient(200, post_status=429)
    )
    assert await translate_descriptions("key", {"A": "text"}, target_language="ru") == {}


async def test_translate_descriptions_returns_empty_on_malformed_json(monkeypatch) -> None:
    """The model didn't reply with clean JSON — degrade to "nothing
    translated", never raise (same "expected external failure" shape
    every platform client here already follows)."""
    body = _messages_response("not json at all")
    monkeypatch.setattr(
        translate_client.httpx, "AsyncClient", _FakeAsyncClient(200, post_body=body)
    )
    assert await translate_descriptions("key", {"A": "text"}, target_language="ru") == {}


async def test_translate_descriptions_returns_empty_when_reply_is_not_a_list(monkeypatch) -> None:
    body = _messages_response(json.dumps({"A": "oops, an object not an array"}))
    monkeypatch.setattr(
        translate_client.httpx, "AsyncClient", _FakeAsyncClient(200, post_body=body)
    )
    assert await translate_descriptions("key", {"A": "text"}, target_language="ru") == {}


async def test_translate_descriptions_handles_a_markdown_fenced_reply(monkeypatch) -> None:
    """Found live (2026-09-09): Haiku wrapped its array in a ```json ... ```
    fence despite being asked for ONLY the array — a real response, not a
    hypothetical edge case."""
    fenced = "```json\n" + json.dumps(["Победи в игре"]) + "\n```"
    body = _messages_response(fenced)
    monkeypatch.setattr(
        translate_client.httpx, "AsyncClient", _FakeAsyncClient(200, post_body=body)
    )

    result = await translate_descriptions("key", {"WIN": "Win the game"}, target_language="ru")

    assert result == {"WIN": "Победи в игре"}
