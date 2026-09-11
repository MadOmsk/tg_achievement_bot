"""Admin panel's own /delete_last (a:cdellast:) — the toast names what got
deleted (2026-09-09 user request, `bot_messages.preview`), the redrawn card
underneath stays unchanged. Reverted from an earlier attempt that baked the
"Удалено: ..." text into the card body itself — user feedback: that reads as
permanent clutter, a toast is the right place for something transient."""

from __future__ import annotations

from types import SimpleNamespace

from bot.db.repo import Repo
from bot.handlers.admin import TOAST_PREVIEW_MAX_CHARS, _chat, _toast_preview, chat_delete_last

CHAT_ID = -100888


class _FakeBot:
    def __init__(self, *, fail: bool = False) -> None:
        self.deleted: list[tuple[int, int]] = []
        self._fail = fail

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        if self._fail:
            raise RuntimeError("too old to delete")
        self.deleted.append((chat_id, message_id))


class _FakeCallback:
    """See tests/test_admin_flood.py's own copy — `.message = None` steers
    `_redraw` into its "can't edit, just acknowledge" branch."""

    def __init__(self, data: str) -> None:
        self.data = data
        self.message = None
        self.from_user = SimpleNamespace(id=1)
        self.answers: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args: object, **kwargs: object) -> None:
        self.answers.append((args, kwargs))


def test_toast_preview_passes_a_short_preview_through_unchanged() -> None:
    assert _toast_preview("Иван получает достижение") == "Иван получает достижение"


def test_toast_preview_collapses_newlines_to_spaces() -> None:
    assert _toast_preview("строка один\nстрока два") == "строка один строка два"


def test_toast_preview_truncates_to_the_telegram_safe_length() -> None:
    preview = "x" * 200  # the max `bot_messages.preview` itself can store
    result = _toast_preview(preview)
    assert len(result) == TOAST_PREVIEW_MAX_CHARS
    assert result.endswith("…")


async def test_chat_delete_last_toast_names_the_preview_and_leaves_card_body_alone(
    repo: Repo,
    i18n,
) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.log_bot_message(CHAT_ID, 42, is_system=False, preview="Иван получает достижение")
    bot = _FakeBot()
    callback = _FakeCallback(f"a:cdellast:{CHAT_ID}")

    await chat_delete_last(callback, repo, bot, i18n)  # type: ignore[arg-type]

    assert bot.deleted == [(CHAT_ID, 42)]
    assert callback.answers, "the toast is the only thing carrying the preview"
    toast_args, _kwargs = callback.answers[0]
    assert "Иван получает достижение" in toast_args[0]

    card_text, _markup = await _chat(repo, CHAT_ID, locale="ru")
    assert "Иван получает достижение" not in card_text


async def test_chat_delete_last_falls_back_to_the_generic_toast_without_a_preview(
    repo: Repo,
    i18n,
) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.log_bot_message(CHAT_ID, 42, is_system=False)
    bot = _FakeBot()
    callback = _FakeCallback(f"a:cdellast:{CHAT_ID}")

    await chat_delete_last(callback, repo, bot, i18n)  # type: ignore[arg-type]

    toast_args, _kwargs = callback.answers[0]
    assert "«" not in toast_args[0]


async def test_chat_delete_last_forgets_the_row_even_when_telegram_refuses(
    repo: Repo, i18n
) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.log_bot_message(CHAT_ID, 42, is_system=False, preview="старое сообщение")
    bot = _FakeBot(fail=True)
    callback = _FakeCallback(f"a:cdellast:{CHAT_ID}")

    await chat_delete_last(callback, repo, bot, i18n)  # type: ignore[arg-type]

    assert bot.deleted == []
    assert await repo.last_non_system_bot_message(CHAT_ID) is None


async def test_chat_delete_last_with_nothing_to_delete(repo: Repo, i18n) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    bot = _FakeBot()
    callback = _FakeCallback(f"a:cdellast:{CHAT_ID}")

    await chat_delete_last(callback, repo, bot, i18n)  # type: ignore[arg-type]

    assert bot.deleted == []
    _toast_args, toast_kwargs = callback.answers[0]
    assert toast_kwargs.get("show_alert") is True
