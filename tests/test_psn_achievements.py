"""services/psn/achievements.py::fetch_unlocked (SPEC 9, M-PSN-2) — the
progress-cache gating that decides whether a recently-touched game is worth
a full trophy-detail call this poll. trophy_titles_for_account/
trophies_for_title are faked at the module boundary, same as the rest of
this project's poller-facing services fake their client layer."""

from __future__ import annotations

from dataclasses import dataclass

from bot.db.repo import Repo
from bot.services.psn import achievements as psn_achievements_module
from bot.services.psn.achievements import fetch_unlocked
from bot.services.psn.client import EarnedTrophy, PsnPrivateProfileError, PsnTitleUnavailableError

ACCOUNT_ID = "acc-1"


@dataclass
class _FakeTitle:
    np_communication_id: str
    title_name: str
    progress: int = 0


def _trophy(trophy_id: int, name: str = "T") -> EarnedTrophy:
    return EarnedTrophy(
        trophy_id=trophy_id,
        title_name="Some Game",
        title_icon_url=None,
        trophy_name=name,
        trophy_detail=None,
        trophy_icon_url=None,
        trophy_type=None,  # type: ignore[arg-type]
        trophy_hidden=False,
        trophy_rarity=None,
        trophy_earn_rate=None,
        earned_date_time=None,
    )


def _install_fakes(monkeypatch, titles, trophies_by_title):
    async def fake_titles(client, account_id, limit=None):
        return titles

    async def fake_trophies(client, account_id, title):
        result = trophies_by_title.get(title.np_communication_id)
        if isinstance(result, Exception):
            raise result
        return result or []

    monkeypatch.setattr(psn_achievements_module, "trophy_titles_for_account", fake_titles)
    monkeypatch.setattr(psn_achievements_module, "trophies_for_title", fake_trophies)


async def test_a_game_seen_for_the_first_time_is_fetched_in_full(
    repo: Repo, monkeypatch
) -> None:
    title = _FakeTitle("NPWR00001_00", "Some Game", progress=10)
    _install_fakes(monkeypatch, [title], {"NPWR00001_00": [_trophy(1), _trophy(2)]})

    result = await fetch_unlocked(repo, object(), ACCOUNT_ID)  # type: ignore[arg-type]

    assert [item.achievement_id for item in result] == ["1", "2"]
    assert await repo.get_psn_title_progress(ACCOUNT_ID, "NPWR00001_00") == 10


async def test_flat_progress_skips_the_full_detail_call(repo: Repo, monkeypatch) -> None:
    title = _FakeTitle("NPWR00001_00", "Some Game", progress=50)
    await repo.set_psn_title_progress(ACCOUNT_ID, "NPWR00001_00", 50)
    _install_fakes(
        monkeypatch, [title], {"NPWR00001_00": Exception("must not be called")}
    )

    result = await fetch_unlocked(repo, object(), ACCOUNT_ID)  # type: ignore[arg-type]

    assert result == []


async def test_grown_progress_triggers_a_fresh_fetch(repo: Repo, monkeypatch) -> None:
    title = _FakeTitle("NPWR00001_00", "Some Game", progress=75)
    await repo.set_psn_title_progress(ACCOUNT_ID, "NPWR00001_00", 50)
    _install_fakes(monkeypatch, [title], {"NPWR00001_00": [_trophy(3)]})

    result = await fetch_unlocked(repo, object(), ACCOUNT_ID)  # type: ignore[arg-type]

    assert [item.achievement_id for item in result] == ["3"]
    assert await repo.get_psn_title_progress(ACCOUNT_ID, "NPWR00001_00") == 75


async def test_a_private_title_is_skipped_not_fatal(repo: Repo, monkeypatch) -> None:
    visible = _FakeTitle("NPWR00002_00", "Visible", progress=10)
    hidden = _FakeTitle("NPWR00001_00", "Hidden", progress=10)
    _install_fakes(
        monkeypatch,
        [hidden, visible],
        {
            "NPWR00001_00": PsnPrivateProfileError(ACCOUNT_ID),
            "NPWR00002_00": [_trophy(9)],
        },
    )

    result = await fetch_unlocked(repo, object(), ACCOUNT_ID)  # type: ignore[arg-type]

    assert [item.achievement_id for item in result] == ["9"]


async def test_a_title_sony_404s_is_skipped_not_fatal(repo: Repo, monkeypatch) -> None:
    """The actual production bug (found live 2026-09-06): one game 404ing
    on Sony's own side used to take down the entire backfill — every retry
    hit the same game and failed identically. Same isolation as a private
    title above, just a different upstream error."""
    visible = _FakeTitle("NPWR00002_00", "Visible", progress=10)
    broken = _FakeTitle("NPWR00001_00", "Broken", progress=10)
    _install_fakes(
        monkeypatch,
        [broken, visible],
        {
            "NPWR00001_00": PsnTitleUnavailableError(ACCOUNT_ID),
            "NPWR00002_00": [_trophy(9)],
        },
    )

    result = await fetch_unlocked(repo, object(), ACCOUNT_ID)  # type: ignore[arg-type]

    assert [item.achievement_id for item in result] == ["9"]


async def test_parsed_achievement_carries_the_tier_and_platform(
    repo: Repo, monkeypatch
) -> None:
    from psnawp_api.models.trophies.trophy_constants import TrophyType

    title = _FakeTitle("NPWR00001_00", "Some Game", progress=10)
    trophy = _trophy(1)
    trophy.trophy_type = TrophyType.GOLD
    trophy.trophy_earn_rate = 12.5
    trophy.trophy_hidden = True
    _install_fakes(monkeypatch, [title], {"NPWR00001_00": [trophy]})

    [item] = await fetch_unlocked(repo, object(), ACCOUNT_ID)  # type: ignore[arg-type]

    assert item.platform == "psn"
    assert item.trophy_type == "gold"
    assert item.rarity_percent == 12.5
    assert item.is_secret is True
    assert item.gamerscore == 0
