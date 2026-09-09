"""services/translate/client.py::check_alive — found live (2026-09-09): the
original httpx.Timeout(connect=..., read=...) call set only two of the four
fields httpx requires (either a default or all of connect/read/write/pool),
so every single call raised ValueError before a request was even attempted —
set_key() never got far enough to save a key at all. These tests exist so
that regression can't come back silently."""

from __future__ import annotations

import httpx

from bot.services.translate import client as translate_client
from bot.services.translate.client import check_alive


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient — real network calls are forbidden in
    tests, same rule every other platform client here already follows."""

    def __init__(self, status_code: int) -> None:
        self._status_code = status_code

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
