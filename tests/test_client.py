"""Contract selection in the achievements request (SPEC 4, 5.3)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from bot.services.xbox import client as xbox_client_module
from bot.services.xbox.client import XboxApiError, XboxClient

MODERN_PAYLOAD = {
    "achievements": [
        {
            "id": "1",
            "name": "Not started yet",
            "progressState": "NotStarted",
            "rewards": [{"type": "Gamerscore", "value": "10"}],
            "titleAssociations": [{"name": "Modern Game", "id": 111}],
        },
        {
            "id": "2",
            "name": "Done",
            "progressState": "Achieved",
            "progression": {"timeUnlocked": "2026-01-01T00:00:00.0000000Z"},
            "rewards": [{"type": "Gamerscore", "value": "10"}],
            "rarity": {"currentPercentage": 12.5},
            "titleAssociations": [{"name": "Modern Game", "id": 111}],
        },
    ]
}

# Contract 1: what the caller earned, no rarity (the real shape, #121).
X360_PAYLOAD = {
    "achievements": [
        {
            "id": 7,
            "titleId": 222,
            "name": "Old school",
            "gamerscore": 25,
            "unlocked": True,
            "timeUnlocked": "2026-01-01T00:00:00.0000000Z",
            "imageId": 12,
        }
    ]
}

# Contract 3: the whole game with rarity — and every item "unlocked": false,
# because it describes the game, not the caller (verified live, #121).
X360_C3_PAYLOAD = {
    "achievements": [
        {
            "id": 7,
            "titleId": 222,
            "name": "Old school",
            "gamerscore": 25,
            "unlocked": False,
            "timeUnlocked": "2002-11-15T00:00:00.0000000Z",
            "imageId": 12,
            "rarity": {"currentPercentage": 4.5},
            "isSecret": False,
        },
        {
            "id": 8,
            "titleId": 222,
            "name": "Not yet",
            "gamerscore": 10,
            "unlocked": False,
            "timeUnlocked": "2002-11-15T00:00:00.0000000Z",
            "imageId": 13,
            "rarity": {"currentPercentage": 40.0},
            "isSecret": False,
        },
    ]
}


class StubResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.status_code = 200
        self.headers: dict[str, str] = {}

    def json(self) -> dict[str, Any]:
        return self._payload


class StubSession:
    def __init__(self, by_contract: dict[str, dict[str, Any]]) -> None:
        self._by_contract = by_contract
        self.contracts: list[str] = []

    async def get(self, url: str, params=None, headers=None) -> StubResponse:
        contract = (headers or {})["x-xbl-contract-version"]
        self.contracts.append(contract)
        return StubResponse(self._by_contract.get(contract, {"achievements": []}))


class StubXsts:
    xuid = "1"
    authorization_header_value = "XBL3.0 x=1;token"


class StubManager:
    def __init__(self, session: StubSession) -> None:
        self.session = session
        self.xsts_token = StubXsts()


class StubAuth:
    def __init__(self, manager: StubManager) -> None:
        self._manager = manager

    async def authenticated_manager(self, tg_id: int) -> StubManager:
        return self._manager


def _client(session: StubSession) -> XboxClient:
    return XboxClient(StubAuth(StubManager(session)))  # type: ignore[arg-type]


async def test_modern_title_uses_contract_4_only() -> None:
    session = StubSession({"4": MODERN_PAYLOAD})
    parsed = await _client(session).title_achievements(1, "111", "xbox_modern")

    assert session.contracts == ["4"]
    assert [item.achievement_id for item in parsed] == ["2"]
    assert parsed[0].rarity_percent == 12.5


async def test_back_compat_title_uses_contract_3() -> None:
    """Presence reports the console, not the game. A 360 title played on a
    Series X arrives as "xbox_modern" and contract 4 answers with an empty list —
    the client asks the Xbox 360 contracts: what was earned from contract 1,
    its rarity from contract 3 (#121)."""
    session = StubSession({"4": {"achievements": []}, "3": X360_C3_PAYLOAD, "1": X360_PAYLOAD})

    parsed = await _client(session).title_achievements(1, "222", "xbox_modern")

    assert session.contracts == ["4", "3", "1"]
    assert len(parsed) == 1
    assert parsed[0].platform == "xbox_360"
    assert parsed[0].rarity_percent == 4.5
    assert parsed[0].icon_url == "http://image.xboxlive.com/global/t.000000de/ach/0/c"
    assert parsed[0].gamerscore == 25


async def test_back_compat_title_falls_back_to_contract_1() -> None:
    """If both contract 4 and contract 3 yield no achievements, fall back to contract 1."""
    session = StubSession({"4": {"achievements": []}, "1": X360_PAYLOAD})

    parsed = await _client(session).title_achievements(1, "222", "xbox_modern")

    assert session.contracts == ["4", "3", "1"]
    assert len(parsed) == 1
    assert parsed[0].platform == "xbox_360"
    assert parsed[0].rarity_percent is None
    assert parsed[0].gamerscore == 25


async def test_known_x360_console_uses_contract_3() -> None:
    session = StubSession({"3": X360_C3_PAYLOAD, "1": X360_PAYLOAD})
    parsed = await _client(session).title_achievements(1, "222", "xbox_360")

    assert session.contracts == ["3", "1"]
    assert [a.achievement_id for a in parsed] == ["7"]
    assert parsed[0].platform == "xbox_360"
    assert parsed[0].rarity_percent == 4.5


async def test_x360_earned_come_from_contract_1_and_the_total_from_contract_3() -> None:
    """Contract 3 alone kept nothing as earned — every item there reads
    "unlocked": false — so no Xbox 360 unlock was stored or published (#121)."""
    session = StubSession({"3": X360_C3_PAYLOAD, "1": X360_PAYLOAD})

    parsed, total = await _client(session).title_achievements_with_total(1, "222", "xbox_360")

    assert [a.achievement_id for a in parsed] == ["7"]
    assert total == 2  # the whole game, not the one earned


async def test_x360_full_list_comes_from_contract_3_alone() -> None:
    session = StubSession({"3": X360_C3_PAYLOAD})

    parsed = await _client(session).title_achievements(1, "222", "xbox_360", earned_only=False)

    assert session.contracts == ["3"]
    assert [a.achievement_id for a in parsed] == ["7", "8"]


async def test_known_x360_console_falls_back_to_contract_1_and_skips_contract_4() -> None:
    session = StubSession({"1": X360_PAYLOAD})
    parsed = await _client(session).title_achievements(1, "222", "xbox_360")

    assert session.contracts == ["3", "1"]
    assert "4" not in session.contracts
    assert parsed[0].platform == "xbox_360"


async def test_title_rarity_with_name_x360_contract_3() -> None:
    session = StubSession({"4": {"achievements": []}, "3": X360_C3_PAYLOAD})
    rarity, name = await _client(session).title_rarity_with_name(1, "222")

    assert session.contracts == ["4", "3"]
    assert rarity == {"7": 4.5, "8": 40.0}  # the whole game, earned or not
    assert name is None


class _HangingTitlehub:
    async def get_title_history(self, xuid: str, max_items: int = 200) -> Any:
        await asyncio.sleep(10)  # far longer than the patched deadline below
        raise AssertionError("should have been cancelled by the deadline first")


class _FakeXboxLiveClientForDeadlineTest:
    def __init__(self, manager: object) -> None:
        self.titlehub = _HangingTitlehub()


async def test_title_history_enforces_a_hard_overall_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Found live (2026-09-09): httpx's own read timeout resets on every
    chunk received, so a response trickling in slowly enough between chunks
    never trips it at all — startup_catch_up's otherwise-sequential loop
    over every Xbox user just stopped advancing, with no exception and no
    timeout, until the process was restarted. asyncio.wait_for is the
    actual hard ceiling; the session's own read timeout only ever catches a
    connection that goes fully silent mid-response."""
    monkeypatch.setattr(xbox_client_module, "XboxLiveClient", _FakeXboxLiveClientForDeadlineTest)
    monkeypatch.setattr(xbox_client_module, "TITLE_HISTORY_DEADLINE_SECONDS", 0.05)
    session = StubSession({})
    client = _client(session)

    with pytest.raises(XboxApiError):
        await client.title_history(1)
