"""PSN trophies stored before #46 get their group (#115)."""

from __future__ import annotations

from psnawp_api.models.trophies.trophy_constants import PlatformType

from bot.db.repo import AchievementRow, Repo
from bot.poller.psn_trophy_groups import PsnTrophyGroups
from bot.services.psn import achievements as psn_achievements
from bot.services.psn.auth import STATUS_ACTIVE
from bot.services.psn.client import EarnedTrophy, title_ref

TG_ID = 42
ACCOUNT_ID = "acc-1"
GAME = "NPWR20813_00"


def _trophy(trophy_id: int, group_id: str) -> EarnedTrophy:
    return EarnedTrophy(
        trophy_id=trophy_id,
        title_name="Spider-Man Remastered",
        title_icon_url=None,
        trophy_name=f"T{trophy_id}",
        trophy_detail=None,
        trophy_icon_url=None,
        trophy_type=None,  # type: ignore[arg-type]
        trophy_hidden=False,
        trophy_rarity=None,
        trophy_earn_rate=None,
        earned_date_time="2026-08-01T10:00:00+00:00",
        trophy_group_id=group_id,
    )


def _row(achievement_id: str, group_id: str | None) -> AchievementRow:
    return AchievementRow(
        title_id=GAME,
        achievement_id=achievement_id,
        name=f"T{achievement_id}",
        description=None,
        icon_url=None,
        unlocked_at="2026-08-01T10:00:00+00:00",
        gamerscore=0,
        rarity_percent=None,
        platform="psn",
        trophy_group_id=group_id,
    )


async def _stored(repo: Repo) -> dict[str, tuple[str | None, int]]:
    cursor = await repo._conn.execute(
        "SELECT achievement_id, trophy_group_id, is_backfill FROM seen_achievements"
    )
    return {r[0]: (r[1], r[2]) for r in await cursor.fetchall()}


async def _held_game(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_platform_account(TG_ID, "psn", ACCOUNT_ID, "Gamer")
    await repo.upsert_title(GAME, "Spider-Man Remastered", "psn", platforms='["PS5"]')
    # 1 and 2 stored before #46 (no group), 3 since (grouped)
    await repo.insert_new_achievements_psn(
        TG_ID, ACCOUNT_ID, [_row("1", None), _row("2", None), _row("3", "005")], is_backfill=False
    )


def _sony_says(monkeypatch, trophies: list[EarnedTrophy], seen: list | None = None) -> None:
    async def fake(client, account_id, title, *, earned_only=True):
        if seen is not None:
            seen.append((account_id, title.np_communication_id, set(title.title_platform)))
        return trophies

    monkeypatch.setattr(psn_achievements, "trophies_for_title", fake)


async def test_old_trophies_get_their_group_and_missing_dlc_is_stored_silently(
    repo: Repo, monkeypatch
) -> None:
    await _held_game(repo)
    _sony_says(
        monkeypatch,
        [_trophy(1, "default"), _trophy(2, "default"), _trophy(3, "005"), _trophy(4, "001")],
    )

    changed = await psn_achievements.regroup_title(
        repo,
        object(),
        TG_ID,
        ACCOUNT_ID,
        title_ref(GAME, ["PS5"]),  # type: ignore[arg-type]
    )

    assert changed == 3  # two regrouped, one added
    stored = await _stored(repo)
    assert stored["1"] == ("default", 0)
    assert stored["2"] == ("default", 0)
    assert stored["3"] == ("005", 0)
    assert stored["4"] == ("001", 1)  # never fetched before #46: history, not news


async def test_the_walker_asks_once_per_game_and_then_leaves_it(repo: Repo, monkeypatch) -> None:
    await _held_game(repo)
    asked: list = []
    _sony_says(monkeypatch, [_trophy(1, "default"), _trophy(2, "default")], asked)

    class _Auth:
        async def status(self):
            return STATUS_ACTIVE

        async def get_client(self):
            return object()

    walker = PsnTrophyGroups(repo, _Auth())  # type: ignore[arg-type]
    await walker.tick()
    await walker.tick()

    assert asked == [(ACCOUNT_ID, GAME, {PlatformType.PS5})]
    assert await repo.psn_titles_missing_groups(10) == []


async def test_an_unlinked_account_is_not_walked(repo: Repo) -> None:
    await _held_game(repo)
    await repo.unlink_platform_account(TG_ID, "psn")

    assert await repo.psn_titles_missing_groups(10) == []


def test_title_ref_picks_the_trophy_service_of_the_newest_console() -> None:
    assert title_ref("X", ["PS5", "PSPC"]).title_platform == {PlatformType.PS5}
    assert title_ref("X", ["PS3", "PS4", "PSVITA"]).title_platform == {PlatformType.PS4}
    assert title_ref("X", ["PSVITA"]).title_platform == {PlatformType.PS_VITA}
    assert title_ref("X", None).title_platform == frozenset()


async def test_a_game_with_progress_and_nothing_stored_is_filled_in(
    repo: Repo, monkeypatch
) -> None:
    """The scan advanced progress when the fetch failed, so it never asks
    again (#120): the walker does, and stores what it finds as history."""
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_platform_account(TG_ID, "psn", ACCOUNT_ID, "Gamer")
    await repo.set_psn_title_progress(ACCOUNT_ID, "NPWR22032_00", 1)
    await repo.set_psn_title_progress(ACCOUNT_ID, "NPWR00000_00", 0)  # nothing earned

    pending = await repo.psn_titles_missing_groups(10)
    assert [(p[1], p[2]) for p in pending] == [(ACCOUNT_ID, "NPWR22032_00")]

    _sony_says(monkeypatch, [_trophy(7, "default")])
    changed = await psn_achievements.regroup_title(
        repo,
        object(),
        TG_ID,
        ACCOUNT_ID,
        title_ref("NPWR22032_00", ["PS5"]),  # type: ignore[arg-type]
    )

    assert changed == 1
    assert (await _stored(repo))["7"] == ("default", 1)
    assert await repo.psn_titles_missing_groups(10) == []
