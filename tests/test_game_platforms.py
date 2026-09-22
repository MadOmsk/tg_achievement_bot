"""Tests for game platforms and device separation (#79)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite
import pytest

from bot.constants import Platform
from bot.db.repo import AchievementRow, Repo
from bot.views.chat import recent_list
from bot.views.lists import games_listing


def _utc(hour: int = 12) -> datetime:
    return datetime(2026, 9, 20, hour, 0, 0, tzinfo=UTC)


async def test_upsert_title_and_query_platforms(repo: Repo) -> None:
    platforms_json = json.dumps(["XboxSeriesX", "XboxOne"])
    await repo.upsert_title(
        "title-1", "Halo Infinite", Platform.XBOX_MODERN, platforms=platforms_json
    )

    # Insert achievement and check users_games_achievements
    await repo.ensure_user(1, "player")
    await repo.link_xbox_account(1, "xuid-1", "Player", 0)
    row = AchievementRow(
        title_id="title-1",
        achievement_id="a1",
        name="First Ach",
        description="Desc",
        icon_url=None,
        unlocked_at="2026-09-20T12:00:00+00:00",
        gamerscore=10,
        rarity_percent=5.0,
        platform=Platform.XBOX_MODERN,
        title_name="Halo Infinite",
        device="XboxSeriesX",
    )
    inserted = await repo.insert_new_achievements("xuid-1", [row], is_backfill=False)
    assert len(inserted) == 1
    assert inserted[0].device == "XboxSeriesX"

    games = await repo.users_games_achievements([1], _utc(10), rare_threshold=10.0, limit=10)
    assert len(games) == 1
    assert games[0].platforms == platforms_json

    # Check game listing formatting (shows (icon short_plat))
    listing = games_listing(games, "untitled", "ru")
    rendered = listing.render()
    assert "(🟢 XOne | Series) Halo Infinite" in rendered


async def test_backfill_leaves_device_null(repo: Repo) -> None:
    await repo.ensure_user(2, "player2")
    await repo.link_xbox_account(2, "xuid-2", "Player2", 0)
    row = AchievementRow(
        title_id="title-bf",
        achievement_id="a-bf",
        name="Backfill Ach",
        description="Desc",
        icon_url=None,
        unlocked_at="2026-09-20T12:00:00+00:00",
        gamerscore=10,
        rarity_percent=5.0,
        platform=Platform.XBOX_MODERN,
        title_name="Backfill Game",
        device="XboxSeriesX",
    )
    # Even if row.device is set, is_backfill=True must store device as NULL
    await repo.insert_new_achievements("xuid-2", [row], is_backfill=True)

    cursor = await repo._conn.execute(
        "SELECT device FROM seen_achievements WHERE title_id = 'title-bf'"
    )
    db_row = await cursor.fetchone()
    assert db_row is not None
    assert db_row["device"] is None


async def test_presence_state_device_and_chat_member_presence(repo: Repo) -> None:
    await repo.upsert_chat(-1001, "Chat", 1)
    await repo.ensure_user(3, "player3")
    await repo.link_xbox_account(3, "xuid-3", "Player3", 0)
    await repo.subscribe(-1001, 3)

    # Save presence with device
    await repo.save_presence_state(
        "xuid-3", "Online", "title-1", "Halo Infinite", device="XboxSeriesX", changed=True
    )

    p = await repo.presence_of("xuid-3")
    assert p is not None
    assert p.device == "XboxSeriesX"

    # Chat presence should resolve winner device
    members = await repo.chat_member_presence(-1001)
    assert len(members) == 1
    assert members[0].device == "XboxSeriesX"
    assert members[0].platform == Platform.XBOX_MODERN


async def test_psn_presence_state_device_and_chat_member_presence(repo: Repo) -> None:
    await repo.upsert_chat(-1002, "Chat", 1)
    await repo.ensure_user(4, "player4")
    await repo.link_platform_account(4, Platform.PSN, "psn-4", "PSNPlayer")
    await repo.subscribe(-1002, 4)

    # Save PSN presence with device
    await repo.save_psn_presence_state(
        "psn-4", "Online", "NPWR12345", "Astro Bot", device="PS5", changed=True
    )

    p = await repo.psn_presence_of("psn-4")
    assert p is not None
    assert p.device == "PS5"

    members = await repo.chat_member_presence(-1002)
    assert len(members) == 1
    assert members[0].device == "PS5"
    assert members[0].platform == Platform.PSN


async def test_chat_recent_achievements_includes_device_and_platforms(repo: Repo) -> None:
    await repo.upsert_chat(-1003, "Chat", 1)
    await repo.ensure_user(5, "player5")
    await repo.link_xbox_account(5, "xuid-5", "Player5", 0)
    await repo.subscribe(-1003, 5)

    platforms_json = json.dumps(["XboxSeriesX"])
    await repo.upsert_title("title-5", "Gears 5", Platform.XBOX_MODERN, platforms=platforms_json)
    row = AchievementRow(
        title_id="title-5",
        achievement_id="a5",
        name="Completed Act",
        description="Desc",
        icon_url=None,
        unlocked_at="2026-09-20T12:00:00+00:00",
        gamerscore=20,
        rarity_percent=12.0,
        platform=Platform.XBOX_MODERN,
        title_name="Gears 5",
        device="XboxSeriesX",
    )
    await repo.insert_new_achievements("xuid-5", [row], is_backfill=False)

    recent = await repo.chat_recent(-1003, limit=5)
    assert len(recent) == 1
    assert recent[0].device == "XboxSeriesX"
    assert recent[0].game_platforms == platforms_json

    # Test recent_list formatting (shows (icon short_plat))
    rendered = recent_list(recent)
    assert "(🟢 XSeries) Gears 5" in rendered

    # Test notification formatting (uses Full platform from game_platforms)
    from bot.views.notification import format_single

    notification = format_single("Player5", row, "Gears 5", locale="ru")
    assert "Gears 5 (<i>🟢 XBOX Series X|S</i>)" in notification


@pytest.fixture
def migration_052_sql() -> str:
    migration_file = Path("bot/db/migrations/052_game_platforms_and_device.sql")
    return migration_file.read_text(encoding="utf-8")


async def test_migration_052_applies_cleanly(tmp_path, migration_052_sql: str) -> None:
    db_path = tmp_path / "migration_test.db"
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        # Create older schema without platforms/device
        await conn.execute(
            "CREATE TABLE titles ("
            "  title_id TEXT PRIMARY KEY,"
            "  name TEXT NOT NULL,"
            "  platform TEXT NOT NULL"
            ")"
        )
        await conn.execute(
            "CREATE TABLE seen_achievements ("
            "  xuid TEXT NOT NULL,"
            "  title_id TEXT NOT NULL,"
            "  achievement_id TEXT NOT NULL,"
            "  PRIMARY KEY (xuid, title_id, achievement_id)"
            ")"
        )
        await conn.execute("CREATE TABLE presence_state (  xuid TEXT PRIMARY KEY,  state TEXT)")
        await conn.execute(
            "CREATE TABLE psn_presence_state (  account_id TEXT PRIMARY KEY,  state TEXT)"
        )
        # Pre-populate titles
        await conn.execute("INSERT INTO titles VALUES ('t-360', 'Halo 3', 'xbox_360')")
        await conn.execute("INSERT INTO titles VALUES ('t-one', 'Halo 5', 'xbox_modern')")
        await conn.execute("INSERT INTO titles VALUES ('t-stm', 'Portal', 'steam')")
        await conn.commit()

        # Run migration 052
        await conn.executescript(migration_052_sql)
        await conn.commit()

        # Verify columns exist and data populated
        cursor = await conn.execute("SELECT title_id, platforms FROM titles ORDER BY title_id")
        rows = {r["title_id"]: r["platforms"] for r in await cursor.fetchall()}
        assert rows["t-360"] == '["Xbox360"]'
        assert rows["t-one"] == '["XboxOne"]'
        assert rows["t-stm"] == '["PC"]'
