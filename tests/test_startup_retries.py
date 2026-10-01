"""Start-up survives Telegram being unreachable for a moment (2026-10-01:
the dev server died on bot.me() and, with the database left open, hung as a
process that looked alive)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import GetMe

from bot import main as bot_main


class _FlakyBot:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    async def me(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise TelegramNetworkError(method=GetMe(), message="timeout")
        return "me"


async def test_me_is_retried_until_telegram_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(bot_main.asyncio, "sleep", _no_sleep)
    bot = _FlakyBot(failures=3)
    assert await bot_main._me_with_retries(bot) == "me"  # type: ignore[arg-type]
    assert bot.calls == 4


async def test_me_gives_up_after_the_last_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(bot_main.asyncio, "sleep", _no_sleep)
    bot = _FlakyBot(failures=99)
    with pytest.raises(TelegramNetworkError):
        await bot_main._me_with_retries(bot)  # type: ignore[arg-type]
    assert bot.calls == len(bot_main._ME_RETRY_DELAYS) + 1


def test_a_failed_run_exits_the_process(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Not left waiting on a thread nobody closes: os._exit(1), so systemd
    restarts it."""
    exits: list[int] = []

    async def _boom(_settings: object) -> None:
        raise RuntimeError("start-up failed")

    monkeypatch.setattr(bot_main, "run", _boom)
    monkeypatch.setattr(bot_main.os, "_exit", lambda code: exits.append(code))
    monkeypatch.setattr(bot_main, "setup_logging", lambda _level: None)
    # Its own lock file: never the real bot's, which a running bot holds.
    monkeypatch.setattr(
        bot_main,
        "get_settings",
        lambda: SimpleNamespace(log_level="INFO", db_path=tmp_path / "bot.db"),
    )
    bot_main.main()
    assert exits == [1]
