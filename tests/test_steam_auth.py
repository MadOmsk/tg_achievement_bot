"""services/steam/auth.py — the single admin-settable Steam Web API key
(#17). check_alive is monkeypatched at the module boundary (no real Steam
call in tests)."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.services.crypto import TokenCipher
from bot.services.steam import auth as steam_auth_module
from bot.services.steam.auth import (
    KEY_ENC_KEY,
    STATUS_ACTIVE,
    STATUS_INVALID,
    STATUS_NOT_CONFIGURED,
    SteamAuth,
    SteamKeyInvalidError,
    SteamNotConfiguredError,
)

KEY = "0123456789ABCDEF0123456789ABCDEF"


def _alive_ok(monkeypatch) -> None:
    async def _alive(api_key: str) -> bool:
        return True

    monkeypatch.setattr(steam_auth_module, "check_alive", _alive)


async def test_unconfigured_reports_not_configured_and_no_key(
    repo: Repo, cipher: TokenCipher
) -> None:
    auth = SteamAuth(repo, cipher)  # no env seed
    assert await auth.status() == STATUS_NOT_CONFIGURED
    assert await auth.get_key() is None
    assert await auth.checked_at() is None


async def test_env_key_is_seeded_once_on_first_access(repo: Repo, cipher: TokenCipher) -> None:
    auth = SteamAuth(repo, cipher, env_key="env-seed-key")

    assert await auth.get_key() == "env-seed-key"
    # Persisted (encrypted) so a later instance / restart still has it.
    assert await repo.get_app_setting(KEY_ENC_KEY) is not None
    fresh = SteamAuth(repo, cipher)  # no env this time
    assert await fresh.get_key() == "env-seed-key"


async def test_env_seed_does_not_override_a_stored_key(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    _alive_ok(monkeypatch)
    await SteamAuth(repo, cipher).set_key(KEY, admin_id=1)

    # A different env value must not clobber what the admin set in the panel.
    seeded = SteamAuth(repo, cipher, env_key="stale-env-key")
    assert await seeded.get_key() == KEY


async def test_set_key_verifies_then_stores(repo: Repo, cipher: TokenCipher, monkeypatch) -> None:
    _alive_ok(monkeypatch)
    auth = SteamAuth(repo, cipher)

    await auth.set_key(f"  {KEY}  ", admin_id=9)  # trimmed

    assert await auth.get_key() == KEY
    assert await auth.status() == STATUS_ACTIVE
    assert await auth.checked_at() is not None


async def test_set_key_rejects_a_key_that_fails_verification(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    async def _dead(api_key: str) -> bool:
        return False

    monkeypatch.setattr(steam_auth_module, "check_alive", _dead)
    auth = SteamAuth(repo, cipher)

    try:
        await auth.set_key(KEY, admin_id=1)
        raise AssertionError("expected SteamKeyInvalidError")
    except SteamKeyInvalidError:
        pass

    assert await auth.status() == STATUS_NOT_CONFIGURED
    assert await repo.get_app_setting(KEY_ENC_KEY) is None


async def test_clear_removes_the_key_and_disables_the_env_seed(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    _alive_ok(monkeypatch)
    auth = SteamAuth(repo, cipher, env_key="env-seed-key")
    await auth.get_key()  # triggers the seed

    await auth.clear(admin_id=1)

    assert await auth.status() == STATUS_NOT_CONFIGURED
    assert await auth.get_key() is None  # not re-seeded from the stale env var
    assert await auth.checked_at() is None
    try:
        await auth.require_key()
        raise AssertionError("expected SteamNotConfiguredError")
    except SteamNotConfiguredError:
        pass


async def test_check_health_notifies_once_on_active_to_invalid(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    _alive_ok(monkeypatch)
    auth = SteamAuth(repo, cipher)
    await auth.set_key(KEY, admin_id=1)

    async def _dead(api_key: str) -> bool:
        return False

    monkeypatch.setattr(steam_auth_module, "check_alive", _dead)
    fired = 0

    async def _on_dead() -> None:
        nonlocal fired
        fired += 1

    auth.on_dead = _on_dead

    assert await auth.check_health() is False
    assert await auth.status() == STATUS_INVALID
    assert fired == 1

    # Still dead — not newsworthy again.
    assert await auth.check_health() is False
    assert fired == 1


async def test_check_health_before_setup_is_a_noop(repo: Repo, cipher: TokenCipher) -> None:
    auth = SteamAuth(repo, cipher)
    fired = False

    async def _on_dead() -> None:
        nonlocal fired
        fired = True

    auth.on_dead = _on_dead
    assert await auth.check_health() is False
    assert fired is False
