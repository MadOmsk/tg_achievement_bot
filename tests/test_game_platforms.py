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

    # Check game listing formatting (shows (icon <i>short_plat</i>))
    listing = games_listing(games, "untitled", "ru")
    rendered = listing.render()
    assert "(🟢 <i>XOne | Series</i>) Halo Infinite" in rendered


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

    # Test recent_list formatting (shows (icon <i>short_plat</i>))
    rendered = recent_list(recent)
    assert "(🟢 <i>XSeries</i>) Gears 5" in rendered

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


@pytest.fixture
def migration_055_sql() -> str:
    migration_file = Path("bot/db/migrations/055_fix_xbox_platforms.sql")
    return migration_file.read_text(encoding="utf-8")


async def test_migration_055_fixes_xbox_platforms(tmp_path, migration_055_sql: str) -> None:
    db_path = tmp_path / "migration_055_test.db"
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute(
            "CREATE TABLE titles ("
            "  title_id TEXT PRIMARY KEY,"
            "  name TEXT NOT NULL,"
            "  platform TEXT NOT NULL,"
            "  platforms TEXT"
            ")"
        )
        await conn.execute(
            "CREATE TABLE seen_achievements (  title_id TEXT NOT NULL,  device TEXT)"
        )
        # Seed titles with erroneous ["XboxOne"] from migration 052
        await conn.execute(
            "INSERT INTO titles VALUES ('t-solitaire', 'Solitaire', 'xbox_modern', '[\"XboxOne\"]')"
        )
        await conn.execute(
            "INSERT INTO titles VALUES ('t-halo', 'Halo Infinite', 'xbox_modern', '[\"XboxOne\"]')"
        )
        await conn.execute(
            "INSERT INTO titles VALUES ('t-unknown', 'Old Game', 'xbox_modern', '[\"XboxOne\"]')"
        )
        await conn.execute(
            "INSERT INTO titles VALUES ('t-360', 'Halo 3', 'xbox_360', '[\"Xbox360\"]')"
        )

        # Seed recorded devices in seen_achievements
        await conn.execute("INSERT INTO seen_achievements VALUES ('t-solitaire', 'WindowsOneCore')")
        await conn.execute("INSERT INTO seen_achievements VALUES ('t-halo', 'XboxSeriesX')")
        await conn.execute("INSERT INTO seen_achievements VALUES ('t-halo', 'XboxOne')")
        await conn.commit()

        # Run migration 055
        await conn.executescript(migration_055_sql)
        await conn.commit()

        cursor = await conn.execute("SELECT title_id, platforms FROM titles ORDER BY title_id")
        rows = {r["title_id"]: r["platforms"] for r in await cursor.fetchall()}

        # 360 left untouched
        assert rows["t-360"] == '["Xbox360"]'
        # Unknown modern game reset to NULL (which formats as generic XBOX)
        assert rows["t-unknown"] is None
        # Solitaire recovered as WindowsOneCore
        assert rows["t-solitaire"] == '["WindowsOneCore"]'
        # Halo recovered as both devices
        halo_devices = json.loads(rows["t-halo"])
        assert set(halo_devices) == {"XboxSeriesX", "XboxOne"}


async def test_save_title_history_writes_the_game_platforms(repo: Repo) -> None:
    from bot.db.repo import TitleHistoryRow

    await repo.upsert_title("t-device-1", "Test Game", Platform.XBOX_MODERN)
    history_row = TitleHistoryRow(
        title_id="t-device-1",
        name="Test Game",
        platform=Platform.XBOX_MODERN,
        current_gamerscore=10,
        max_gamerscore=1000,
        achievements_unlocked=1,
        achievements_total=10,
        last_played_at="2026-09-20T12:00:00+00:00",
        devices=["XboxOne", "XboxSeriesX"],
    )
    await repo.save_title_history("xuid-1", [history_row])
    title_row = await repo.title_platforms(["t-device-1"])
    assert set(json.loads(title_row["t-device-1"])) == {"XboxOne", "XboxSeriesX"}

    # Xbox 360 titles: saved as ["Xbox360"] regardless of backward-compat devices
    await repo.upsert_title("t-360-dev", "Fable II", Platform.XBOX_360)
    history_row_360 = TitleHistoryRow(
        title_id="t-360-dev",
        name="Fable II",
        platform=Platform.XBOX_360,
        current_gamerscore=10,
        max_gamerscore=1000,
        achievements_unlocked=1,
        achievements_total=10,
        last_played_at="2026-09-20T12:00:00+00:00",
        devices=["Xbox360", "XboxOne", "XboxSeries"],
    )
    await repo.save_title_history("xuid-1", [history_row_360])
    title_row_360 = await repo.title_platforms(["t-360-dev"])
    assert title_row_360["t-360-dev"] == '["Xbox360"]'


