"""Steam game names for games nobody plays any more (#61).

Everything else fills in on the next poll of a game; a game finished a year
ago is never polled again, and the Steam Web API answers with one name
whatever `l=` says — only the storefront knows the other one.
"""

from __future__ import annotations

from bot.db.repo import Repo
from bot.poller import steam_localization as module
from bot.poller.steam_localization import SteamLocalization

APPID = "2389240"  # G.O.P.O.T.A — "Г.О.П.О.Т.А" on its Russian store page


def _store(answers: dict[tuple[str, str], str | None], calls: list[tuple[str, str]]):
    async def fake_store_name(appid: str, language: str) -> str | None:
        calls.append((appid, language))
        return answers.get((appid, language))

    return fake_store_name


async def test_a_game_nobody_plays_still_gets_its_russian_name(repo: Repo, monkeypatch) -> None:
    await repo.upsert_title(APPID, "G.O.P.O.T.A", "steam")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        module,
        "store_name",
        _store({(APPID, "russian"): "Г.О.П.О.Т.А", (APPID, "english"): "G.O.P.O.T.A"}, calls),
    )

    await SteamLocalization(repo).tick()

    assert await repo.title_names([APPID]) == {APPID: ("Г.О.П.О.Т.А", "G.O.P.O.T.A")}
    assert calls == [(APPID, "russian"), (APPID, "english")]


async def test_a_game_already_localized_is_not_asked_again(repo: Repo, monkeypatch) -> None:
    await repo.upsert_title(APPID, "G.O.P.O.T.A", "steam")
    await repo.set_title_names(APPID, "Г.О.П.О.Т.А", "G.O.P.O.T.A")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(module, "store_name", _store({}, calls))

    await SteamLocalization(repo).tick()

    assert calls == []


async def test_a_game_the_store_will_not_answer_for_is_dropped_for_this_process(
    repo: Repo, monkeypatch
) -> None:
    """Delisted, region-locked, or simply gone. Without this the same appid
    would be asked about every minute forever, against a service that owes us
    nothing."""
    await repo.upsert_title(APPID, "Gone", "steam")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(module, "store_name", _store({}, calls))
    job = SteamLocalization(repo)

    await job.tick()
    await job.tick()

    assert calls == [(APPID, "russian"), (APPID, "english")]


async def test_only_steam_titles_are_walked(repo: Repo, monkeypatch) -> None:
    """Xbox and PSN get their names from responses the bot already makes; the
    storefront is Steam's own gap."""
    await repo.upsert_title("t-xbox", "Halo", "xbox_modern")
    await repo.upsert_title("NPWR1", "Spider-Man", "psn")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(module, "store_name", _store({}, calls))

    await SteamLocalization(repo).tick()

    assert calls == []


async def test_a_tick_takes_only_its_own_bite(repo: Repo, monkeypatch) -> None:
    for index in range(5):
        await repo.upsert_title(f"app-{index}", f"Game {index}", "steam")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        module,
        "store_name",
        _store(
            {(f"app-{i}", lang): f"Игра {i}" for i in range(5) for lang in ("russian", "english")},
            calls,
        ),
    )

    await SteamLocalization(repo, titles_per_tick=2).tick()

    assert len({appid for appid, _ in calls}) == 2
