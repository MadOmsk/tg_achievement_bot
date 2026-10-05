"""The status message while an account's history is read (handlers/backfill.py,
owner 2026-09-30): one message, redrawn as the backfill reports, ending as
the result — or as a failure with a retry button."""

from __future__ import annotations

from types import SimpleNamespace

from bot.db.repo import Repo
from bot.handlers import backfill
from bot.poller.psn_fetcher import PsnBackfillResult
from bot.services.steam.client import SteamGameDetailsPrivateError

TG_ID = 7


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.edits: list[tuple[str, object]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: object):
        self.sent.append(text)
        return SimpleNamespace(chat=SimpleNamespace(id=chat_id), message_id=100)

    async def edit_message_text(self, text: str, **kwargs: object) -> None:
        self.edits.append((text, kwargs.get("reply_markup")))


def _callbacks(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]


class FakeSteam:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result, self.error = result, error

    async def backfill(self, tg_id, steam_id, *, progress=None):
        if progress is not None:
            await progress(0, 3, 0)
            await progress(1, 3, 10)  # inside the interval: not drawn
            await progress(3, 3, 42)  # the last one always is
        if self.error:
            raise self.error
        return self.result


async def test_one_message_that_ends_as_the_result(repo: Repo, monkeypatch) -> None:
    await repo.ensure_user(TG_ID, "igor")
    bot = FakeBot()

    await backfill.run_steam(bot, FakeSteam(result=42), repo, TG_ID, "1")  # type: ignore[arg-type]

    assert len(bot.sent) == 1 and "Steam" in bot.sent[0]  # one message, then edits
    texts = [text for text, _ in bot.edits]
    assert any("0 из 3 игр" in text for text in texts)
    assert not any("1 из 3" in text for text in texts)  # throttled
    final, markup = bot.edits[-1]
    assert final.startswith("✅") and "42 достижения" in final and "из 3 игр" in final
    assert _callbacks(markup) == ["panel:refresh"]


async def test_a_failure_offers_a_retry_on_the_same_message(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    bot = FakeBot()

    await backfill.run_steam(bot, FakeSteam(error=RuntimeError("boom")), repo, TG_ID, "1")  # type: ignore[arg-type]

    final, markup = bot.edits[-1]
    assert final.startswith("⚠️")
    assert _callbacks(markup) == ["bf:steam", "panel:refresh"]


async def test_hidden_steam_game_details_ask_for_a_recheck(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    bot = FakeBot()

    await backfill.run_steam(
        bot,
        FakeSteam(error=SteamGameDetailsPrivateError("x")),
        repo,
        TG_ID,
        "1",  # type: ignore[arg-type]
    )

    final, markup = bot.edits[-1]
    assert "Игровая статистика" in final and "/connect_steam" not in final
    assert markup.inline_keyboard[0][0].text == "🔄 Проверить снова"


class FakePsn:
    def __init__(self, result: PsnBackfillResult) -> None:
        self.result = result

    async def backfill(self, tg_id, account_id, *, progress=None):
        if progress is not None:
            await progress(5, 5, self.result.stored)
        return self.result


async def test_psn_names_the_account_and_notes_private_games(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    bot = FakeBot()
    result = PsnBackfillResult(stored=21, private_title_ids=["a", "b"], games=5)

    await backfill.run_psn(bot, FakePsn(result), repo, TG_ID, "acc-1", "SuperOmsk")  # type: ignore[arg-type]

    final, _markup = bot.edits[-1]
    assert "PSN (SuperOmsk)" in final and "21 трофей" in final
    assert "У 2 игр закрыта приватность" in final


async def test_hidden_psn_trophies_ask_for_a_recheck_of_that_account(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    bot = FakeBot()

    await backfill.run_psn(
        bot,
        FakePsn(PsnBackfillResult(visible=False)),
        repo,
        TG_ID,
        "acc-1",
        "SuperOmsk",  # type: ignore[arg-type]
    )

    final, markup = bot.edits[-1]
    assert "скрыты" in final
    assert _callbacks(markup) == ["bf:psn:acc-1", "panel:refresh"]
