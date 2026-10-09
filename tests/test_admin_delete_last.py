"""The super-admin's «delete the last one» on a chat — an action of the
registry (#176, services/admin_actions.py). The toast names what got deleted
(2026-09-09 user request, `bot_messages.preview`); the redrawn card stays
unchanged — a toast is the place for something transient."""

from __future__ import annotations

from types import SimpleNamespace

from bot.db.repo import Repo
from bot.handlers.admin import admin_action
from bot.services.admin_actions import toast_preview
from bot.services.admin_settings import TOAST_PREVIEW_MAX_CHARS
from bot.views.admin import render_chat_card

CHAT_ID = -100888
DELETE_LAST = f"a:x:c:{CHAT_ID}:delete_last:0"


class _FakeBot:
    def __init__(self, *, fail: bool = False) -> None:
        self.deleted: list[tuple[int, int]] = []
        self._fail = fail

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        if self._fail:
            raise RuntimeError("too old to delete")
        self.deleted.append((chat_id, message_id))


class _FakeCallback:
    """`.message = None` steers `_redraw` into its "can't edit, just
    acknowledge" branch."""

    def __init__(self, data: str) -> None:
        self.data = data
        self.message = None
        self.from_user = SimpleNamespace(id=1)
        self.answers: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args: object, **kwargs: object) -> None:
        self.answers.append((args, kwargs))


async def _tap(callback, repo, bot, settings, i18n) -> None:
    await admin_action(callback, repo, bot, None, None, None, settings, i18n)  # type: ignore[arg-type]


def test_toast_preview_passes_a_short_preview_through_unchanged() -> None:
    assert toast_preview("Иван получает достижение") == "Иван получает достижение"


def test_toast_preview_collapses_newlines_to_spaces() -> None:
    assert toast_preview("строка один\nстрока два") == "строка один строка два"


def test_toast_preview_truncates_to_the_telegram_safe_length() -> None:
    result = toast_preview("x" * 200)  # the most `bot_messages.preview` stores
    assert len(result) == TOAST_PREVIEW_MAX_CHARS
    assert result.endswith("…")


async def test_the_toast_names_the_preview_and_the_card_stays(repo: Repo, settings, i18n) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.log_bot_message(CHAT_ID, 42, is_system=False, preview="Иван получает достижение")
    bot = _FakeBot()
    callback = _FakeCallback(DELETE_LAST)

    await _tap(callback, repo, bot, settings, i18n)

    assert bot.deleted == [(CHAT_ID, 42)]
    toast_args, _kwargs = callback.answers[0]
    assert "Иван получает достижение" in toast_args[0]
    card_text, _markup = await render_chat_card(repo, CHAT_ID, locale="ru")
    assert "Иван получает достижение" not in card_text


async def test_no_preview_gives_the_plain_toast(repo: Repo, settings, i18n) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.log_bot_message(CHAT_ID, 42, is_system=False)
    callback = _FakeCallback(DELETE_LAST)

    await _tap(callback, repo, _FakeBot(), settings, i18n)

    toast_args, _kwargs = callback.answers[0]
    assert "«" not in toast_args[0]


async def test_the_row_is_forgotten_even_when_telegram_refuses(repo: Repo, settings, i18n) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.log_bot_message(CHAT_ID, 42, is_system=False, preview="старое сообщение")
    bot = _FakeBot(fail=True)

    await _tap(_FakeCallback(DELETE_LAST), repo, bot, settings, i18n)

    assert bot.deleted == []
    assert await repo.last_deletable_bot_message(CHAT_ID) is None


async def test_nothing_to_delete_is_an_alert(repo: Repo, settings, i18n) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    callback = _FakeCallback(DELETE_LAST)

    await _tap(callback, repo, _FakeBot(), settings, i18n)

    _toast_args, toast_kwargs = callback.answers[0]
    assert toast_kwargs.get("show_alert") is True
