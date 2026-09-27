"""Several PSN accounts per person (#10) at the database layer: linking one
more keeps the others, every one-row-per-person query still returns one row,
and per-account writes touch only their account."""

from __future__ import annotations

import sqlite3

import pytest

from bot.constants import Platform
from bot.db.repo import AchievementRow, Repo, TitleAchievementRow

TG = 7


async def _two_psn(repo: Repo) -> None:
    await repo.ensure_user(TG, "igor")
    await repo.link_platform_account(TG, "psn", "acc-1", "SuperOmsk")
    await repo.link_platform_account(TG, "psn", "acc-2", "OmskSecond")


async def test_a_second_psn_account_is_added_beside_the_first(repo: Repo) -> None:
    await _two_psn(repo)

    links = await repo.platform_links_for(TG, "psn")

    assert [link.external_id for link in links] == ["acc-1", "acc-2"]
    first = await repo.get_platform_link(TG, "psn")
    assert first is not None and first.external_id == "acc-1"


async def test_steam_still_swaps_its_one_account(repo: Repo) -> None:
    await repo.ensure_user(TG, "igor")
    await repo.link_platform_account(TG, "steam", "1", "A")
    await repo.link_platform_account(TG, "steam", "2", "B")

    assert [link.external_id for link in await repo.platform_links_for(TG, "steam")] == ["2"]


async def test_the_index_still_holds_one_account_for_steam(repo: Repo) -> None:
    await repo.ensure_user(TG, "igor")
    await repo.link_platform_account(TG, "steam", "1", "A")
    await repo._ensure_account("steam", "2")

    with pytest.raises(sqlite3.IntegrityError):
        await repo._conn.execute(
            "INSERT INTO account_links (tg_id, platform, external_id, is_active, linked_at)"
            " VALUES (?, 'steam', '2', 1, '2026-09-25')",
            (TG,),
        )


async def test_person_queries_return_the_person_once(repo: Repo) -> None:
    await _two_psn(repo)
    await repo.upsert_chat(-100, "XBOX CG", None)
    await repo.subscribe(-100, TG)

    assert len([row for row in await repo.admin_users() if row.tg_id == TG]) == 1
    assert len(await repo.chat_member_presence(-100)) == 1
    assert len(await repo.chat_subscribers(-100)) == 1


async def test_nickname_and_visibility_writes_touch_one_account(repo: Repo) -> None:
    await _two_psn(repo)

    await repo.update_platform_names(TG, "psn", "Renamed", external_id="acc-2")
    await repo.set_achievements_visible(TG, "psn", False, external_id="acc-2")
    await repo.set_psn_trophy_level(TG, 14, account_id="acc-2")

    first, second = await repo.platform_links_for(TG, "psn")
    assert first.display_name == "SuperOmsk" and second.display_name == "Renamed"
    assert first.achievements_visible is not False and second.achievements_visible is False
    assert first.psn_trophy_level is None and second.psn_trophy_level == 14


async def test_unlinking_one_account_keeps_the_other(repo: Repo) -> None:
    await _two_psn(repo)

    await repo.unlink_account(TG, "psn", "acc-1")

    assert [link.external_id for link in await repo.platform_links_for(TG, "psn")] == ["acc-2"]


async def test_the_platform_switch_covers_every_account(repo: Repo) -> None:
    await _two_psn(repo)

    await repo.set_platform_publishes(TG, "psn", False)

    assert not any(link.publishes for link in await repo.platform_links_for(TG, "psn"))


async def test_checklist_combines_and_deduplicates_across_accounts(repo: Repo) -> None:
    await _two_psn(repo)
    await repo.upsert_title("npwr_test", "Test Game", Platform.PSN)
    await repo.upsert_title_achievements(
        [
            TitleAchievementRow(
                platform=Platform.PSN,
                title_id="npwr_test",
                achievement_id="0",
                name_en="Platinum",
                trophy_type="platinum",
            ),
            TitleAchievementRow(
                platform=Platform.PSN,
                title_id="npwr_test",
                achievement_id="1",
                name_en="Bronze 1",
                trophy_type="bronze",
            ),
            TitleAchievementRow(
                platform=Platform.PSN,
                title_id="npwr_test",
                achievement_id="2",
                name_en="Bronze 2",
                trophy_type="bronze",
            ),
        ],
        complete=True,
    )

    await repo.insert_new_achievements(
        "acc-1",
        [
            AchievementRow(
                title_id="npwr_test",
                achievement_id="1",
                name="Bronze 1",
                description="D",
                icon_url=None,
                unlocked_at="2026-09-20T12:00:00+00:00",
                gamerscore=0,
                rarity_percent=50.0,
                platform=Platform.PSN,
                title_name="Test Game",
                trophy_type="bronze",
            )
        ],
        is_backfill=False,
    )
    await repo.insert_new_achievements(
        "acc-2",
        [
            AchievementRow(
                title_id="npwr_test",
                achievement_id="1",
                name="Bronze 1",
                description="D",
                icon_url=None,
                unlocked_at="2026-09-21T12:00:00+00:00",
                gamerscore=0,
                rarity_percent=50.0,
                platform=Platform.PSN,
                title_name="Test Game",
                trophy_type="bronze",
            ),
            AchievementRow(
                title_id="npwr_test",
                achievement_id="2",
                name="Bronze 2",
                description="D",
                icon_url=None,
                unlocked_at="2026-09-22T12:00:00+00:00",
                gamerscore=0,
                rarity_percent=30.0,
                platform=Platform.PSN,
                title_name="Test Game",
                trophy_type="bronze",
            ),
        ],
        is_backfill=False,
    )

    links = await repo.platform_links_for(TG, "psn")
    xuids = [link.external_id for link in links]
    checklist = await repo.get_title_achievements_with_user_unlocks(
        Platform.PSN, "npwr_test", xuids=xuids
    )

    assert len(checklist) == 3
    t0 = next(item for item in checklist if item.achievement.achievement_id == "0")
    t1 = next(item for item in checklist if item.achievement.achievement_id == "1")
    t2 = next(item for item in checklist if item.achievement.achievement_id == "2")

    assert not t0.is_unlocked and t0.unlocked_at is None
    assert t1.is_unlocked and t1.unlocked_at == "2026-09-20T12:00:00+00:00"
    assert t2.is_unlocked and t2.unlocked_at == "2026-09-22T12:00:00+00:00"

