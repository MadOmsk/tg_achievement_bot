"""poller/service_health.py — decides *when* to run the two shared-
credential liveness checks; the checks themselves live in
PsnAuth.check_health / SteamAuth.check_health (SPEC 9, M-PSN-1's
"мониторинг живости" paragraph, applied to Steam too, #17)."""

from __future__ import annotations

from datetime import timedelta

from bot.constants import Platform
from bot.db.repo import Repo
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
from bot.services.steam import auth as steam_auth_module
from bot.services.steam.auth import SteamAuth
from bot.services.translate import auth as anthropic_auth_module
from bot.services.translate.auth import AnthropicAuth
from bot.util import utcnow


def _unconfigured_anthropic_auth(repo: Repo, cipher: TokenCipher) -> AnthropicAuth:
    return AnthropicAuth(repo, cipher)


def _wired_anthropic_auth(
    repo: Repo, cipher: TokenCipher, notifier: AdminNotifier, *, configured: bool = True
) -> AnthropicAuth:
    auth = AnthropicAuth(repo, cipher, env_key="fake-key" if configured else None)
    auth.on_dead = notifier.translation_key_dead
    return auth


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> None:
        self.sent.append((chat_id, text))


def _wired_steam_auth(
    repo: Repo, cipher: TokenCipher, notifier: AdminNotifier, *, configured: bool = True
) -> SteamAuth:
    auth = SteamAuth(repo, cipher, env_key="fake-key" if configured else None)
    auth.on_dead = lambda: notifier.service_key_dead(Platform.STEAM)
    return auth


async def test_steam_never_configured_is_skipped_entirely(repo: Repo, cipher: TokenCipher) -> None:
    notifier = AdminNotifier(FakeBot(), repo, [1])  # type: ignore[arg-type]
    steam_auth = _wired_steam_auth(repo, cipher, notifier, configured=False)
    health = ServiceHealth(
        repo, PsnAuth(repo, cipher), steam_auth, _unconfigured_anthropic_auth(repo, cipher)
    )

    await health.tick()

    assert await repo.get_app_setting(STEAM_STATUS_KEY) is None


