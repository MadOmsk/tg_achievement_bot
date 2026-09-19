"""A titlehub reply xbox-webapi refuses to parse (2026-09-19).

Some games come back with `detail.developerName: null`, and the library's
model demands a string — so a perfectly good answer arrives as a pydantic
`ValidationError`. It is not an `XboxApiError`, which is the only thing
`Fetcher.ensure_title_name` catches, and `poll_title` calls that *after*
storing the new rows and *before* publishing them. So the achievements were
stored and never announced: #82's shape, arriving by another road.

Found by a one-off backfill that died on its first title; 76 Xbox games on
production had been unnameable this way all along.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from bot.services.xbox import client as client_module
from bot.services.xbox.client import XboxApiError, XboxClient


class _Model(BaseModel):
    name: str


def _a_real_validation_error() -> ValidationError:
    try:
        _Model(name=None)  # type: ignore[arg-type]
    except ValidationError as exc:
        return exc
    raise AssertionError("pydantic accepted None")  # pragma: no cover


class _FakeAuth:
    async def authenticated_manager(self, tg_id: int):
        return object()


def _xbox_client_raising(monkeypatch, error: Exception) -> XboxClient:
    class _Titlehub:
        async def get_title_info(self, title_id: str, *args, **kwargs):
            raise error

    class _Live:
        def __init__(self, manager) -> None:
            self.titlehub = _Titlehub()

    monkeypatch.setattr(client_module, "XboxLiveClient", _Live)
    return XboxClient(_FakeAuth())  # type: ignore[arg-type]


async def test_a_reply_the_library_cannot_parse_is_an_ordinary_miss(monkeypatch) -> None:
    client = _xbox_client_raising(monkeypatch, _a_real_validation_error())

    assert await client.resolve_title(1, "title-with-null-developer") is None


async def test_a_real_api_failure_still_raises(monkeypatch) -> None:
    """The point is to stop swallowing one specific shape, not every shape:
    a genuine request failure must still reach the caller."""
    import httpx

    client = _xbox_client_raising(monkeypatch, httpx.RequestError("connection reset"))

    with pytest.raises(XboxApiError):
        await client.resolve_title(1, "title")