# The device an achievement was earned on is a fact or nothing (owner, 2026-09-24).


def _row(title_id: str, achievement_id: str, platform: Platform, device: str | None = None):
    return AchievementRow(
        title_id=title_id,
        achievement_id=achievement_id,
        name="A",
        description=None,
        icon_url=None,
        unlocked_at="2026-09-20T12:00:00+00:00",
        gamerscore=10,
        rarity_percent=None,
        platform=platform,
        device=device,
    )


async def _devices(repo: Repo) -> dict[str, str | None]:
    cursor = await repo._conn.execute("SELECT title_id, device FROM seen_achievements")
    return {r["title_id"]: r["device"] for r in await cursor.fetchall()}


async def test_a_single_platform_game_gets_its_platform_as_the_device(repo: Repo) -> None:
    await repo.upsert_title(
        "t-one", "Series only", Platform.XBOX_MODERN, platforms='["XboxSeries"]'
    )
    await repo.upsert_title(
        "t-many", "Play Anywhere", Platform.XBOX_MODERN, platforms='["PC", "XboxSeries"]'
    )
    await repo.insert_new_achievements(
        "xuid-1",
        [_row("t-one", "1", Platform.XBOX_MODERN), _row("t-many", "1", Platform.XBOX_MODERN)],
        is_backfill=True,
    )

    devices = await _devices(repo)
    assert devices["t-one"] == "XboxSeries"
    assert devices["t-many"] is None  # several platforms: not guessed


async def test_a_device_presence_reported_is_kept(repo: Repo) -> None:
    await repo.upsert_title(
        "t-many", "Play Anywhere", Platform.XBOX_MODERN, platforms='["PC", "XboxSeries"]'
    )
    await repo.insert_new_achievements(
        "xuid-1",
        [_row("t-many", "1", Platform.XBOX_MODERN, device="Scarlett")],
        is_backfill=False,
    )

    assert (await _devices(repo))["t-many"] == "Scarlett"


async def test_the_device_fills_in_once_the_game_platforms_arrive(repo: Repo) -> None:
    from bot.db.repo import TitleHistoryRow

    await repo.insert_new_achievements(
        "xuid-1", [_row("t-late", "1", Platform.XBOX_MODERN)], is_backfill=True
    )
    assert (await _devices(repo))["t-late"] is None

    await repo.save_title_history(
        "xuid-1",
        [
            TitleHistoryRow(
                title_id="t-late",
                name="Late",
                platform=Platform.XBOX_MODERN,
                current_gamerscore=0,
                max_gamerscore=0,
                achievements_unlocked=1,
                achievements_total=1,
                last_played_at=None,
                devices=["PC"],
            )
        ],
    )
    assert (await _devices(repo))["t-late"] == "PC"


