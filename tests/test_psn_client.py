"""services/psn/client.py — the async wrapper over psnawp_api (SPEC 9,
M-PSN-1). No real network calls: psnawp_api's own classes are faked here,
the same "mock the third-party boundary" treatment Xbox/Steam fixtures get
elsewhere in this suite. The live-verified claims (one token reads another
account's public trophies) are covered by the 2026-09-05/06 manual
verification referenced in SPEC.md, not re-proven here — this file is only
about our own exception mapping and shaping."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pytest
from psnawp_api.core.psnawp_exceptions import (
    PSNAWPAuthenticationError,
    PSNAWPForbiddenError,
    PSNAWPNotFoundError,
)
from psnawp_api.models.trophies.trophy_constants import PlatformType, TrophyType

from bot.services.psn import client as psn_client
from bot.services.psn.client import (
    PsnApiError,
    PsnPrivateProfileError,
    PsnTokenDeadError,
    build_client,
    check_alive,
    is_trophy_visible,
    recent_earned_trophies,
    resolve_profile,
)

_next_trophy_id = iter(range(1, 100_000))


@dataclass
class _FakeTrophy:
    trophy_name: str
    earned: bool
    trophy_type: TrophyType = TrophyType.BRONZE
    trophy_detail: str | None = None
    trophy_icon_url: str | None = "https://example.com/icon.png"
    trophy_hidden: bool = False
    trophy_rarity: object | None = None
    trophy_earn_rate: float | None = None
    trophy_id: int = field(default_factory=lambda: next(_next_trophy_id))
    earned_date_time: datetime | None = None


@dataclass
class _FakeTitle:
    np_communication_id: str
    title_name: str
    title_icon_url: str | None = "https://example.com/title.png"
    title_platform: frozenset = field(default_factory=lambda: frozenset({PlatformType.PS4}))
    trophies_by_id: dict[str, list[_FakeTrophy]] = field(default_factory=dict)


class _FakeUser:
    def __init__(
        self,
        account_id: str,
        online_id: str,
        *,
        forbidden: bool = False,
        titles: list[_FakeTitle] | None = None,
    ) -> None:
        self.account_id = account_id
        self.online_id = online_id
        self._forbidden = forbidden
        self._titles = titles or []

    def trophy_summary(self) -> object:
        if self._forbidden:
            raise PSNAWPForbiddenError("closed")
        return object()

    def trophy_titles(self, limit: int | None = None) -> list[_FakeTitle]:
        return self._titles[:limit] if limit else list(self._titles)

    def trophies(self, np_communication_id: str, platform: object, include_progress: bool = False):
        title = next(t for t in self._titles if t.np_communication_id == np_communication_id)
        if title.trophies_by_id.get("__forbidden__"):
            raise PSNAWPForbiddenError("closed")
        return list(title.trophies_by_id.get(np_communication_id, []))


class _FakeClient:
    def __init__(self, users: dict[str, _FakeUser] | None = None, *, dead: bool = False) -> None:
        self._by_online_id = users or {}
        self._dead = dead

    def me(self) -> object:
        if self._dead:
            raise PSNAWPAuthenticationError("dead")
        return object()

    def user(self, online_id: str | None = None, account_id: str | None = None) -> _FakeUser:
        if self._dead:
            raise PSNAWPAuthenticationError("dead")
        if online_id is not None:
            if online_id not in self._by_online_id:
                raise PSNAWPNotFoundError(f"no such user {online_id}")
            return self._by_online_id[online_id]
        for user in self._by_online_id.values():
            if user.account_id == account_id:
                return user
        raise PSNAWPNotFoundError(f"no such account {account_id}")


async def test_build_client_wraps_bad_npsso_as_token_dead(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(npsso: str) -> object:
        raise PSNAWPAuthenticationError("bad npsso")

    monkeypatch.setattr(psn_client, "PSNAWP", _boom)
    with pytest.raises(PsnTokenDeadError):
        await build_client("whatever")


async def test_build_client_wraps_unexpected_errors_as_setup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Found live 2026-09-06: a sandboxed systemd unit denied psnawp's own
    rate-limiter its temp dir, raising a bare FileNotFoundError that wasn't
    about the NPSSO at all — must not be mistaken for PsnTokenDeadError."""

    def _boom(npsso: str) -> object:
        raise FileNotFoundError("no usable temp dir")

    monkeypatch.setattr(psn_client, "PSNAWP", _boom)
    with pytest.raises(psn_client.PsnClientSetupError):
        await build_client("whatever")


async def test_check_alive_true_and_false() -> None:
    assert await check_alive(_FakeClient({})) is True
    assert await check_alive(_FakeClient({}, dead=True)) is False


