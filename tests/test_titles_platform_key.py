"""A game is its platform and its id (#147, migration 090): the id spaces of
Steam and Xbox overlap, and an Xbox game found to be the other generation
moves with its achievements instead of splitting."""

from __future__ import annotations

import aiosqlite

from bot.constants import Platform
from bot.db.repo import MIGRATIONS_DIR, Repo


async def test_a_steam_and_an_xbox_game_with_one_id_are_two_games(repo: Repo) -> None:
    await repo.upsert_title("2154930", "Some Steam Game", Platform.STEAM)
    await repo.upsert_title("2154930", "Modern Warfare Remastered", Platform.XBOX_MODERN)

    assert await repo.title_name(Platform.STEAM, "2154930") == "Some Steam Game"
    assert await repo.title_name("xbox", "2154930") == "Modern Warfare Remastered"
    names = await repo.title_names([(Platform.STEAM, "2154930"), (Platform.XBOX_MODERN, "2154930")])
    assert set(names) == {(Platform.STEAM, "2154930"), (Platform.XBOX_MODERN, "2154930")}


async def test_a_game_found_to_be_360_moves_and_keeps_what_was_learned(repo: Repo) -> None:
    await repo.upsert_title("360", "Fable II", Platform.XBOX_MODERN, icon_url="https://art")
    await repo.record_hltb_match(Platform.XBOX_MODERN, "360", 42, 0.9)

    await repo.update_title_platform("360", Platform.XBOX_360)

    cursor = await repo._conn.execute(
        "SELECT platform, icon_url, hltb_id, platforms FROM titles WHERE title_id = '360'"
    )
    rows = [tuple(row) for row in await cursor.fetchall()]
    assert rows == [("xbox_360", "https://art", 42, '["Xbox360"]')]


async def test_a_move_onto_an_existing_row_fills_its_gaps(repo: Repo) -> None:
    await repo.upsert_title("360", "Fable II", Platform.XBOX_360)
    await repo._conn.execute(
        "INSERT INTO titles (platform, title_id, name, icon_url, updated_at)"
        " VALUES ('xbox_modern', '360', 'Fable II', 'https://art', '')"
    )
    await repo._conn.commit()

    await repo.update_title_platform("360", Platform.XBOX_360)

    cursor = await repo._conn.execute(
        "SELECT platform, icon_url FROM titles WHERE title_id = '360'"
    )
    assert [tuple(row) for row in await cursor.fetchall()] == [("xbox_360", "https://art")]


async def test_a_360_game_named_through_the_modern_contract_stays_360(repo: Repo) -> None:
    await repo.upsert_title("360", "Fable II", Platform.XBOX_360)

    await repo.upsert_title("360", "Fable II", Platform.XBOX_MODERN, achievements_total=50)

    cursor = await repo._conn.execute(
        "SELECT platform, achievements_total FROM titles WHERE title_id = '360'"
    )
    assert [tuple(row) for row in await cursor.fetchall()] == [("xbox_360", 50)]


async def test_migration_090_keys_titles_by_platform(tmp_path) -> None:
    sql = (MIGRATIONS_DIR / "090_titles_platform_key.sql").read_text(encoding="utf-8")
    async with aiosqlite.connect(tmp_path / "m089.db") as conn:
        await conn.executescript(
            """
            CREATE TABLE titles (
                title_id TEXT PRIMARY KEY, name TEXT NOT NULL, name_ru TEXT, name_en TEXT,
                platform TEXT, platforms TEXT,
                platforms_attempts INTEGER NOT NULL DEFAULT 0, platforms_checked_at TEXT,
                icon_url TEXT, achievements_total INTEGER, cover_path TEXT, cover_hash TEXT,
                cover_checked_at TEXT, achievements_checked_at TEXT, hltb_id INTEGER,
                hltb_match_score REAL, hltb_attempts INTEGER NOT NULL DEFAULT 0,
                hltb_checked_at TEXT, steam_appid INTEGER,
                steam_appid_attempts INTEGER NOT NULL DEFAULT 0, steam_appid_checked_at TEXT,
                tips_checked_at TEXT, updated_at TEXT NOT NULL);
            CREATE TABLE seen_achievements (platform TEXT, title_id TEXT);
            CREATE TABLE psn_title_progress (account_id TEXT, np_communication_id TEXT);
            CREATE TABLE title_achievements (
                platform TEXT, title_id TEXT, achievement_id TEXT,
                PRIMARY KEY (platform, title_id, achievement_id));
            CREATE TABLE title_guide_reads (
                title_id TEXT, guide_id TEXT, fingerprint TEXT, answer TEXT, checked_at TEXT,
                PRIMARY KEY (title_id, guide_id));
            INSERT INTO titles (title_id, name, platform, hltb_id, updated_at) VALUES
                ('550', 'Left 4 Dead 2', 'steam', 7, 'x'),
                ('111', 'Known by its rows', NULL, NULL, 'x'),
                ('NPWR1_00', 'A PSN game', NULL, NULL, 'x'),
                ('222', 'Nobody knows', NULL, NULL, 'x'),
                ('333', 'A 360 game', 'xbox_360', NULL, 'x');
            INSERT INTO seen_achievements VALUES ('xbox_360', '111');
            INSERT INTO title_achievements VALUES
                ('xbox_360', '333', 'a'), ('xbox_modern', '333', 'a'), ('xbox_modern', '333', 'b');
            INSERT INTO title_guide_reads VALUES ('550', 'g', 'f', '{}', 'x');
            """
        )
        await conn.executescript(sql)
        titles = await (
            await conn.execute("SELECT platform, title_id, hltb_id FROM titles ORDER BY title_id")
        ).fetchall()
        catalog = await (
            await conn.execute("SELECT platform, achievement_id FROM title_achievements ORDER BY 2")
        ).fetchall()
        reads = await (
            await conn.execute("SELECT platform, title_id FROM title_guide_reads")
        ).fetchall()
        pk = await (
            await conn.execute("SELECT name, pk FROM pragma_table_info('titles')")
        ).fetchall()

    assert [tuple(r) for r in titles] == [
        ("xbox_360", "111", None),
        ("xbox_modern", "222", None),
        ("xbox_360", "333", None),
        ("steam", "550", 7),
        ("psn", "NPWR1_00", None),
    ]
    # The stray modern copy of a 360 game's achievement goes; one only it has stays.
    assert [tuple(r) for r in catalog] == [("xbox_360", "a"), ("xbox_modern", "b")]
    assert [tuple(r) for r in reads] == [("steam", "550")]
    assert {name for name, position in pk if position} == {"platform", "title_id"}
