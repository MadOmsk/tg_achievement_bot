"""PSN login flow (SPEC 9, M-PSN-1) — the shared prompt_for_link() step and
the AwaitingPsnLink filter, plus the actual resolve+visibility+link body
(_connect), which unlike Steam's own version is small enough to unit-test
directly here (no backfill, no URL parsing)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bot.db.repo import Repo
from bot.handlers import psn as psn_handlers
from bot.handlers.psn import (
    AwaitingPsnLink,
    _awaiting_link,
    _connect,
    prompt_for_link,
)
from bot.services.crypto import TokenCipher
from bot.services.psn.auth import PsnAuth
from bot.services.psn.client import PsnApiError, PsnProfile, PsnTokenDeadError

TG_ID = 42
NPSSO = "fake-npsso"


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> None:
        self.sent.append((chat_id, text))


def _event(tg_id: int | None) -> SimpleNamespace:
    user = SimpleNamespace(id=tg_id) if tg_id is not None else None
    return SimpleNamespace(from_user=user)


async def _configured_auth(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> PsnAuth:
    async def _build(npsso: str) -> object:
        return object()

    monkeypatch.setattr("bot.services.psn.auth.build_client", _build)
    auth = PsnAuth(repo, cipher)
    await auth.set_npsso(NPSSO, admin_id=1)
    return auth


async def test_awaiting_filter_is_false_for_an_unarmed_user() -> None:
    _awaiting_link.discard(TG_ID)
    assert await AwaitingPsnLink()(_event(TG_ID)) is False


async def test_awaiting_filter_is_true_once_armed() -> None:
    _awaiting_link.add(TG_ID)
    try:
        assert await AwaitingPsnLink()(_event(TG_ID)) is True
    finally:
        _awaiting_link.discard(TG_ID)


async def test_awaiting_filter_is_false_with_no_user_at_all() -> None:
    assert await AwaitingPsnLink()(_event(None)) is False


async def test_prompt_replies_not_configured_without_arming(
    repo: Repo, cipher: TokenCipher
) -> None:
    bot = FakeBot()
    _awaiting_link.discard(TG_ID)
    auth = PsnAuth(repo, cipher)  # never configured

    await prompt_for_link(bot, repo, auth, TG_ID)  # type: ignore[arg-type]

    assert bot.sent == [
        (TG_ID, "Подключение PSN пока не настроено — обратитесь к администратору.")
    ]
    assert TG_ID not in _awaiting_link


async def test_prompt_reports_already_connected_without_arming(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_platform_account(TG_ID, "psn", "acc-1", "Gamer")
    auth = await _configured_auth(repo, cipher, monkeypatch)
    bot = FakeBot()
    _awaiting_link.discard(TG_ID)

    await prompt_for_link(bot, repo, auth, TG_ID)  # type: ignore[arg-type]

    assert bot.sent == [(TG_ID, "PSN уже подключён: Gamer.")]
    assert TG_ID not in _awaiting_link


async def test_prompt_arms_the_wait_and_sends_the_link_prompt(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    await repo.ensure_user(TG_ID, "igor")
    auth = await _configured_auth(repo, cipher, monkeypatch)
    bot = FakeBot()
    _awaiting_link.discard(TG_ID)

    await prompt_for_link(bot, repo, auth, TG_ID)  # type: ignore[arg-type]

    assert TG_ID in _awaiting_link
    assert len(bot.sent) == 1
    assert "Online ID" in bot.sent[0][1]
    _awaiting_link.discard(TG_ID)


async def test_connect_links_a_visible_profile(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = await _configured_auth(repo, cipher, monkeypatch)
    bot = FakeBot()

    async def _resolve(client: object, online_id: str) -> PsnProfile:
        return PsnProfile(account_id="acc-1", online_id="Gamer")

    async def _visible(client: object, account_id: str) -> bool:
        return True

    monkeypatch.setattr(psn_handlers, "resolve_profile", _resolve)
    monkeypatch.setattr(psn_handlers, "is_trophy_visible", _visible)

    await _connect(bot, repo, auth, TG_ID, "igor", "Gamer")  # type: ignore[arg-type]

    link = await repo.get_platform_link(TG_ID, "psn")
    assert link is not None
    assert link.external_id == "acc-1"
    assert link.display_name == "Gamer"
    assert bot.sent[-1] == (TG_ID, "Подключил PSN: Gamer.")


async def test_connect_refuses_a_closed_profile_without_linking(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirrors Steam's own private-profile refusal (services/steam/client.py's
    is_public check) — checklist item 3, SPEC 9, M-PSN-1."""
    auth = await _configured_auth(repo, cipher, monkeypatch)
    bot = FakeBot()

    async def _resolve(client: object, online_id: str) -> PsnProfile:
        return PsnProfile(account_id="acc-1", online_id="Gamer")

    async def _closed(client: object, account_id: str) -> bool:
        return False

    monkeypatch.setattr(psn_handlers, "resolve_profile", _resolve)
    monkeypatch.setattr(psn_handlers, "is_trophy_visible", _closed)

    await _connect(bot, repo, auth, TG_ID, "igor", "Gamer")  # type: ignore[arg-type]

    assert await repo.get_platform_link(TG_ID, "psn") is None
    assert "скрыты" in bot.sent[-1][1]


async def test_connect_reports_unresolvable_online_id(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = await _configured_auth(repo, cipher, monkeypatch)
    bot = FakeBot()

    async def _not_found(client: object, online_id: str) -> PsnProfile:
        raise PsnApiError("nope")

    monkeypatch.setattr(psn_handlers, "resolve_profile", _not_found)

    await _connect(bot, repo, auth, TG_ID, "igor", "nobody")  # type: ignore[arg-type]

    assert await repo.get_platform_link(TG_ID, "psn") is None
    assert "Не нашёл" in bot.sent[-1][1]


async def test_connect_reports_a_dead_service_token(
    repo: Repo, cipher: TokenCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = await _configured_auth(repo, cipher, monkeypatch)
    bot = FakeBot()

    async def _dead(client: object, online_id: str) -> PsnProfile:
        raise PsnTokenDeadError("dead")

    monkeypatch.setattr(psn_handlers, "resolve_profile", _dead)

    await _connect(bot, repo, auth, TG_ID, "igor", "Gamer")  # type: ignore[arg-type]

    assert await repo.get_platform_link(TG_ID, "psn") is None
    assert "недоступен" in bot.sent[-1][1]


async def test_disconnect_removes_the_link(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_platform_account(TG_ID, "psn", "acc-1", "Gamer")

    await repo.unlink_platform_account(TG_ID, "psn")

    assert await repo.get_platform_link(TG_ID, "psn") is None
