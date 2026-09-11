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
from bot.handlers.admin import _chat, chat_locale_toggle
from bot.handlers.keyboards import locale_name, next_locale, panel_keyboard
from bot.handlers.panel import panel_toggle_locale
from bot.i18n import AVAILABLE_LOCALES, build_i18n_context

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
    assert any(label.startswith("Язык: Русский") for label in labels)


async def test_the_panel_keyboard_is_english_for_an_english_context() -> None:
    english = await build_i18n_context("en")
    markup = panel_keyboard(180, english)
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert any(label.startswith("Language: English") for label in labels)


async def test_the_panel_toggle_flips_the_persons_own_locale(repo: Repo, i18n: I18nContext) -> None:
    await repo.ensure_user(TG_ID)
    callback = _FakeCallback("panel:locale")

    await panel_toggle_locale(callback, repo, i18n)  # type: ignore[arg-type]

    assert await repo.user_locale(TG_ID) == "en"
    assert callback.answers == ["English"]


async def test_the_panel_toggle_comes_back(repo: Repo, i18n: I18nContext) -> None:
    await repo.ensure_user(TG_ID)
    await repo.update_user_settings(TG_ID, locale="en")

    await panel_toggle_locale(_FakeCallback("panel:locale"), repo, i18n)  # type: ignore[arg-type]

    assert await repo.user_locale(TG_ID) == "ru"


async def test_the_panel_toggle_leaves_every_chat_alone(repo: Repo, i18n: I18nContext) -> None:
    """A personal choice must not move what a group sees — that is the whole
    reason these are two settings."""
    await repo.ensure_user(TG_ID)
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", TG_ID)

    await panel_toggle_locale(_FakeCallback("panel:locale"), repo, i18n)  # type: ignore[arg-type]

    assert await repo.user_locale(TG_ID) == "en"
    assert await repo.chat_locale(CHAT_ID) == "ru"


# ----------------------------------------------------- the chat card toggle


async def test_the_chat_card_shows_the_language_and_its_button(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", TG_ID)

    text, markup = await _chat(repo, CHAT_ID, locale="ru")

    assert "Язык:         Русский" in text
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert "Язык: Русский" in labels


async def test_the_chat_toggle_flips_the_chats_locale(repo: Repo, i18n: I18nContext) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", TG_ID)
    callback = _FakeCallback(f"a:cloc:{CHAT_ID}")

    await chat_locale_toggle(callback, repo, i18n)  # type: ignore[arg-type]

    assert await repo.chat_locale(CHAT_ID) == "en"

    text, _markup = await _chat(repo, CHAT_ID, locale="ru")
    # The card itself still renders in the super-admin's language; only the
    # value it reports has changed.
    assert "Язык:         English" in text


async def test_the_chat_toggle_leaves_the_super_admin_alone(repo: Repo, i18n: I18nContext) -> None:
    await repo.ensure_user(TG_ID)
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", TG_ID)

    await chat_locale_toggle(_FakeCallback(f"a:cloc:{CHAT_ID}"), repo, i18n)  # type: ignore[arg-type]

    assert await repo.chat_locale(CHAT_ID) == "en"
    assert await repo.user_locale(TG_ID) == "ru"


async def test_the_chat_toggle_survives_a_missing_chat(repo: Repo, i18n: I18nContext) -> None:
    callback = _FakeCallback("a:cloc:-1")

    await chat_locale_toggle(callback, repo, i18n)  # type: ignore[arg-type]

    assert callback.answers == ["Чат не найден"]
