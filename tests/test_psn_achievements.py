"""services/psn/achievements.py::sync_account (SPEC 9, M-PSN-2, #26) — the
progress-cache gating that decides whether a recently-touched game is worth
a full trophy-detail call, and the per-game "trophies before progress"
ordering that makes an interrupted scan safe. trophy_titles_for_account/
trophies_for_title are faked at the module boundary; the repo is the real
in-memory one, so the actual seen_achievements / psn_title_progress writes
are exercised."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from bot.db.repo import Repo
from bot.services.psn import achievements as psn_achievements_module
from bot.services.psn.achievements import sync_account
from bot.services.psn.client import (
    EarnedTrophy,
    PsnPrivateProfileError,
    PsnTitleUnavailableError,
    PsnTokenDeadError,
    TrophyGroup,
)

TG_ID = 42
ACCOUNT_ID = "acc-1"


@dataclass
class _FakeTitle:
    np_communication_id: str
    title_name: str
    progress: int = 0


def _trophy(trophy_id: int, name: str = "T", group_id: str | None = "default") -> EarnedTrophy:
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
        earned_date_time="2026-09-06T10:00:00+00:00",
        trophy_group_id=group_id,
    )


def _install_fakes(monkeypatch, titles, trophies_by_title, groups_by_title=None):
    async def fake_titles(client, account_id, limit=None):
        return titles

    async def fake_trophies(client, account_id, title):
        result = trophies_by_title.get(title.np_communication_id)
        if isinstance(result, Exception):
            raise result
        return result or []

    async def fake_groups(client, account_id, title):
        return groups_by_title.get(title.np_communication_id, []) if groups_by_title else []

    monkeypatch.setattr(psn_achievements_module, "trophy_titles_for_account", fake_titles)
    monkeypatch.setattr(psn_achievements_module, "trophies_for_title", fake_trophies)
    monkeypatch.setattr(psn_achievements_module, "trophy_groups_for_title", fake_groups)


async def _linked(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_platform_account(TG_ID, "psn", ACCOUNT_ID, "Gamer")


async def _run(repo: Repo, *, is_backfill: bool = False):
    return await sync_account(
        repo,
        object(),  # type: ignore[arg-type]  # the fakes never touch the client
        TG_ID,
        ACCOUNT_ID,
        is_backfill=is_backfill,
        anthropic_auth=object(),  # type: ignore[arg-type]  # none of these trophies have detail text
        translation_client=None,  # bilingual fetch is covered separately, see test_psn_bilingual.py
    )


async def _seen_ids(repo: Repo) -> list[str]:
    cur = await repo._conn.execute(
        "SELECT achievement_id FROM seen_achievements WHERE xuid = ? ORDER BY achievement_id",
        (ACCOUNT_ID,),
    )
    return [row["achievement_id"] for row in await cur.fetchall()]


async def test_a_game_seen_for_the_first_time_is_fetched_and_persisted(
    repo: Repo, monkeypatch
) -> None:
    await _linked(repo)
    title = _FakeTitle("NPWR00001_00", "Some Game", progress=10)
    _install_fakes(monkeypatch, [title], {"NPWR00001_00": [_trophy(1), _trophy(2)]})

    outcome = await _run(repo)

    assert [row.achievement_id for row in outcome.new_rows] == ["1", "2"]
    assert await _seen_ids(repo) == ["1", "2"]
    assert await repo.get_psn_title_progress(ACCOUNT_ID, "NPWR00001_00") == 10


async def test_flat_progress_skips_the_full_detail_call(repo: Repo, monkeypatch) -> None:
    await _linked(repo)
    title = _FakeTitle("NPWR00001_00", "Some Game", progress=50)
    await repo.set_psn_title_progress(ACCOUNT_ID, "NPWR00001_00", 50)
    _install_fakes(monkeypatch, [title], {"NPWR00001_00": Exception("must not be called")})

    outcome = await _run(repo)

    assert outcome.new_rows == []
    assert outcome.scanned == 1


async def test_grown_progress_triggers_a_fresh_fetch(repo: Repo, monkeypatch) -> None:
    await _linked(repo)
    title = _FakeTitle("NPWR00001_00", "Some Game", progress=75)
    await repo.set_psn_title_progress(ACCOUNT_ID, "NPWR00001_00", 50)
    _install_fakes(monkeypatch, [title], {"NPWR00001_00": [_trophy(3)]})

    outcome = await _run(repo)

    assert [row.achievement_id for row in outcome.new_rows] == ["3"]
    assert await repo.get_psn_title_progress(ACCOUNT_ID, "NPWR00001_00") == 75


async def test_a_private_title_is_recorded_and_skipped_not_fatal(repo: Repo, monkeypatch) -> None:
    await _linked(repo)
    hidden = _FakeTitle("NPWR00001_00", "Hidden", progress=10)
    visible = _FakeTitle("NPWR00002_00", "Visible", progress=10)
    _install_fakes(
        monkeypatch,
        [hidden, visible],
        {
            "NPWR00001_00": PsnPrivateProfileError(ACCOUNT_ID),
            "NPWR00002_00": [_trophy(9)],
        },
    )

    outcome = await _run(repo)

    assert [row.achievement_id for row in outcome.new_rows] == ["9"]
    assert outcome.private_title_ids == ["NPWR00001_00"]  # #28: surfaced, not silent
    # Progress still advances for the private one so the failing call isn't
    # repeated every tick — parity with the pre-#26 behaviour.
    assert await repo.get_psn_title_progress(ACCOUNT_ID, "NPWR00001_00") == 10


async def test_a_title_sony_404s_is_skipped_not_fatal(repo: Repo, monkeypatch) -> None:
    await _linked(repo)
    broken = _FakeTitle("NPWR00001_00", "Broken", progress=10)
    visible = _FakeTitle("NPWR00002_00", "Visible", progress=10)
    _install_fakes(
        monkeypatch,
        [broken, visible],
        {
            "NPWR00001_00": PsnTitleUnavailableError(ACCOUNT_ID),
            "NPWR00002_00": [_trophy(9)],
        },
    )

    outcome = await _run(repo)

    assert [row.achievement_id for row in outcome.new_rows] == ["9"]
    assert outcome.private_title_ids == []
    assert await repo.get_psn_title_progress(ACCOUNT_ID, "NPWR00001_00") == 10


async def test_an_unmapped_error_mid_scan_does_not_lose_earlier_titles(
    repo: Repo, monkeypatch
) -> None:
    """#26, the core regression: a game processed successfully before some
    later game raises an *unmapped* exception must keep its trophies AND not
    have the crashing game marked 'seen'. The scan must not abort."""
    await _linked(repo)
    good = _FakeTitle("NPWR00001_00", "Good", progress=10)
    boom = _FakeTitle("NPWR00002_00", "Boom", progress=20)
    _install_fakes(
        monkeypatch,
        [good, boom],
        {
            "NPWR00001_00": [_trophy(1), _trophy(2)],
            "NPWR00002_00": RuntimeError("psnawp did something unexpected"),
        },
    )

    outcome = await _run(repo)

    # The good game's trophies survived — returned and actually persisted.
    assert [row.achievement_id for row in outcome.new_rows] == ["1", "2"]
    assert await _seen_ids(repo) == ["1", "2"]
    assert await repo.get_psn_title_progress(ACCOUNT_ID, "NPWR00001_00") == 10
    # The crashing game is left looking untouched, so the next pass retries
    # it instead of skipping it forever.
    assert await repo.get_psn_title_progress(ACCOUNT_ID, "NPWR00002_00") is None
    assert outcome.unmapped_errors == 1
    assert outcome.scanned == 2


async def test_a_retry_after_an_interruption_picks_up_the_previously_crashed_title(
    repo: Repo, monkeypatch
) -> None:
    await _linked(repo)
    good = _FakeTitle("NPWR00001_00", "Good", progress=10)
    boom = _FakeTitle("NPWR00002_00", "Boom", progress=20)

    _install_fakes(
        monkeypatch,
        [good, boom],
        {
            "NPWR00001_00": [_trophy(1)],
            "NPWR00002_00": RuntimeError("transient"),
        },
    )
    await _run(repo)

    # Second pass: the transient error is gone.
    _install_fakes(
        monkeypatch,
        [good, boom],
        {
            "NPWR00001_00": [_trophy(1)],  # flat since last time — must be skipped
            "NPWR00002_00": [_trophy(5), _trophy(6)],
        },
    )
    outcome = await _run(repo)

    assert [row.achievement_id for row in outcome.new_rows] == ["5", "6"]
    assert await _seen_ids(repo) == ["1", "5", "6"]
    assert await repo.get_psn_title_progress(ACCOUNT_ID, "NPWR00002_00") == 20


async def test_an_account_level_api_error_propagates_but_keeps_earlier_progress(
    repo: Repo, monkeypatch
) -> None:
    """A mapped PsnApiError (dead token, hard rate-limit) is an account-level
    problem — it must propagate so the poller/backfill handle it, not be
    swallowed as "skip this one game". Games already committed this pass stay
    committed."""
    await _linked(repo)
    good = _FakeTitle("NPWR00001_00", "Good", progress=10)
    dead = _FakeTitle("NPWR00002_00", "Dead", progress=20)
    _install_fakes(
        monkeypatch,
        [good, dead],
        {
            "NPWR00001_00": [_trophy(1)],
            "NPWR00002_00": PsnTokenDeadError("service NPSSO expired"),
        },
    )

    with pytest.raises(PsnTokenDeadError):
        await _run(repo)

    assert await _seen_ids(repo) == ["1"]
    assert await repo.get_psn_title_progress(ACCOUNT_ID, "NPWR00001_00") == 10
    assert await repo.get_psn_title_progress(ACCOUNT_ID, "NPWR00002_00") is None


async def test_parsed_trophy_carries_the_tier_rarity_secret_and_platform(
    repo: Repo, monkeypatch
) -> None:
    from psnawp_api.models.trophies.trophy_constants import TrophyType

    await _linked(repo)
    title = _FakeTitle("NPWR00001_00", "Some Game", progress=10)
    trophy = _trophy(1)
    trophy.trophy_type = TrophyType.GOLD
    trophy.trophy_earn_rate = 12.5
    trophy.trophy_hidden = True
    _install_fakes(monkeypatch, [title], {"NPWR00001_00": [trophy]})

    [row] = (await _run(repo)).new_rows

    assert row.platform == "psn"
    assert row.trophy_type == "gold"
    assert row.rarity_percent == 12.5
    assert row.is_secret is True
    assert row.gamerscore == 0


# ------------------------------------------------ per-group progress (#46)


async def test_a_games_groups_are_fetched_once_and_cached(repo: Repo, monkeypatch) -> None:
    """The group names and sizes are a fact about the game, not about the
    person — one request, ever, then `title_groups` answers."""
    await _linked(repo)
    title = _FakeTitle("NPWR00001_00", "Spider-Man", progress=10)
    calls: list[str] = []

    _install_fakes(
        monkeypatch,
        [title],
        {"NPWR00001_00": [_trophy(1)]},
        {"NPWR00001_00": [TrophyGroup("default", "Spider-Man", 51), TrophyGroup("001", "DLC", 7)]},
    )
    real = psn_achievements_module.trophy_groups_for_title

    async def counting(client, account_id, group_title):
        calls.append(group_title.np_communication_id)
        return await real(client, account_id, group_title)

    monkeypatch.setattr(psn_achievements_module, "trophy_groups_for_title", counting)

    await _run(repo)
    assert calls == ["NPWR00001_00"]

    title.progress = 20
    await _run(repo)
    assert calls == ["NPWR00001_00"], "the second pass must not ask Sony again"


async def test_the_trophys_own_group_reaches_the_stored_row(repo: Repo, monkeypatch) -> None:
    await _linked(repo)
    title = _FakeTitle("NPWR00001_00", "Spider-Man", progress=10)
    _install_fakes(
        monkeypatch,
        [title],
        {"NPWR00001_00": [_trophy(1, group_id="default"), _trophy(2, group_id="001")]},
    )

    await _run(repo)

    cur = await repo._conn.execute(
        "SELECT achievement_id, trophy_group_id FROM seen_achievements "
        "WHERE xuid = ? ORDER BY achievement_id",
        (ACCOUNT_ID,),
    )
    assert [(r[0], r[1]) for r in await cur.fetchall()] == [("1", "default"), ("2", "001")]


async def test_a_first_group_aware_pass_is_catch_up_not_news(repo: Repo, monkeypatch) -> None:
    """Until #46 only the base group was ever fetched, so the pass that
    widens a game to all of its groups digs up every DLC trophy at once —
    years of them. Those go out under the 24h cap, not as fresh unlocks."""
    await _linked(repo)
    title = _FakeTitle("NPWR00001_00", "Spider-Man", progress=10)

    # What the old code left behind: stored trophies, none carrying a group.
    _install_fakes(monkeypatch, [title], {"NPWR00001_00": [_trophy(1, group_id=None)]})
    await _run(repo)

    title.progress = 40
    _install_fakes(
        monkeypatch,
        [title],
        {"NPWR00001_00": [_trophy(1, group_id="default"), _trophy(2, group_id="001")]},
    )
    outcome = await _run(repo)

    assert [row.achievement_id for row in outcome.catch_up_rows] == ["2"]
    assert outcome.new_rows == []

    # And only once: the next pass is ordinary polling again.
    title.progress = 60
    _install_fakes(monkeypatch, [title], {"NPWR00001_00": [_trophy(3, group_id="001")]})
    outcome = await _run(repo)
    assert [row.achievement_id for row in outcome.new_rows] == ["3"]
    assert outcome.catch_up_rows == []


async def test_a_game_with_no_stored_trophies_is_not_treated_as_widening(
    repo: Repo, monkeypatch
) -> None:
    """A game nobody has ever polled for this account is simply new — its
    trophies are as fresh as they look, and must not be capped."""
    await _linked(repo)
    title = _FakeTitle("NPWR00002_00", "Stray", progress=10)
    _install_fakes(monkeypatch, [title], {"NPWR00002_00": [_trophy(1)]})

    outcome = await _run(repo)

    assert [row.achievement_id for row in outcome.new_rows] == ["1"]
    assert outcome.catch_up_rows == []


async def test_backfill_never_splits_off_catch_up(repo: Repo, monkeypatch) -> None:
    await _linked(repo)
    title = _FakeTitle("NPWR00001_00", "Spider-Man", progress=10)
    _install_fakes(monkeypatch, [title], {"NPWR00001_00": [_trophy(1, group_id=None)]})
    await _run(repo, is_backfill=True)

    title.progress = 40
    _install_fakes(monkeypatch, [title], {"NPWR00001_00": [_trophy(2, group_id="001")]})
    outcome = await _run(repo, is_backfill=True)

    assert [row.achievement_id for row in outcome.new_rows] == ["2"]
    assert outcome.catch_up_rows == []
