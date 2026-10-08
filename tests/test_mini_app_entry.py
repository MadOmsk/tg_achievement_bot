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

from bot.handlers.chat import help_command, panel_command
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
        self.stats_categories: list[bool] = []

    async def answer(self, text: str, reply_markup=None, **kwargs) -> None:
        from bot.services.message_log import _stats_category

        self.answers.append(text)
        self.markups.append(reply_markup)
        self.stats_categories.append(_stats_category.get())


class _FakeBot:
    async def me(self):
        return SimpleNamespace(username=BOT)


def test_the_hub_gains_an_app_row_only_when_there_is_an_app() -> None:
    assert len(_buttons(hub_keyboard(BOT, CHAT_ID))) == 11

    buttons = _buttons(hub_keyboard(BOT, CHAT_ID, mini_app_url=APP_URL))
    assert len(buttons) == 12
    app_button = buttons[0]
    assert app_button.url == f"https://t.me/{BOT}?startapp=c{CHAT_ID}"
    assert app_button.web_app is None


def test_a_blank_url_is_not_an_app() -> None:
    """`MINI_APP_URL=` in the environment reads as an empty string, not as a
    missing key — a button to nowhere is worse than no button."""
    assert len(_buttons(hub_keyboard(BOT, CHAT_ID, mini_app_url="   "))) == 11


async def test_panel_command_in_a_group_sends_a_link_not_a_web_app(i18n, repo) -> None:
    message = _FakeMessage(ChatType.SUPERGROUP, CHAT_ID)

    await panel_command(message, repo, _FakeBot(), i18n, SimpleNamespace(mini_app_url=APP_URL))

    buttons = _buttons(message.markups[0])
    app_button = buttons[0]
    assert app_button.web_app is None
    assert app_button.url == f"https://t.me/{BOT}?startapp=c{CHAT_ID}"


async def test_help_command_in_a_group_links_settings_instead_of_a_bare_panel(i18n, repo) -> None:
    """#133: a tap on a bare `/panel` in a group sends it to the group; the
    settings are a button into the DM."""
    message = _FakeMessage(ChatType.SUPERGROUP, CHAT_ID)

    await help_command(message, repo, _FakeBot(), i18n, SimpleNamespace(mini_app_url=APP_URL))

    buttons = _buttons(message.markups[0])
    assert [b.url for b in buttons[:1]] == [f"https://t.me/{BOT}?start=panel"]
    assert buttons[-1].callback_data == "msg:close"
    assert "в личке, /panel" not in message.answers[0]


async def test_help_command_in_a_dm_opens_the_app_itself(i18n, repo) -> None:
    message = _FakeMessage(ChatType.PRIVATE, 4242)

    await help_command(message, repo, _FakeBot(), i18n, SimpleNamespace(mini_app_url=APP_URL))

    buttons = _buttons(message.markups[0])
    assert len(buttons) == 1  # the app, nothing else (#140)
    app_button = buttons[0]
    assert app_button.url is None
    assert app_button.web_app is not None
    assert app_button.web_app.url.startswith(APP_URL)
    assert "/connect_" not in message.answers[0]


async def test_help_command_in_a_dm_without_app_url(i18n, repo) -> None:
    message = _FakeMessage(ChatType.PRIVATE, 4242)

    await help_command(message, repo, _FakeBot(), i18n, SimpleNamespace(mini_app_url=""))

    assert message.markups[0] is None


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

    connect = SimpleNamespace(start_login=lambda person, **_kw: "https://login.example")
    settings = SimpleNamespace(mini_app_url=APP_URL)

    group = _Msg(ChatType.SUPERGROUP)
    await _greet(group, repo, connect, _FakeBot(), i18n, settings)
    group_buttons = _buttons(group.markups[-1])

    private = _Msg(ChatType.PRIVATE)
    await _greet(private, repo, connect, _FakeBot(), i18n, settings)
    private_buttons = _buttons(private.markups[-1])

    assert not any(button.web_app for button in group_buttons)
    assert any(button.web_app for button in private_buttons)


def test_promo_text_ru_and_en() -> None:
    from bot.views.promo import promo_text

    text_ru = promo_text("ru")
    assert text_ru.startswith("🎮 <b>Игровой клуб</b>")
    assert "Mini App" in text_ru

    text_en = promo_text("en")
    assert text_en.startswith("🎮 <b>Gaming Club</b>")
    assert "Mini App" in text_en


def test_promo_keyboard_group_and_private() -> None:
    from bot.views.promo import promo_keyboard

    # Group keyboard: URL button
    kb_group = promo_keyboard(BOT, CHAT_ID, mini_app_url=APP_URL, is_group=True, locale="ru")
    assert kb_group is not None
    btn = kb_group.inline_keyboard[0][0]
    assert btn.text == "Открыть Mini App"
    assert btn.url == f"https://t.me/{BOT}?startapp=c{CHAT_ID}"
    assert btn.web_app is None

    # Private keyboard: WebApp button
    kb_dm = promo_keyboard(BOT, 12345, mini_app_url=APP_URL, is_group=False, locale="en")
    assert kb_dm is not None
    btn_dm = kb_dm.inline_keyboard[0][0]
    assert btn_dm.text == "Open Mini App"
    assert btn_dm.url is None
    assert btn_dm.web_app is not None
    assert btn_dm.web_app.url.startswith(APP_URL)


async def test_promo_command_in_group(i18n) -> None:
    from bot.handlers.chat import promo_command

    msg = _FakeMessage(ChatType.SUPERGROUP, CHAT_ID)
    settings = SimpleNamespace(mini_app_url=APP_URL)
    await promo_command(msg, _FakeBot(), i18n, settings)

    assert len(msg.answers) == 1
    assert "Игровой клуб" in msg.answers[0]
    assert msg.stats_categories == [True]
    btn = msg.markups[0].inline_keyboard[0][0]
    assert btn.url == f"https://t.me/{BOT}?startapp=c{CHAT_ID}"


async def test_admin_chat_send_promo_sets_stats_category(i18n, repo) -> None:
    from bot.handlers.delivery import send_promo
    from bot.services.message_log import _stats_category

    await repo.upsert_chat(CHAT_ID, "Test Chat", 1)

    class _AdminBot:
        def __init__(self) -> None:
            self.sent_categories: list[bool] = []

        async def me(self):
            return SimpleNamespace(username=BOT)

        async def send_message(self, chat_id: int, text: str, **kwargs):
            self.sent_categories.append(_stats_category.get())

    admin_bot = _AdminBot()

    await send_promo(admin_bot, CHAT_ID, "ru", APP_URL)  # type: ignore[arg-type]
    assert admin_bot.sent_categories == [True]
