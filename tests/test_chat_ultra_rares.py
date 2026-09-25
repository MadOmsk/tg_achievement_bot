from __future__ import annotations

from datetime import timedelta

from bot.db.repo import AchievementRow, Repo
from bot.util import utcnow

CHAT_ID = -100700
TG_ID = 7
XUID = "xuid-ultra"


async def test_chat_ultra_rares_takes_all_under_half_percent_for_the_month(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "hunter")
    await repo.link_xbox_account(TG_ID, XUID, "Hunter", 0)
    await repo.upsert_chat(CHAT_ID, "Chat", TG_ID)
    await repo.subscribe(CHAT_ID, TG_ID)
    now = utcnow()
    await repo.insert_new_achievements(
        XUID,
        [
            AchievementRow(
                title_id="t1",
                achievement_id="u1",
                name="Ultra",
                description=None,
                icon_url=None,
                unlocked_at=(now - timedelta(days=2)).isoformat(),
                gamerscore=10,
                rarity_percent=None,
                platform="xbox_modern",
                title_name="Rare Game",
            ),
            AchievementRow(
                title_id="t1",
                achievement_id="u2",
                name="Also Ultra",
                description=None,
                icon_url=None,
                unlocked_at=(now - timedelta(days=1)).isoformat(),
                gamerscore=10,
                rarity_percent=None,
                platform="xbox_modern",
                title_name="Rare Game",
            ),
            AchievementRow(
                title_id="t1",
                achievement_id="common",
                name="Common",
                description=None,
                icon_url=None,
                unlocked_at=now.isoformat(),
                gamerscore=10,
                rarity_percent=None,
                platform="xbox_modern",
                title_name="Rare Game",
            ),
            AchievementRow(
                title_id="t1",
                achievement_id="old",
                name="Old Ultra",
                description=None,
                icon_url=None,
                unlocked_at=(now - timedelta(days=40)).isoformat(),
                gamerscore=10,
                rarity_percent=None,
                platform="xbox_modern",
                title_name="Rare Game",
            ),
        ],
        is_backfill=False,
    )
    await repo.cache_rarity(
        "xbox_modern",
        "t1",
        {"u1": 0.3, "u2": 0.9, "common": 12.0, "old": 0.1},
    )

    rows = await repo.chat_ultra_rares(
        CHAT_ID, since=now - timedelta(days=30), until=now + timedelta(days=1)
    )

    assert [r.name for r in rows] == ["Ultra"]
    assert all(r.rarity_percent is not None and r.rarity_percent < 0.5 for r in rows)
