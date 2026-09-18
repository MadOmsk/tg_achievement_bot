"""Getting into the Mini App from a chat (1.2.0).

Everything these cover shipped with #81 already written and wired to
nothing: six translated strings with no caller, a hub keyboard rebuilt as a
list of rows with no row ever appended to it, and `settings` threaded into
five handlers and read by none.

The rule worth a test of its own is the one that cannot be discovered
locally: **a group cannot carry a `web_app` button at all** — Telegram
answers BUTTON_TYPE_INVALID — so the same "open the app" affordance has to
be a `t.me/<bot>?startapp=…` link there and a real WebApp button in a DM.
Getting that backwards fails only against Telegram's own API, which the
tests here are forbidden from calling.
"""

from __future__ import annotations

from types import SimpleNamespace

from aiogram.enums import ChatType

from bot.handlers.chat import open_app
from bot.views.chat import hub_keyboard

BOT = "mybot"
CHAT_ID = -100500
APP_URL = "https://example.test/app/"


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


class _FakeMessage:
    def __init__(self, chat_type: str, chat_id: int) -> None:
        self.chat = SimpleNamespace(id=chat_id, type=chat_type)
        self.answers: list[str] = []
        self.markups: list[object] = []

    async def answer(self, text: str, reply_markup=None, **kwargs) -> None:
        self.answers.append(text)
        self.markups.append(reply_markup)


class _FakeBot:
    async def me(self):
        return SimpleNamespace(username=BOT)


def test_the_hub_gains_an_app_row_only_when_there_is_an_app() -> None:
    assert len(_buttons(hub_keyboard(BOT, CHAT_ID))) == 5

    buttons = _buttons(hub_keyboard(BOT, CHAT_ID, mini_app_url=APP_URL))
    assert len(buttons) == 6
    app_button = buttons[-1]
    assert app_button.url == f"https://t.me/{BOT}?startapp=c{CHAT_ID}"
    assert app_button.web_app is None


def test_a_blank_url_is_not_an_app() -> None:
    """`MINI_APP_URL=` in the environment reads as an empty string, not as a
    missing key — a button to nowhere is worse than no button."""
    assert len(_buttons(hub_keyboard(BOT, CHAT_ID, mini_app_url="   "))) == 5


async def test_app_command_in_a_group_sends_a_link_not_a_web_app(i18n) -> None:
    message = _FakeMessage(ChatType.SUPERGROUP, CHAT_ID)

    await open_app(message, _FakeBot(), i18n, SimpleNamespace(mini_app_url=APP_URL))

    [button] = _buttons(message.markups[0])
    assert button.web_app is None
    assert button.url == f"https://t.me/{BOT}?startapp=c{CHAT_ID}"


async def test_app_command_in_a_dm_opens_the_app_itself(i18n) -> None:
    message = _FakeMessage(ChatType.PRIVATE, 4242)

    await open_app(message, _FakeBot(), i18n, SimpleNamespace(mini_app_url=APP_URL))

    [button] = _buttons(message.markups[0])
    assert button.url is None
    assert button.web_app is not None
    assert button.web_app.url.startswith(APP_URL)


async def test_app_command_says_so_when_no_app_is_configured(i18n) -> None:
    """The command is published in Telegram's own menu, so somebody will
    type it whether or not MINI_APP_URL is set."""
    message = _FakeMessage(ChatType.SUPERGROUP, CHAT_ID)

    await open_app(message, _FakeBot(), i18n, SimpleNamespace(mini_app_url=""))

    assert message.markups == [None]
    assert "MINI_APP_URL" in message.answers[0]


async def test_start_in_a_group_gets_no_web_app_button(i18n, repo) -> None:
    """Telegram accepts a `web_app` button only in a private chat; anywhere
    else it answers BUTTON_TYPE_INVALID and the *whole message* fails. So a
    `/start` typed in a group — which carries no chat-type filter — must be
    answered with one row fewer, not with an error.
    """
    from types import SimpleNamespace

    from bot.handlers.connect import _greet

    class _Msg:
        def __init__(self, chat_type: str) -> None:
            self.chat = SimpleNamespace(id=555, type=chat_type)
            self.markups: list[object] = []

        async def answer(self, text: str, reply_markup=None, **kwargs) -> None:
            self.markups.append(reply_markup)

    connect = SimpleNamespace(start_login=lambda tg_id: "https://login.example")
    settings = SimpleNamespace(mini_app_url=APP_URL)

    group = _Msg(ChatType.SUPERGROUP)
    await _greet(group, repo, connect, _FakeBot(), i18n, settings)
    group_buttons = _buttons(group.markups[-1])

    private = _Msg(ChatType.PRIVATE)
    await _greet(private, repo, connect, _FakeBot(), i18n, settings)
    private_buttons = _buttons(private.markups[-1])

    assert not any(button.web_app for button in group_buttons)
    assert any(button.web_app for button in private_buttons)