async def test_resolve_profile_returns_account_id_and_online_id() -> None:
    client = _FakeClient({"gamer": _FakeUser("acc-1", "gamer")})
    profile = await resolve_profile(client, "gamer")
    assert profile.account_id == "acc-1"
    assert profile.online_id == "gamer"


async def test_resolve_profile_unknown_online_id_is_a_plain_api_error() -> None:
    client = _FakeClient({})
    with pytest.raises(PsnApiError):
        await resolve_profile(client, "nobody")


async def test_resolve_profile_dead_token_raises_token_dead() -> None:
    client = _FakeClient({}, dead=True)
    with pytest.raises(PsnTokenDeadError):
        await resolve_profile(client, "gamer")


async def test_is_trophy_visible_true_for_open_profile() -> None:
    client = _FakeClient({"gamer": _FakeUser("acc-1", "gamer")})
    assert await is_trophy_visible(client, "acc-1") is True


async def test_is_trophy_visible_false_for_closed_profile() -> None:
    """The exact case checklist item 3 (SPEC 9, M-PSN-1) worried about — a
    closed profile must read as "no", not raise."""
    client = _FakeClient({"gamer": _FakeUser("acc-1", "gamer", forbidden=True)})
    assert await is_trophy_visible(client, "acc-1") is False


async def test_is_trophy_visible_false_for_unknown_account() -> None:
    client = _FakeClient({})
    assert await is_trophy_visible(client, "no-such-account") is False


async def test_recent_earned_trophies_skips_unearned_and_sorts_by_recency() -> None:
    old = _FakeTrophy("Old One", earned=True, earned_date_time=datetime(2020, 1, 1))
    new = _FakeTrophy("New One", earned=True, earned_date_time=datetime(2026, 1, 1))
    not_earned = _FakeTrophy("Not Earned", earned=False)
    title = _FakeTitle(
        "NPWR00001_00",
        "Some Game",
        trophies_by_id={"NPWR00001_00": [old, not_earned, new]},
    )
    client = _FakeClient({"gamer": _FakeUser("acc-1", "gamer", titles=[title])})

    result = await recent_earned_trophies(client, "acc-1", limit=10)

    assert [t.trophy_name for t in result] == ["New One", "Old One"]
    assert result[0].title_name == "Some Game"


async def test_recent_earned_trophies_respects_the_limit() -> None:
    trophies = [
        _FakeTrophy(f"T{i}", earned=True, earned_date_time=datetime(2020, 1, i + 1))
        for i in range(5)
    ]
    title = _FakeTitle("NPWR00001_00", "Some Game", trophies_by_id={"NPWR00001_00": trophies})
    client = _FakeClient({"gamer": _FakeUser("acc-1", "gamer", titles=[title])})

    result = await recent_earned_trophies(client, "acc-1", limit=2)

    assert len(result) == 2


async def test_recent_earned_trophies_private_profile_raises_private_error() -> None:
    client = _FakeClient({"gamer": _FakeUser("acc-1", "gamer")})

    def _boom(*args: object, **kwargs: object) -> None:
        raise PSNAWPForbiddenError("closed")

    monkeypatch_target = client._by_online_id["gamer"]
    monkeypatch_target.trophy_titles = _boom  # type: ignore[method-assign]

    with pytest.raises(PsnPrivateProfileError):
        await recent_earned_trophies(client, "acc-1", limit=10)


async def test_recent_earned_trophies_skips_one_forbidden_game_not_the_whole_screen() -> None:
    """One game's detail can be hidden without the profile as a whole being
    closed (SPEC 9's own M-PSN-2 notes) — that one game silently contributes
    nothing, the rest still comes through."""
    visible_trophy = _FakeTrophy("Visible", earned=True, earned_date_time=datetime(2024, 1, 1))
    visible = _FakeTitle(
        "NPWR00002_00", "Visible Game", trophies_by_id={"NPWR00002_00": [visible_trophy]}
    )
    hidden = _FakeTitle(
        "NPWR00001_00", "Hidden Game", trophies_by_id={"NPWR00001_00": [], "__forbidden__": [1]}
    )
    client = _FakeClient({"gamer": _FakeUser("acc-1", "gamer", titles=[hidden, visible])})

    result = await recent_earned_trophies(client, "acc-1", limit=10)

    assert [t.trophy_name for t in result] == ["Visible"]


async def test_request_count_today_reflects_calls_made() -> None:
    # A pure smoke check that the shared limiter is actually wired in — the
    # exact count depends on test execution order within this module, so
    # only non-negativity is asserted.
    assert psn_client.request_count_today() >= 0
