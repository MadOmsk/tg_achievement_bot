"""handlers/admin.py — the "Ключи платформ" screen and its free-text key
entry (#17). _keys_screen is rendered directly; admin_text_input's Steam
branch is driven with a minimal fake Message."""

from __future__ import annotations

from types import SimpleNamespace

from bot.db.repo import Repo
from bot.handlers.admin import (
    STEAM_KEY_KEY,
    _awaiting_input,
    _keys_screen,
    admin_text_input,
)
from bot.services.crypto import TokenCipher
from bot.services.psn.auth import PsnAuth
from bot.services.steam import auth as steam_auth_module
from bot.services.steam.auth import SteamAuth

KEY = "0123456789ABCDEF0123456789ABCDEF"
ADMIN_ID = 1


def _callback_datas(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


async def test_keys_screen_lists_both_platforms_unconfigured(
    repo: Repo, cipher: TokenCipher
) -> None:
    text, markup = await _keys_screen(SteamAuth(repo, cipher), PsnAuth(repo, cipher))

    datas = _callback_datas(markup)
    assert "a:keyset:steam" in datas
    assert "a:keyset:psn" in datas
    # Nothing configured — no Clear buttons.
    assert "a:keyclr:steam" not in datas
    assert "a:keyclr:psn" not in datas
    assert "не настроен" in text


async def test_keys_screen_offers_clear_once_steam_is_configured(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    async def _alive(api_key: str) -> bool:
        return True

    monkeypatch.setattr(steam_auth_module, "check_alive", _alive)
    steam_auth = SteamAuth(repo, cipher)
    await steam_auth.set_key(KEY, admin_id=ADMIN_ID)

    _text, markup = await _keys_screen(steam_auth, PsnAuth(repo, cipher))

    datas = _callback_datas(markup)
    assert "a:keyclr:steam" in datas
    assert "a:keyclr:psn" not in datas


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=ADMIN_ID)
        self.chat = SimpleNamespace(id=ADMIN_ID)
        self.answers: list[str] = []

    async def answer(self, text: str, **kwargs) -> None:
        self.answers.append(text)


async def test_admin_text_input_saves_a_valid_steam_key(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    async def _alive(api_key: str) -> bool:
        return True

    monkeypatch.setattr(steam_auth_module, "check_alive", _alive)
    steam_auth = SteamAuth(repo, cipher)
    psn_auth = PsnAuth(repo, cipher)
    _awaiting_input[ADMIN_ID] = (STEAM_KEY_KEY, None)
    msg = _FakeMessage(KEY)

    await admin_text_input(msg, psn_auth, steam_auth)

    assert await steam_auth.get_key() == KEY
    assert ADMIN_ID not in _awaiting_input  # flow finished
    assert msg.answers and "🔑" in msg.answers[0]


async def test_admin_text_input_rejects_a_bad_steam_key_and_stays_armed(
    repo: Repo, cipher: TokenCipher, monkeypatch
) -> None:
    async def _dead(api_key: str) -> bool:
        return False

    monkeypatch.setattr(steam_auth_module, "check_alive", _dead)
    steam_auth = SteamAuth(repo, cipher)
    _awaiting_input[ADMIN_ID] = (STEAM_KEY_KEY, None)
    msg = _FakeMessage("bad-key")

    await admin_text_input(msg, PsnAuth(repo, cipher), steam_auth)

    assert await steam_auth.get_key() is None
    assert _awaiting_input.get(ADMIN_ID) == (STEAM_KEY_KEY, None)  # still armed for a retry
    _awaiting_input.pop(ADMIN_ID, None)