async def test_steam_never_gets_a_device(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    await repo.insert_new_achievements_steam(
        1, "76561197960287930", [_row("550", "a", Platform.STEAM)], is_backfill=True
    )
    await repo.upsert_title("550", "L4D2", Platform.STEAM, platforms='["PC"]')
    await repo.fill_single_platform_devices(["550"])

    assert (await _devices(repo))["550"] is None


@pytest.fixture
def migration_059_sql() -> str:
    return Path("bot/db/migrations/059_device_facts_only.sql").read_text(encoding="utf-8")


async def test_migration_059_keeps_facts_and_drops_guesses(
    tmp_path, migration_059_sql: str
) -> None:
    async with aiosqlite.connect(tmp_path / "m059.db") as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute(
            "CREATE TABLE titles"
            " (title_id TEXT PRIMARY KEY, name TEXT, platform TEXT, platforms TEXT)"
        )
        await conn.execute(
            "CREATE TABLE seen_achievements (title_id TEXT, platform TEXT, device TEXT)"
        )
        await conn.executemany(
            "INSERT INTO titles VALUES (?, ?, ?, ?)",
            [
                ("t-seeded", "Haven", "xbox_modern", '["Scarlett"]'),  # a device, not platforms
                ("t-xpa", "Well Dweller", "xbox_modern", '["PC", "XboxOne", "XboxSeries"]'),
                ("t-pc", "Solitaire", "xbox_modern", '["PC"]'),
                ("t-mc", "Minecraft", "xbox_modern", '["Android"]'),  # a real platform
                ("t-ps-multi", "Spider-Man", "psn", '["PS4", "PS5"]'),
                ("t-ps-one", "Astro Bot", "psn", '["PS5"]'),
                ("t-360", "Halo 3", "xbox_360", '["Xbox360"]'),
                ("550", "L4D2", "steam", '["PC"]'),
            ],
        )
        await conn.executemany(
            "INSERT INTO seen_achievements VALUES (?, ?, ?)",
            [
                ("t-seeded", "xbox_modern", "Scarlett"),  # presence: a fact
                ("t-xpa", "xbox_modern", None),
                ("t-pc", "xbox_modern", None),
                ("t-ps-multi", "psn", "PS4"),  # possibly guessed
                ("t-ps-one", "psn", None),
                ("t-360", "xbox_360", None),
                ("550", "steam", "PC"),
            ],
        )
        await conn.commit()

        await conn.executescript(migration_059_sql)
        await conn.commit()

        cursor = await conn.execute("SELECT title_id, platforms FROM titles")
        titles = {r["title_id"]: r["platforms"] for r in await cursor.fetchall()}
        cursor = await conn.execute("SELECT title_id, device FROM seen_achievements")
        devices = {r["title_id"]: r["device"] for r in await cursor.fetchall()}

    assert titles["t-seeded"] is None  # titlehub refills it
    assert titles["t-mc"] == '["Android"]'
    assert devices["t-seeded"] == "Scarlett"
    assert devices["t-xpa"] is None
    assert devices["t-pc"] == "PC"
    assert devices["t-ps-multi"] is None
    assert devices["t-ps-one"] == "PS5"
    assert devices["t-360"] == "Xbox360"
    assert devices["550"] is None


@pytest.fixture
def migration_056_sql() -> str:
    migration_file = Path("bot/db/migrations/056_fix_x360_platforms.sql")
    return migration_file.read_text(encoding="utf-8")


async def test_migration_056_fixes_x360_platforms(tmp_path, migration_056_sql: str) -> None:
    db_path = tmp_path / "migration_056_test.db"
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute(
            "CREATE TABLE titles ("
            "  title_id TEXT PRIMARY KEY,"
            "  name TEXT NOT NULL,"
            "  platform TEXT NOT NULL,"
            "  platforms TEXT"
            ")"
        )
        # Seed titles with backward-compatibility pollution in platforms
        gow_plats = '["Xbox360", "XboxOne", "XboxSeries"]'
        conker_plats = '["Xbox360", "PC", "XboxOne", "XboxSeries"]'
        halo_plats = '["XboxOne", "XboxSeriesX"]'
        await conn.execute(
            "INSERT INTO titles VALUES ('t-gow2', 'Gears of War 2', 'xbox_360', ?)", (gow_plats,)
        )
        await conn.execute(
            "INSERT INTO titles VALUES ('t-conker', 'Conker', 'xbox_360', ?)", (conker_plats,)
        )
        await conn.execute(
            "INSERT INTO titles VALUES ('t-halo-inf', 'Halo Infinite', 'xbox_modern', ?)",
            (halo_plats,),
        )
        await conn.commit()

        # Run migration 056
        await conn.executescript(migration_056_sql)
        await conn.commit()

        cursor = await conn.execute("SELECT title_id, platforms FROM titles ORDER BY title_id")
        rows = {r["title_id"]: r["platforms"] for r in await cursor.fetchall()}

        assert rows["t-gow2"] == '["Xbox360"]'
        assert rows["t-conker"] == '["Xbox360"]'
        assert rows["t-halo-inf"] == '["XboxOne", "XboxSeriesX"]'
