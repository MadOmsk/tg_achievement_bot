"""services/psn/auth.py — the single service-wide PSN credential (SPEC 9,
M-PSN-1). build_client is monkeypatched at the module boundary throughout
(no real NPSSO exchange in tests)."""

from __future__ import annotations

import pytest
from psnawp_api.core.psnawp_exceptions import PSNAWPAuthenticationError

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
    """A real `.me()` (psnawp's cheapest authenticated call) means the real
    check_alive() can drive set_npsso()'s own verification call without
    needing to be mocked separately in most of these tests — flip
    `.alive` to make a later check_health() see it go dark."""

    def __init__(self, *, alive: bool = True) -> None:
        self.alive = alive

    def me(self) -> _FakeClient:
        if not self.alive:
            raise PSNAWPAuthenticationError("dead")
        return self

    online_id = "service-account"


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


async def test_set_npsso_rejects_a_client_that_fails_verification(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """build_client() alone does NOT prove the NPSSO works (found live
    2026-09-06: psnawp_api's constructor "succeeds" for complete garbage,
    no network call at all) — set_npsso() must make a real verification
    call (check_alive) before considering it good."""

    async def _build(npsso: str) -> _FakeClient:
        return _FakeClient(alive=False)

    monkeypatch.setattr(psn_auth_module, "build_client", _build)
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


async def test_clear_reverts_to_not_configured(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#17: the admin panel's Clear action — set_npsso only ever overwrote,
    nothing removed the row before."""

    async def _build(npsso: str) -> _FakeClient:
        return _FakeClient()

    monkeypatch.setattr(psn_auth_module, "build_client", _build)
    auth = PsnAuth(repo, cipher)
    await auth.set_npsso(NPSSO, admin_id=1)
    assert await auth.status() == STATUS_ACTIVE

    await auth.clear(admin_id=1)

    assert await auth.status() == STATUS_NOT_CONFIGURED
    assert await auth.checked_at() is None
    assert await repo.get_app_setting(psn_auth_module.NPSSO_KEY) is None
    with pytest.raises(PsnNotConfiguredError):
        await auth.get_client()


async def test_check_health_before_setup_is_a_noop(repo: Repo, cipher: TokenCipher) -> None:
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
    fake_client = _FakeClient()

    async def _build(npsso: str) -> _FakeClient:
        return fake_client

    monkeypatch.setattr(psn_auth_module, "build_client", _build)
    auth = PsnAuth(repo, cipher)
    await auth.set_npsso(NPSSO, admin_id=1)

    fake_client.alive = False  # the same cached client instance goes dark

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


# get_translation_client() — the second, Russian-locale client (2026-09-09,
# #48).


async def test_get_translation_client_before_setup_raises_not_configured(
    repo: Repo, cipher: TokenCipher
) -> None:
    auth = PsnAuth(repo, cipher)
    with pytest.raises(PsnNotConfiguredError):
        await auth.get_translation_client()


async def test_get_translation_client_passes_the_ru_headers(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[dict[str, str] | None] = []

    async def _build(npsso: str, *, headers: dict[str, str] | None = None) -> _FakeClient:
        seen.append(headers)
        return _FakeClient()

    monkeypatch.setattr(psn_auth_module, "build_client", _build)
    auth = PsnAuth(repo, cipher)
    await auth.set_npsso(NPSSO, admin_id=1)  # the primary client — no headers override
    seen.clear()

    await auth.get_translation_client()

    assert seen == [psn_auth_module.TRANSLATION_HEADERS]


async def test_get_translation_client_is_cached_and_distinct_from_the_primary(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_calls = 0

    async def _build(npsso: str, *, headers: dict[str, str] | None = None) -> _FakeClient:
        nonlocal build_calls
        build_calls += 1
        return _FakeClient()

    monkeypatch.setattr(psn_auth_module, "build_client", _build)
    auth = PsnAuth(repo, cipher)
    await auth.set_npsso(NPSSO, admin_id=1)
    build_calls = 0  # set_npsso's own primary build already happened

    ru_a = await auth.get_translation_client()
    ru_b = await auth.get_translation_client()
    primary = await auth.get_client()

    assert ru_a is ru_b
    assert ru_a is not primary
    assert build_calls == 1  # cached after the first build, same as the primary


async def test_set_npsso_invalidates_a_previously_built_translation_client(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _build(npsso: str, *, headers: dict[str, str] | None = None) -> _FakeClient:
        return _FakeClient()

    monkeypatch.setattr(psn_auth_module, "build_client", _build)
    auth = PsnAuth(repo, cipher)
    await auth.set_npsso(NPSSO, admin_id=1)
    first_ru = await auth.get_translation_client()

    await auth.set_npsso(NPSSO, admin_id=1)  # e.g. a fresh NPSSO pasted in
    second_ru = await auth.get_translation_client()

    assert first_ru is not second_ru


async def test_clear_invalidates_the_translation_client_too(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _build(npsso: str, *, headers: dict[str, str] | None = None) -> _FakeClient:
        return _FakeClient()

    monkeypatch.setattr(psn_auth_module, "build_client", _build)
    auth = PsnAuth(repo, cipher)
    await auth.set_npsso(NPSSO, admin_id=1)
    await auth.get_translation_client()

    await auth.clear(admin_id=1)

    with pytest.raises(PsnNotConfiguredError):
        await auth.get_translation_client()


async def test_check_health_death_invalidates_the_translation_client_too(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_client = _FakeClient()

    async def _build(npsso: str, *, headers: dict[str, str] | None = None) -> _FakeClient:
        return fake_client

    monkeypatch.setattr(psn_auth_module, "build_client", _build)
    auth = PsnAuth(repo, cipher)
    await auth.set_npsso(NPSSO, admin_id=1)
    first_ru = await auth.get_translation_client()

    fake_client.alive = False
    await auth.check_health()

    build_calls = 0

    async def _rebuild(npsso: str, *, headers: dict[str, str] | None = None) -> _FakeClient:
        nonlocal build_calls
        build_calls += 1
        return _FakeClient()

    monkeypatch.setattr(psn_auth_module, "build_client", _rebuild)
    second_ru = await auth.get_translation_client()

    assert second_ru is not first_ru
    assert build_calls == 1


async def test_check_health_recovers_silently(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coming back to life just flips the status back — no notify for
    recovery, only for death (scope explicitly kept narrow)."""

    fake_client = _FakeClient()

    async def _build(npsso: str) -> _FakeClient:
        return fake_client

    monkeypatch.setattr(psn_auth_module, "build_client", _build)
    auth = PsnAuth(repo, cipher)
    await auth.set_npsso(NPSSO, admin_id=1)
    await repo.set_app_setting(psn_auth_module.STATUS_KEY, STATUS_INVALID)

    calls = 0

    async def _on_dead() -> None:
        nonlocal calls
        calls += 1

    auth.on_dead = _on_dead

    assert await auth.check_health() is True
    assert await auth.status() == STATUS_ACTIVE
    assert calls == 0
