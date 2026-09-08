"""poller/psn_presence.py — issue #1's "/online" piece. get_presence() is
faked at the module boundary, same as every other poller test in this
project fakes its client/service layer."""

from __future__ import annotations

from bot.config import Settings
from bot.db.repo import Repo
from bot.poller import psn_presence as psn_presence_module
from bot.poller.psn_presence import PsnPresencePoller
from bot.services.crypto import TokenCipher
from bot.services.psn.auth import PsnAuth
from bot.services.psn.client import PsnApiError, PsnPresenceSnapshot

TG_ID = 42
ACCOUNT_ID = "acc-1"


async def _linked_user(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_platform_account(TG_ID, "psn", ACCOUNT_ID, "Gamer")


async def _configured_auth(repo: Repo, cipher: TokenCipher, monkeypatch) -> PsnAuth:
    async def _build(npsso: str) -> object:
        return object()

    async def _alive(client: object) -> bool:
        return True

    monkeypatch.setattr("bot.services.psn.auth.build_client", _build)
    monkeypatch.setattr("bot.services.psn.auth.check_alive", _alive)
    auth = PsnAuth(repo, cipher)
    await auth.set_npsso("fake-npsso", admin_id=1)
    return auth


def _fake_presence(monkeypatch, result) -> list[str]:
    """`result` is either one PsnPresenceSnapshot/exception (returned/raised
    every call) or a dict of account_id -> snapshot-or-exception. Records
    which account_ids were actually queried."""
    calls: list[str] = []

    async def fake_get_presence(client: object, account_id: str) -> PsnPresenceSnapshot:
        calls.append(account_id)
        outcome = result[account_id] if isinstance(result, dict) else result
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(psn_presence_module, "get_presence", fake_get_presence)
    return calls


async def test_tick_saves_online_presence_and_touches_last_online(
    repo: Repo, cipher: TokenCipher, settings: Settings, monkeypatch
) -> None:
    await _linked_user(repo)
    auth = await _configured_auth(repo, cipher, monkeypatch)
    _fake_presence(
        monkeypatch, PsnPresenceSnapshot(state="Online", title_id="CUSA14296_00", title_name="Rust")
    )
    poller = PsnPresencePoller(settings, repo, auth)

    await poller.tick()

    saved = await repo.psn_presence_of(ACCOUNT_ID)
    assert saved is not None
    assert saved.state == "Online"
    assert saved.title_id == "CUSA14296_00"
    assert saved.title_name == "Rust"
    user = await repo.get_user(TG_ID)
    assert user is not None and user.last_online_at is not None


async def test_tick_saves_offline_presence_without_touching_last_online(
    repo: Repo, cipher: TokenCipher, settings: Settings, monkeypatch
) -> None:
    await _linked_user(repo)
    auth = await _configured_auth(repo, cipher, monkeypatch)
    _fake_presence(
        monkeypatch, PsnPresenceSnapshot(state="Offline", title_id=None, title_name=None)
    )
    poller = PsnPresencePoller(settings, repo, auth)

    await poller.tick()

    saved = await repo.psn_presence_of(ACCOUNT_ID)
    assert saved is not None
    assert saved.state == "Offline"
    user = await repo.get_user(TG_ID)
    assert user is not None and user.last_online_at is None


async def test_tick_skips_silently_when_psn_is_not_configured(
    repo: Repo, cipher: TokenCipher, settings: Settings
) -> None:
    """No NPSSO set anywhere — same silent skip PsnFetcher's own tick gets
    (M-PSN-1), not an exception that would take down the whole scheduler."""
    await _linked_user(repo)
    auth = PsnAuth(repo, cipher)  # never configured
    poller = PsnPresencePoller(settings, repo, auth)

    await poller.tick()  # must not raise

    assert await repo.psn_presence_of(ACCOUNT_ID) is None


async def test_tick_isolates_one_accounts_failure_from_the_rest(
    repo: Repo, cipher: TokenCipher, settings: Settings, monkeypatch
) -> None:
    """A private profile (or any other PsnApiError) for one account must not
    stop the tick from reaching the next one — same isolation discipline
    presence.py/steam_presence.py already follow."""
    await _linked_user(repo)
    await repo.ensure_user(43, "other")
    await repo.link_platform_account(43, "psn", "acc-2", "OtherGamer")
    auth = await _configured_auth(repo, cipher, monkeypatch)
    calls = _fake_presence(
        monkeypatch,
        {
            ACCOUNT_ID: PsnApiError("private profile"),
            "acc-2": PsnPresenceSnapshot(state="Online", title_id=None, title_name=None),
        },
    )
    poller = PsnPresencePoller(settings, repo, auth)

    await poller.tick()

    assert set(calls) == {ACCOUNT_ID, "acc-2"}
    assert await repo.psn_presence_of(ACCOUNT_ID) is None  # failed account: nothing saved
    saved = await repo.psn_presence_of("acc-2")
    assert saved is not None and saved.state == "Online"


async def test_a_recently_polled_account_is_not_due_again_immediately(
    repo: Repo, cipher: TokenCipher, settings: Settings, monkeypatch
) -> None:
    await _linked_user(repo)
    auth = await _configured_auth(repo, cipher, monkeypatch)
    calls = _fake_presence(
        monkeypatch, PsnPresenceSnapshot(state="Offline", title_id=None, title_name=None)
    )
    poller = PsnPresencePoller(settings, repo, auth)

    await poller.tick()
    await poller.tick()  # same tick cycle, well inside the offline interval

    assert calls == [ACCOUNT_ID]  # second tick found nothing due