async def test_steam_transition_to_dead_notifies_once(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    bot = FakeBot()
    notifier = AdminNotifier(bot, repo, [1])  # type: ignore[arg-type]
    steam_auth = _wired_steam_auth(repo, cipher, notifier)
    health = ServiceHealth(
        repo, PsnAuth(repo, cipher), steam_auth, _unconfigured_anthropic_auth(repo, cipher)
    )

    async def _dead(api_key: str) -> bool:
        return False

    monkeypatch.setattr(steam_auth_module, "check_alive", _dead)

    await health.tick()

    assert await repo.get_app_setting(STEAM_STATUS_KEY) == STATUS_INVALID
    assert await repo.get_app_setting(STEAM_CHECKED_AT_KEY) is not None
    assert len(bot.sent) == 1
    assert "Steam" in bot.sent[0][1]

    # Second tick, still dead — must not notify again (SPEC 9's own "at most
    # once per transition" rule, same as PsnAuth.check_health).
    await health.tick()
    assert len(bot.sent) == 1


async def test_steam_recovers_silently(repo: Repo, cipher: TokenCipher, monkeypatch) -> None:
    bot = FakeBot()
    notifier = AdminNotifier(bot, repo, [1])  # type: ignore[arg-type]
    steam_auth = _wired_steam_auth(repo, cipher, notifier)
    health = ServiceHealth(
        repo, PsnAuth(repo, cipher), steam_auth, _unconfigured_anthropic_auth(repo, cipher)
    )
    await repo.set_app_setting(STEAM_STATUS_KEY, STATUS_INVALID)

    async def _alive(api_key: str) -> bool:
        return True

    monkeypatch.setattr(steam_auth_module, "check_alive", _alive)

    await health.tick()

    assert await repo.get_app_setting(STEAM_STATUS_KEY) == STATUS_ACTIVE
    assert bot.sent == []


async def test_steam_check_is_skipped_before_the_interval_elapses(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    """This runs on the 60s tick, gated by KEY_CHECK_INTERVAL_KEY — a second
    tick right after the first must not re-check at all."""
    notifier = AdminNotifier(FakeBot(), repo, [1])  # type: ignore[arg-type]
    steam_auth = _wired_steam_auth(repo, cipher, notifier)
    health = ServiceHealth(
        repo, PsnAuth(repo, cipher), steam_auth, _unconfigured_anthropic_auth(repo, cipher)
    )
    calls = 0

    async def _counting(api_key: str) -> bool:
        nonlocal calls
        calls += 1
        return True

    monkeypatch.setattr(steam_auth_module, "check_alive", _counting)

    await health.tick()
    await health.tick()

    assert calls == 1


async def test_psn_check_is_skipped_before_the_interval_elapses(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    """Lets PsnAuth's *real* check_health run (mocking only the network
    boundary, check_alive) so checked_at actually gets written."""
    psn_auth = PsnAuth(repo, cipher)

    async def _build(npsso: str) -> object:
        return object()

    calls = 0

    async def _counting_check_alive(client: object) -> bool:
        nonlocal calls
        calls += 1
        return True

    monkeypatch.setattr("bot.services.psn.auth.build_client", _build)
    monkeypatch.setattr("bot.services.psn.auth.check_alive", _counting_check_alive)
    await psn_auth.set_npsso("fake-npsso", admin_id=1)
    calls = 0  # set_npsso's own verification call doesn't count
    stale = (utcnow() - timedelta(minutes=40)).isoformat(timespec="seconds")
    await repo.set_app_setting(PSN_CHECKED_AT_KEY, stale)
    notifier = AdminNotifier(FakeBot(), repo, [1])  # type: ignore[arg-type]
    steam_auth = _wired_steam_auth(repo, cipher, notifier, configured=False)
    health = ServiceHealth(repo, psn_auth, steam_auth, _unconfigured_anthropic_auth(repo, cipher))

    await health.tick()
    await health.tick()

    assert calls == 1


async def test_tick_also_runs_the_psn_health_check(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    """PSN's own check lives in PsnAuth — this just confirms the job
    actually calls it every tick, not just Steam's."""
    psn_auth = PsnAuth(repo, cipher)
    calls = 0

    async def _check_health() -> bool:
        nonlocal calls
        calls += 1
        return True

    monkeypatch.setattr(psn_auth, "check_health", _check_health)
    notifier = AdminNotifier(FakeBot(), repo, [1])  # type: ignore[arg-type]
    steam_auth = _wired_steam_auth(repo, cipher, notifier, configured=False)
    health = ServiceHealth(repo, psn_auth, steam_auth, _unconfigured_anthropic_auth(repo, cipher))

    await health.tick()

    assert calls == 1


async def test_anthropic_never_configured_is_skipped_entirely(
    repo: Repo, cipher: TokenCipher
) -> None:
    notifier = AdminNotifier(FakeBot(), repo, [1])  # type: ignore[arg-type]
    anthropic_auth = _wired_anthropic_auth(repo, cipher, notifier, configured=False)
    health = ServiceHealth(
        repo,
        PsnAuth(repo, cipher),
        _wired_steam_auth(repo, cipher, notifier, configured=False),
        anthropic_auth,
    )

    await health.tick()

    assert await repo.get_app_setting(anthropic_auth_module.STATUS_KEY) is None


async def test_anthropic_transition_to_dead_notifies_once(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    bot = FakeBot()
    notifier = AdminNotifier(bot, repo, [1])  # type: ignore[arg-type]
    anthropic_auth = _wired_anthropic_auth(repo, cipher, notifier)
    health = ServiceHealth(
        repo,
        PsnAuth(repo, cipher),
        _wired_steam_auth(repo, cipher, notifier, configured=False),
        anthropic_auth,
    )

    async def _dead(api_key: str) -> bool:
        return False

    monkeypatch.setattr(anthropic_auth_module, "check_alive", _dead)

    await health.tick()

    assert await repo.get_app_setting(anthropic_auth_module.STATUS_KEY) == STATUS_INVALID
    assert len(bot.sent) == 1
    assert "Anthropic" in bot.sent[0][1]

    # Same "at most once per transition" rule the other two credentials have.
    await health.tick()
    assert len(bot.sent) == 1


async def test_anthropic_recovers_silently(repo: Repo, cipher: TokenCipher, monkeypatch) -> None:
    bot = FakeBot()
    notifier = AdminNotifier(bot, repo, [1])  # type: ignore[arg-type]
    anthropic_auth = _wired_anthropic_auth(repo, cipher, notifier)
    health = ServiceHealth(
        repo,
        PsnAuth(repo, cipher),
        _wired_steam_auth(repo, cipher, notifier, configured=False),
        anthropic_auth,
    )
    await repo.set_app_setting(anthropic_auth_module.STATUS_KEY, STATUS_INVALID)

    async def _alive(api_key: str) -> bool:
        return True

    monkeypatch.setattr(anthropic_auth_module, "check_alive", _alive)

    await health.tick()

    assert await repo.get_app_setting(anthropic_auth_module.STATUS_KEY) == STATUS_ACTIVE
    assert bot.sent == []
