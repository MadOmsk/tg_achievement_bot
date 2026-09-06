"""poller/service_health.py — periodic liveness check for the two shared
service credentials (SPEC 9, M-PSN-1's "мониторинг живости" paragraph,
applied to Steam too)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import SecretStr

from bot.config import Settings
from bot.db.repo import Repo
from bot.poller import service_health as service_health_module
from bot.poller.service_health import (
    STATUS_ACTIVE,
    STATUS_INVALID,
    STEAM_CHECKED_AT_KEY,
    STEAM_STATUS_KEY,
    ServiceHealth,
)
from bot.services.crypto import TokenCipher
from bot.services.notify import AdminNotifier
from bot.services.psn.auth import CHECKED_AT_KEY as PSN_CHECKED_AT_KEY
from bot.services.psn.auth import PsnAuth
from bot.util import utcnow


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> None:
        self.sent.append((chat_id, text))


def _steam_settings(settings: Settings, *, configured: bool = True) -> Settings:
    return settings.model_copy(
        update={"steam_api_key": SecretStr("fake-key") if configured else None}
    )


async def test_steam_never_configured_is_skipped_entirely(
    repo: Repo, settings: Settings, cipher: TokenCipher
) -> None:
    unconfigured = _steam_settings(settings, configured=False)
    notifier = AdminNotifier(FakeBot(), repo, [1])  # type: ignore[arg-type]
    health = ServiceHealth(unconfigured, repo, PsnAuth(repo, cipher), notifier)

    await health.tick()

    assert await repo.get_app_setting(STEAM_STATUS_KEY) is None


async def test_steam_transition_to_dead_notifies_once(
    repo: Repo, settings: Settings, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = _steam_settings(settings, configured=True)
    bot = FakeBot()
    notifier = AdminNotifier(bot, repo, [1])  # type: ignore[arg-type]
    health = ServiceHealth(configured, repo, PsnAuth(repo, cipher), notifier)

    async def _dead(api_key: str) -> bool:
        return False

    monkeypatch.setattr(service_health_module, "steam_check_alive", _dead)

    await health.tick()

    assert await repo.get_app_setting(STEAM_STATUS_KEY) == STATUS_INVALID
    assert await repo.get_app_setting(STEAM_CHECKED_AT_KEY) is not None
    assert len(bot.sent) == 1
    assert "Steam" in bot.sent[0][1]

    # Second tick, still dead — must not notify again (SPEC 9's own "at most
    # once per transition" rule, same as PsnAuth.check_health).
    await health.tick()
    assert len(bot.sent) == 1


async def test_steam_recovers_silently(
    repo: Repo, settings: Settings, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = _steam_settings(settings, configured=True)
    bot = FakeBot()
    notifier = AdminNotifier(bot, repo, [1])  # type: ignore[arg-type]
    health = ServiceHealth(configured, repo, PsnAuth(repo, cipher), notifier)
    await repo.set_app_setting(STEAM_STATUS_KEY, STATUS_INVALID)

    async def _alive(api_key: str) -> bool:
        return True

    monkeypatch.setattr(service_health_module, "steam_check_alive", _alive)

    await health.tick()

    assert await repo.get_app_setting(STEAM_STATUS_KEY) == STATUS_ACTIVE
    assert bot.sent == []


async def test_steam_check_is_skipped_before_the_interval_elapses(
    repo: Repo, settings: Settings, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Follow-up 2026-09-06: this now runs on the 60s tick, gated by
    KEY_CHECK_INTERVAL_KEY internally — a second tick right after the first
    must not re-check at all, not just avoid a duplicate notify."""
    configured = _steam_settings(settings, configured=True)
    notifier = AdminNotifier(FakeBot(), repo, [1])  # type: ignore[arg-type]
    health = ServiceHealth(configured, repo, PsnAuth(repo, cipher), notifier)
    calls = 0

    async def _counting(api_key: str) -> bool:
        nonlocal calls
        calls += 1
        return True

    monkeypatch.setattr(service_health_module, "steam_check_alive", _counting)

    await health.tick()
    await health.tick()

    assert calls == 1


async def test_psn_check_is_skipped_before_the_interval_elapses(
    repo: Repo, settings: Settings, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unlike the PSN test above, this lets PsnAuth's *real* check_health run
    (mocking only the network boundary, check_alive) so checked_at actually
    gets written — otherwise a mocked-out check_health would never update
    it, and every tick would look equally "never checked" forever."""
    unconfigured = _steam_settings(settings, configured=False)
    psn_auth = PsnAuth(repo, cipher)

    async def _build(npsso: str) -> object:
        return object()

    monkeypatch.setattr("bot.services.psn.auth.build_client", _build)
    await psn_auth.set_npsso("fake-npsso", admin_id=1)
    # set_npsso itself just checked (and stamped checked_at) — backdate it so
    # the first tick below is the one that's actually due, same as a real
    # bot that set this up half an hour ago.
    stale = (utcnow() - timedelta(minutes=40)).isoformat(timespec="seconds")
    await repo.set_app_setting(PSN_CHECKED_AT_KEY, stale)

    calls = 0

    async def _counting_check_alive(client: object) -> bool:
        nonlocal calls
        calls += 1
        return True

    monkeypatch.setattr("bot.services.psn.auth.check_alive", _counting_check_alive)
    notifier = AdminNotifier(FakeBot(), repo, [1])  # type: ignore[arg-type]
    health = ServiceHealth(unconfigured, repo, psn_auth, notifier)

    await health.tick()
    await health.tick()

    assert calls == 1


async def test_tick_also_runs_the_psn_health_check(
    repo: Repo, settings: Settings, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PSN's own check lives in PsnAuth — this just confirms the job
    actually calls it every tick, not just Steam's."""
    unconfigured = _steam_settings(settings, configured=False)
    psn_auth = PsnAuth(repo, cipher)
    calls = 0

    async def _check_health() -> bool:
        nonlocal calls
        calls += 1
        return True

    monkeypatch.setattr(psn_auth, "check_health", _check_health)
    notifier = AdminNotifier(FakeBot(), repo, [1])  # type: ignore[arg-type]
    health = ServiceHealth(unconfigured, repo, psn_auth, notifier)

    await health.tick()

    assert calls == 1
