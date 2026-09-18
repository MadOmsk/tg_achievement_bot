"""Mini App repo helpers: show_secrets, month windows, person feed, PSN tiers."""

from __future__ import annotations

from datetime import timedelta

from bot.db.repo import AchievementRow, Repo
from bot.util import utcnow


def _row(
    achievement_id: str,
    *,
    unlocked_at: str,
    icon_url: str | None = None,
    is_secret: bool = False,
) -> AchievementRow:
    return AchievementRow(
        title_id="440",
        achievement_id=achievement_id,
        name=f"Achievement {achievement_id}",
        description="desc",
        icon_url=icon_url,
        unlocked_at=unlocked_at,
        gamerscore=0,
        rarity_percent=12.0,
        platform="steam",
        title_name="TF2",
        is_secret=is_secret,
    )


async def test_show_secrets_defaults_off_and_updates(repo: Repo) -> None:
    await repo.ensure_user(1, "ada")
    settings = await repo.get_user_settings(1)
    assert settings is not None
    assert settings.show_secrets is False

    await repo.update_user_settings(1, show_secrets=1)
    settings = await repo.get_user_settings(1)
    assert settings is not None
    assert settings.show_secrets is True


async def test_person_recent_and_chat_unlock_months(repo: Repo) -> None:
    await repo.ensure_user(10, "ada")
    await repo.link_platform_account(10, "steam", "76561190000000010", "Ada")
    now = utcnow()
    await repo.insert_new_achievements_steam(
        10,
        "76561190000000010",
        [
            _row(
                "a1",
                unlocked_at=(now - timedelta(days=1)).isoformat(timespec="seconds"),
                icon_url="https://example/a1.png",
            ),
            _row(
                "a2",
                unlocked_at=(now - timedelta(days=40)).isoformat(timespec="seconds"),
                is_secret=True,
            ),
        ],
        is_backfill=False,
    )

    feed = await repo.person_recent(10, 10)
    assert len(feed) == 2
    assert feed[0].achievement_id == "a1"
    assert feed[0].icon_url == "https://example/a1.png"
    assert feed[0].title_id == "440"
    assert feed[0].xuid == "76561190000000010"
    assert feed[0].trophy_group_id is None

    since = now - timedelta(days=7)
    recent = await repo.person_recent(10, 10, since=since)
    assert [row.achievement_id for row in recent] == ["a1"]

    await repo.upsert_chat(-100, "club", 10)
    await repo.subscribe(-100, 10)
    months = await repo.chat_unlock_months(-100)
    assert len(months) >= 1
    assert all(len(ym) == 7 and ym[4] == "-" for ym in months)


def _trophy(achievement_id: str, tier: str) -> AchievementRow:
    return AchievementRow(
        title_id="NPWR00001_00",
        achievement_id=achievement_id,
        name=f"Trophy {achievement_id}",
        description=None,
        icon_url=None,
        unlocked_at=utcnow().isoformat(timespec="seconds"),
        gamerscore=0,
        rarity_percent=None,
        platform="psn",
        title_name="A Game",
        trophy_type=tier,
    )


async def test_psn_trophy_tier_counts(repo: Repo) -> None:
    """The panel and the person card both open on this, and both used to
    answer HTTP 500: the method was called in two places and defined in
    none, which no test could notice while none of them called a handler.

    The order is the one both callers unpack — bronze, silver, gold,
    platinum — and getting it backwards would read as a pile of platinums.
    """
    await repo.ensure_user(20, "ada")
    await repo.link_platform_account(20, "psn", "acc-20", "AdaPSN")
    await repo.insert_new_achievements_psn(
        20,
        "acc-20",
        [
            _trophy("t1", "bronze"),
            _trophy("t2", "bronze"),
            _trophy("t3", "bronze"),
            _trophy("t4", "silver"),
            _trophy("t5", "silver"),
            _trophy("t6", "gold"),
            _trophy("t7", "platinum"),
        ],
        is_backfill=False,
    )

    assert await repo.psn_trophy_tier_counts(20) == (3, 2, 1, 1)


async def test_psn_trophy_tier_counts_without_any_trophies(repo: Repo) -> None:
    """SUM over no rows is NULL, not 0 — the caller unpacks four ints and
    would hand `None` straight into the panel's own arithmetic."""
    await repo.ensure_user(21, "grace")
    assert await repo.psn_trophy_tier_counts(21) == (0, 0, 0, 0)
