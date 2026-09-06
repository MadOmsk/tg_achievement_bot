"""services/psn/auth.py — the single service-wide PSN credential (SPEC 9,
M-PSN-1). build_client is monkeypatched at the module boundary throughout
(no real NPSSO exchange in tests)."""

from __future__ import annotations

import pytest

from bot.db.repo import Repo
from bot.services.crypto import TokenCipher
from bot.services.psn import auth as psn_auth_module
from bot.services.psn.auth import (
    STATUS_ACTIVE,
    STATUS_INVALID,
    STATUS_NOT_CONFIGURED,
    PsnAuth,
    PsnNotConfiguredError,
)
from bot.services.psn.client import PsnTokenDeadError

NPSSO = "fake-npsso-value"


class _FakeClient:
    def __init__(self, *, alive: bool = True) -> None:
        self.alive = alive


async def test_status_defaults_to_not_configured(repo: Repo, cipher: TokenCipher) -> None:
    auth = PsnAuth(repo, cipher)
    assert await auth.status() == STATUS_NOT_CONFIGURED
    assert await auth.checked_at() is None


async def test_get_client_before_setup_raises_not_configured(
    repo: Repo, cipher: TokenCipher
) -> None:
    auth = PsnAuth(repo, cipher)
    with pytest.raises(PsnNotConfiguredError):
        await auth.get_client()


async def test_set_npsso_validates_before_storing_anything(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A typo'd NPSSO must not silently overwrite a working one — build_client
    is called (and must succeed) before any app_settings row is touched."""

    async def _dead(npsso: str) -> _FakeClient:
        raise PsnTokenDeadError("bad")

    monkeypatch.setattr(psn_auth_module, "build_client", _dead)
    auth = PsnAuth(repo, cipher)

    with pytest.raises(PsnTokenDeadError):
        await auth.set_npsso(NPSSO, admin_id=1)

    assert await auth.status() == STATUS_NOT_CONFIGURED


async def test_set_npsso_then_get_client_reuses_the_cached_instance(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_calls = 0

    async def _build(npsso: str) -> _FakeClient:
        nonlocal build_calls
        build_calls += 1
        assert npsso == NPSSO
        return _FakeClient()

    monkeypatch.setattr(psn_auth_module, "build_client", _build)
    auth = PsnAuth(repo, cipher)

    await auth.set_npsso(NPSSO, admin_id=7)
    assert await auth.status() == STATUS_ACTIVE
    assert await auth.checked_at() is not None

    client_a = await auth.get_client()
    client_b = await auth.get_client()
    assert client_a is client_b
    assert build_calls == 1  # set_npsso's own build is reused, not repeated


async def test_get_client_rebuilds_from_storage_across_instances(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh PsnAuth (as after a restart) has no in-memory client, but the
    encrypted NPSSO in app_settings survives — get_client() must rebuild
    from it rather than treating that as "not configured"."""

    async def _build(npsso: str) -> _FakeClient:
        assert npsso == NPSSO
        return _FakeClient()

    monkeypatch.setattr(psn_auth_module, "build_client", _build)
    await PsnAuth(repo, cipher).set_npsso(NPSSO, admin_id=1)

    fresh = PsnAuth(repo, cipher)
    client = await fresh.get_client()
    assert isinstance(client, _FakeClient)


async def test_check_health_before_setup_is_a_noop(
    repo: Repo, cipher: TokenCipher
) -> None:
    auth = PsnAuth(repo, cipher)
    fired = False

    async def _on_dead() -> None:
        nonlocal fired
        fired = True

    auth.on_dead = _on_dead
    assert await auth.check_health() is False
    assert fired is False  # nothing was ever configured — not a failure to report


async def test_check_health_notifies_once_on_active_to_invalid_transition(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _build(npsso: str) -> _FakeClient:
        return _FakeClient()

    monkeypatch.setattr(psn_auth_module, "build_client", _build)
    auth = PsnAuth(repo, cipher)
    await auth.set_npsso(NPSSO, admin_id=1)

    async def _check_alive(client: object) -> bool:
        return False

    monkeypatch.setattr(psn_auth_module, "check_alive", _check_alive)

    fired = 0

    async def _on_dead() -> None:
        nonlocal fired
        fired += 1

    auth.on_dead = _on_dead

    assert await auth.check_health() is False
    assert await auth.status() == STATUS_INVALID
    assert fired == 1

    # A second consecutive failed check must not notify again — only the
    # active->invalid transition is newsworthy (poller/service_health.py's
    # own docstring), not "still dead".
    assert await auth.check_health() is False
    assert fired == 1


async def test_check_health_recovers_silently(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coming back to life just flips the status back — no notify for
    recovery, only for death (scope explicitly kept narrow)."""

    async def _build(npsso: str) -> _FakeClient:
        return _FakeClient()

    monkeypatch.setattr(psn_auth_module, "build_client", _build)
    auth = PsnAuth(repo, cipher)
    await auth.set_npsso(NPSSO, admin_id=1)
    await repo.set_app_setting(psn_auth_module.STATUS_KEY, STATUS_INVALID)

    calls = 0

    async def _on_dead() -> None:
        nonlocal calls
        calls += 1

    async def _alive_again(client: object) -> bool:
        return True

    auth.on_dead = _on_dead
    monkeypatch.setattr(psn_auth_module, "check_alive", _alive_again)

    assert await auth.check_health() is True
    assert await auth.status() == STATUS_ACTIVE
    assert calls == 0
