"""A titlehub reply read whole (2026-09-19, 2026-10-12).

Some games come back with `detail.developerName: null`. xbox-webapi's model
demanded a string, so a good answer arrived as a `ValidationError` and the
whole of it — name, devices, picture — was lost (76 Xbox games on production
were unnameable this way). `resolve_title` reads titlehub's JSON itself now:
whatever came is kept, a missing field is None, and the `detail` it asked for
(studio, publisher, release day, genres) and the Store product it names are
no longer thrown away.
"""

from __future__ import annotations

import httpx
import pytest

from bot.services.xbox.client import XboxApiError, XboxClient


class _Token:
    xuid = "123"
    authorization_header_value = "XBL3.0 x=1;token"


class _Session:
    def __init__(self, answer: object) -> None:
        self.answer = answer
        self.urls: list[str] = []

    async def get(self, url: str, **_kw: object) -> httpx.Response:
        self.urls.append(url)
        if isinstance(self.answer, Exception):
            raise self.answer
        return httpx.Response(200, json=self.answer, request=httpx.Request("GET", url))


class _Manager:
    def __init__(self, session: _Session) -> None:
        self.xsts_token = _Token()
        self.session = session


class _FakeAuth:
    def __init__(self, session: _Session) -> None:
        self._manager = _Manager(session)

    async def authenticated_manager(self, person_id: int) -> _Manager:
        return self._manager


def _client(answer: object) -> tuple[XboxClient, _Session]:
    session = _Session(answer)
    return XboxClient(_FakeAuth(session)), session  # type: ignore[arg-type]


async def test_a_null_developer_keeps_the_rest_of_the_answer() -> None:
    client, session = _client(
        {
            "titles": [
                {
                    "titleId": "1297287122",
                    "name": "Kameo",
                    "devices": ["Xbox360"],
                    "displayImage": "https://store-images/kameo",
                    "productId": "BV83SM3191S5",
                    "modernTitleId": "992058215",
                    "detail": {
                        "developerName": None,
                        "publisherName": "Microsoft Studios",
                        "releaseDate": "2005-11-16T00:00:00Z",
                        "genres": ["Action & adventure"],
                    },
                }
            ]
        }
    )
    entry = await client.resolve_title(1, "1297287122")
    assert entry is not None
    assert (entry.name, entry.developer, entry.publisher) == ("Kameo", None, "Microsoft Studios")
    assert entry.release_date == "2005-11-16" and entry.genres == ["Action & adventure"]
    assert entry.product_ids == ["BV83SM3191S5"] and entry.modern_title_id == "992058215"
    assert entry.platform == "xbox_360"
    assert session.urls[0].endswith(
        "/decoration/achievement,alternateTitleId,detail,image,scid,productId"
    )


async def test_an_empty_answer_is_an_ordinary_miss() -> None:
    client, _ = _client({"titles": []})
    assert await client.resolve_title(1, "title") is None


async def test_a_real_api_failure_still_raises() -> None:
    client, _ = _client(httpx.RequestError("connection reset"))
    with pytest.raises(XboxApiError):
        await client.resolve_title(1, "title")
