"""Deep-link payload parsing for the group hub's «Подключить Xbox» button
(SPEC 6.3)."""

from __future__ import annotations

from types import SimpleNamespace

from aiogram.filters import CommandObject
from aiogram_i18n import I18nContext

from bot.config import Settings
from bot.db.repo import Repo
from bot.handlers import awaiting
from bot.handlers.connect import _parse_connect_payload, _person_id, start_with_payload
from bot.services.crypto import TokenCipher
from bot.services.psn.auth import PsnAuth
from bot.services.steam.auth import SteamAuth


def test_plain_connect_has_no_origin_chat() -> None:
    assert _parse_connect_payload("connect") == (True, None)


def test_connect_with_a_group_id_extracts_it() -> None:
    # Group chat ids are always negative.
    assert _parse_connect_payload("connect-1001234567890") == (True, -1001234567890)


def test_unrelated_payload_is_not_a_connect_payload() -> None:
    assert _parse_connect_payload("panel") == (False, None)
    assert _parse_connect_payload("") == (False, None)


def test_garbage_after_connect_does_not_crash() -> None:
    assert _parse_connect_payload("connectnonsense") == (False, None)


def test_person_id_returns_from_user_id() -> None:
    msg = SimpleNamespace(
        from_user=SimpleNamespace(id=123, username="user"), chat=SimpleNamespace(id=-100555)
    )
    assert _person_id(msg) == 123  # type: ignore[arg-type]


def test_person_id_returns_none_when_no_from_user() -> None:
    msg = SimpleNamespace(from_user=None, chat=SimpleNamespace(id=-100555))
    assert _person_id(msg) is None  # type: ignore[arg-type]


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> None:
        self.sent.append((chat_id, text))


async def test_start_with_payload_connectsteam_arms_waiting_and_prompts(
    repo: Repo, steam_auth: SteamAuth, cipher: TokenCipher, settings: Settings, i18n: I18nContext
) -> None:
    bot = FakeBot()
    user_id = 12345
    awaiting.clear(user_id)
    msg = SimpleNamespace(
        from_user=SimpleNamespace(id=user_id, username="test_gamer"),
        chat=SimpleNamespace(id=user_id, type="private"),
    )
    cmd = CommandObject(prefix="/", command="start", args="connectsteam")
    psn_auth = PsnAuth(repo, cipher)

    await start_with_payload(
        message=msg,  # type: ignore[arg-type]
        command=cmd,
        repo=repo,
        connect=None,  # type: ignore[arg-type]
        settings=settings,
        psn_auth=psn_auth,
        steam_auth=steam_auth,
        bot=bot,  # type: ignore[arg-type]
        i18n=i18n,
    )

    try:
        assert awaiting.is_expecting(user_id, "steam") is True
        assert len(bot.sent) == 1
        chat_id, text = bot.sent[0]
        assert chat_id == user_id
        assert "steamcommunity.com" in text
    finally:
        awaiting.clear(user_id)


async def test_start_with_payload_connectpsn_arms_waiting_and_prompts(
    repo: Repo, steam_auth: SteamAuth, cipher: TokenCipher, settings: Settings, i18n: I18nContext
) -> None:
    bot = FakeBot()
    user_id = 12346
    awaiting.clear(user_id)
    msg = SimpleNamespace(
        from_user=SimpleNamespace(id=user_id, username="test_gamer_psn"),
        chat=SimpleNamespace(id=user_id, type="private"),
    )
    cmd = CommandObject(prefix="/", command="start", args="connectpsn")
    await repo.set_app_setting("psn_key_status", "active")
    psn_auth = PsnAuth(repo, cipher)

    await start_with_payload(
        message=msg,  # type: ignore[arg-type]
        command=cmd,
        repo=repo,
        connect=None,  # type: ignore[arg-type]
        settings=settings,
        psn_auth=psn_auth,
        steam_auth=steam_auth,
        bot=bot,  # type: ignore[arg-type]
        i18n=i18n,
    )

    try:
        assert awaiting.is_expecting(user_id, "psn") is True
        assert len(bot.sent) == 1
        chat_id, text = bot.sent[0]
        assert chat_id == user_id
        assert "PSN Online ID" in text
    finally:
        awaiting.clear(user_id)
