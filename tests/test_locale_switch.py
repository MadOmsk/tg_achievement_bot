"""The two controls that actually let someone pick a language (#48).

Everything else in this feature was invisible until these existed: a
personal toggle in /panel, and the chat's own one on the super-admin's chat
card. The two are deliberately separate settings — Telegram cannot render
one group message differently per viewer, so a chat needs one shared answer
while a DM can be personal.
"""

from __future__ import annotations

from aiogram_i18n import I18nContext

from bot.db.repo import Repo
from bot.handlers.admin import chat_setting_open, chat_setting_pick
from bot.handlers.panel import panel_toggle_locale
from bot.i18n import AVAILABLE_LOCALES, build_i18n_context
from bot.views.admin import render_chat_card
from bot.views.keyboards import locale_name, next_locale, panel_keyboard

CHAT_ID = -100800
TG_ID = 8008


class _FakeCallback:
    """Minimal CallbackQuery stand-in — `.message` is not a real Message, so
    the redraw path takes its "can't edit, just acknowledge" branch."""

    def __init__(self, data: str, tg_id: int = TG_ID) -> None:
        self.data = data
        self.message = None
        self.from_user = type("User", (), {"id": tg_id})()
        self.answers: list[str | None] = []

    async def answer(self, text: str | None = None, **_kwargs: object) -> None:
        self.answers.append(text)


# ------------------------------------------------------------------ cycling


def test_next_locale_cycles_through_every_shipped_locale() -> None:
    seen = []
    current = AVAILABLE_LOCALES[0]
    for _ in AVAILABLE_LOCALES:
        seen.append(current)
        current = next_locale(current)
    assert seen == list(AVAILABLE_LOCALES)
    assert current == AVAILABLE_LOCALES[0]  # back where it started


def test_next_locale_recovers_from_an_unknown_value() -> None:
    assert next_locale("klingon") == next_locale(AVAILABLE_LOCALES[0])


def test_language_names_are_endonyms() -> None:
    """Always written in their own language, never translated: the point of
    a language picker is that someone who cannot read the current interface
    can still find their own language in it."""
    assert locale_name("ru") == "Русский"
    assert locale_name("en") == "English"


# --------------------------------------------------------- the panel toggle


async def test_the_panel_offers_a_language_button(i18n: I18nContext) -> None:
    markup = panel_keyboard(180, i18n)
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert any(label.startswith("🌐 Язык: Русский") for label in labels)


async def test_the_panel_keyboard_is_english_for_an_english_context() -> None:
    english = await build_i18n_context("en")
    markup = panel_keyboard(180, english)
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert any(label.startswith("🌐 Language: English") for label in labels)


async def test_the_panel_toggle_flips_the_persons_own_locale(repo: Repo, i18n: I18nContext) -> None:
    await repo.ensure_user(TG_ID)
    callback = _FakeCallback("panel:locale")

    await panel_toggle_locale(callback, repo, i18n)  # type: ignore[arg-type]

    assert await repo.user_locale(await repo.person_id(TG_ID)) == "en"
    assert callback.answers == ["English"]


async def test_the_panel_toggle_comes_back(repo: Repo, i18n: I18nContext) -> None:
    await repo.ensure_user(TG_ID)
    await repo.update_user_settings(await repo.person_id(TG_ID), locale="en")

    await panel_toggle_locale(_FakeCallback("panel:locale"), repo, i18n)  # type: ignore[arg-type]

    assert await repo.user_locale(await repo.person_id(TG_ID)) == "ru"


async def test_the_panel_toggle_leaves_every_chat_alone(repo: Repo, i18n: I18nContext) -> None:
    """A personal choice must not move what a group sees — that is the whole
    reason these are two settings."""
    await repo.ensure_user(TG_ID)
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", TG_ID)

    await panel_toggle_locale(_FakeCallback("panel:locale"), repo, i18n)  # type: ignore[arg-type]

    assert await repo.user_locale(await repo.person_id(TG_ID)) == "en"
    assert await repo.chat_locale(CHAT_ID) == "ru"


# ------------------------------------------------- the chat's language

# A setting of the registry (#176), in the chat card's «Основное» group: its
# button opens the languages, a pick sets the chat's.


async def test_the_chat_card_shows_the_language_in_its_main_group(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", TG_ID)

    text, _markup = await render_chat_card(repo, CHAT_ID, locale="ru")
    _text, group = await render_chat_card(repo, CHAT_ID, locale="ru", section="main")

    assert "Язык:         Русский" in text
    labels = [button.text for row in group.inline_keyboard for button in row]
    assert "Язык: Русский ▸" in labels


async def test_picking_a_language_sets_the_chats_own(repo: Repo, i18n: I18nContext) -> None:
    await repo.ensure_user(TG_ID)
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", TG_ID)
    english = AVAILABLE_LOCALES.index("en")

    await chat_setting_pick(  # type: ignore[arg-type]
        _FakeCallback(f"a:csv:{CHAT_ID}:locale:{english}"), repo, i18n
    )

    assert await repo.chat_locale(CHAT_ID) == "en"
    # The card itself still renders in the super-admin's language; only the
    # value it reports has changed — and the super-admin's own is untouched.
    text, _markup = await render_chat_card(repo, CHAT_ID, locale="ru")
    assert "Язык:         English" in text
    assert await repo.user_locale(await repo.person_id(TG_ID)) == "ru"


async def test_a_missing_chat_is_said_so(repo: Repo, i18n: I18nContext) -> None:
    callback = _FakeCallback("a:cs:-1:locale")

    await chat_setting_open(callback, repo, i18n)  # type: ignore[arg-type]

    assert callback.answers == ["Чат не найден"]


# ------------------------------------------------- the chat card's groups


async def test_the_card_opens_its_groups_and_the_messages(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", TG_ID)

    _text, markup = await render_chat_card(repo, CHAT_ID, locale="ru")
    datas = [button.callback_data for row in markup.inline_keyboard for button in row]

    for group in ("main", "publishing", "summary", "flood"):
        assert f"a:cg:{CHAT_ID}:{group}" in datas
    assert f"a:mdel:{CHAT_ID}" in datas
    # and none of what they contain is on the card itself
    assert f"a:cs:{CHAT_ID}:daily_summary_time" not in datas
    assert f"a:cdellast:{CHAT_ID}" not in datas


async def test_every_group_leads_back_to_the_card(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", TG_ID)

    for section in ("main", "publishing", "summary", "flood", "messages"):
        text, markup = await render_chat_card(repo, CHAT_ID, locale="ru", section=section)
        datas = [button.callback_data for row in markup.inline_keyboard for button in row]
        assert f"a:chat:{CHAT_ID}" in datas, section
        # The card's own text stays put on every group, so the chat's state is
        # still readable while its settings are being changed.
        assert "Гейминг-чат" in text


async def test_the_messages_submenu_holds_every_wipe_action(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", TG_ID)

    _text, markup = await render_chat_card(repo, CHAT_ID, locale="ru", section="messages")
    datas = [button.callback_data for row in markup.inline_keyboard for button in row]

    for action in ("cdellast", "cwipe", "cswipe", "cswipeall"):
        assert f"a:{action}:{CHAT_ID}" in datas
