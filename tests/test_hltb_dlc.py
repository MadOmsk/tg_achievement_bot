"""HLTB entries checked against our versions, and HLTB's DLC put on our DLC
inside the game they belong to (#147; owner, 2026-10-12) — no network."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.services.hltb_match import entry_fits_version, match_dlc_entries
from bot.services.store_collect import link_hltb_entry
from bot.services.stores import StoreDlc, StoreVersion, hltb_page, steam_store


def test_a_dlc_entry_never_stands_for_a_base_game() -> None:
    def fits(**kw: object) -> bool:
        args = {
            "game_type": "game",
            "steam_appids": set(),
            "entry_year": 2015,
            "version_store": "xbox",
            "version_product": "X",
            "version_kind": "game",
            "version_year": 2015,
        }
        return entry_fits_version(**{**args, **kw})  # type: ignore[arg-type]

    assert fits()
    assert not fits(game_type="dlc")
    assert not fits(version_store="steam", version_product="1", steam_appids={2})
    assert fits(version_store="steam", version_product="2", steam_appids={2, 3})
    assert not fits(version_year=2005, entry_year=2023)  # the entry is the remake
    assert fits(version_year=2024)  # a port years later is still it


def test_dlc_entries_are_matched_inside_their_game_only() -> None:
    children = [
        (1, "Hearts of Stone", None),
        (2, "The Witcher 3: Wild Hunt - Blood and Wine", 378648),
        (3, "Expansion Pass", None),
        (4, "Expansion Pass", None),
    ]
    dlcs = [
        (10, "steam", "378648", "The Witcher 3: Wild Hunt - Blood and Wine"),
        (11, "xbox", "HOS", "The Witcher 3: Wild Hunt – Hearts of Stone"),
        (12, "xbox", "HOS2", "The Witcher 3: Wild Hunt - Hearts of Stone"),  # another product
        (13, "xbox", "PASS", "Expansion Pass"),  # two entries share the name
        (14, "psn", "HOS-PS", "Hearts of Stone"),
    ]
    found = match_dlc_entries(children, dlcs, ["The Witcher 3: Wild Hunt"])
    assert found == {10: 2, 14: 1}


async def test_a_games_dlc_entries_are_linked_to_its_dlc(repo: Repo) -> None:
    version = steam_store.parse_app(
        {"type": "game", "name": "Cyberpunk 2077", "steam_appid": 1091500}
    )
    vid = await repo.save_version(version, platform=None, title_id=None)
    await repo.save_dlc(vid, StoreDlc(store_id="2138330", name="Cyberpunk 2077: Phantom Liberty"))
    page = {
        "game": [{"game_id": 2127, "game_name": "Cyberpunk 2077", "game_type": "game"}],
        "relationships": [{"game_id": 113203, "game_name": "Phantom Liberty", "game_type": "dlc"}],
    }
    await repo.save_hltb_game(hltb_page.parse_page(page))  # type: ignore[arg-type]
    await repo.save_payload("hltb:2127", "hltb_page", page)
    await repo.link_version_hltb(vid, 2127)
    await link_hltb_entry(repo, 2127)
    cursor = await repo._conn.execute("SELECT hltb_id, source FROM dlc_hltb")
    assert [tuple(r) for r in await cursor.fetchall()] == [(113203, "auto")]
    # The entry turns out to be a DLC's: no base game keeps it.
    await repo._conn.execute("UPDATE hltb_games SET game_type = 'dlc' WHERE hltb_id = 2127")
    await link_hltb_entry(repo, 2127)
    # The link stays as a refusal, so nothing makes it again.
    cursor = await repo._conn.execute("SELECT source FROM version_hltb")
    assert [r[0] for r in await cursor.fetchall()] == ["rejected"]
    assert await repo.versions_of_hltb(2127) == []


# ------------------------------------------- one home for a list's HLTB entry (110)


async def _list_with_version(repo: Repo, title_id: str = "T1") -> int:
    await repo.upsert_title(title_id, "Control", "xbox_modern")
    version = StoreVersion(
        store="xbox", product_id=f"P{title_id}", console="series", name="Control"
    )
    return await repo.save_version(version, platform="xbox_modern", title_id=title_id)


async def test_a_match_is_a_link_of_the_lists_versions_and_a_stand_in_carries_it(
    repo: Repo,
) -> None:
    await repo.upsert_title("ONLY", "Lonely List", "xbox_360")
    await repo.record_hltb_match("xbox_360", "ONLY", 77, 0.95)

    assert await repo.list_hltb_match("xbox_360", "ONLY") == (77, 0.95)
    (version,) = await repo.versions_of_title("xbox_360", "ONLY")
    assert version["stand_in"] == 1 and (version["store"], version["console"]) == ("xbox", "360")
    assert not await repo.fetch_due("xbox_360:ONLY", "hltb_match")


async def test_the_operators_link_wins_and_a_refusal_is_never_made_again(repo: Repo) -> None:
    version = await _list_with_version(repo)
    await repo.link_version_hltb(version, 10, "auto", 0.99)
    await repo.link_version_hltb(version, 20, "manual")
    assert await repo.list_hltb_match("xbox_modern", "T1") == (20, None)

    # Refused by hand: the automatic matcher and a collection leave it alone.
    await repo.unlink_version_hltb(version, 20)
    await repo.link_version_hltb(version, 20, "auto", 0.5)
    assert await repo.list_hltb_match("xbox_modern", "T1") == (10, 0.99)
    await repo.record_hltb_match("xbox_modern", "T1", 20, 0.8)
    assert await repo.list_hltb_match("xbox_modern", "T1") == (10, 0.99)
    # The operator can change their mind.
    await repo.link_version_hltb(version, 20, "manual")
    assert await repo.list_hltb_match("xbox_modern", "T1") == (20, None)


async def test_an_entry_refused_everywhere_counts_as_a_failed_attempt(repo: Repo) -> None:
    version = await _list_with_version(repo)
    await repo.unlink_version_hltb(version, 5)

    await repo.record_hltb_match("xbox_modern", "T1", 5, 0.9)

    assert await repo.list_hltb_match("xbox_modern", "T1") is None
    cursor = await repo._conn.execute(
        "SELECT status, attempts FROM fetch_state WHERE source = 'hltb_match'"
    )
    assert tuple(await cursor.fetchone()) == ("error", 1)


async def test_the_match_row_is_due_until_matched_and_then_not_for_a_while(
    repo: Repo,
) -> None:
    await _list_with_version(repo)
    assert await repo.title_hltb_match_row("xbox_modern", "T1") is not None
    await repo.record_hltb_match("xbox_modern", "T1", None, None)
    assert await repo.title_hltb_match_row("xbox_modern", "T1") is None  # asked just now
    await repo.record_hltb_match("xbox_modern", "T1", 9, 0.9)
    assert await repo.title_hltb_match_row("xbox_modern", "T1") is None  # matched


async def test_migration_110_gives_every_list_a_version_and_the_old_match_a_link(
    tmp_path,
) -> None:
    import aiosqlite

    from bot.db.repo import MIGRATIONS_DIR
    from bot.services.stores import console_of, store_of

    sql = (MIGRATIONS_DIR / "110_hltb_entry_is_a_version_link.sql").read_text(encoding="utf-8")
    lists = [
        ("xbox_modern", "1", '["XboxOne", "XboxSeries"]'),
        ("xbox_modern", "2", '["XboxSeries"]'),
        ("xbox_modern", "3", '["PC"]'),
        ("xbox_modern", "4", '["Win32"]'),
        ("xbox_modern", "5", '["PC", "XboxOne", "XboxSeries"]'),
        ("xbox_modern", "6", None),
        ("xbox_modern", "7", "[]"),
        ("xbox_modern", "8", '["xboxone", "Mobile"]'),
        ("xbox_360", "9", '["Xbox360"]'),
        ("steam", "10", '["PC"]'),
        ("psn", "11", '["PS5"]'),
        ("psn", "12", '["PS4", "PS5"]'),
        ("psn", "13", '["PSVITA"]'),
    ]
    async with aiosqlite.connect(tmp_path / "m109.db") as conn:
        await conn.executescript(
            """
            CREATE TABLE titles (
                platform TEXT NOT NULL, title_id TEXT NOT NULL, name TEXT NOT NULL, name_ru TEXT,
                name_en TEXT, platforms TEXT, hltb_id INTEGER, hltb_match_score REAL,
                hltb_attempts INTEGER NOT NULL DEFAULT 0, hltb_checked_at TEXT,
                updated_at TEXT NOT NULL, PRIMARY KEY (platform, title_id));
            CREATE TABLE versions (
                version_id INTEGER PRIMARY KEY, store TEXT NOT NULL, product_id TEXT NOT NULL,
                console TEXT NOT NULL, platform TEXT, title_id TEXT, name TEXT, name_ru TEXT,
                kind TEXT, live_service INTEGER NOT NULL DEFAULT 0,
                origin TEXT NOT NULL DEFAULT 'played', updated_at TEXT NOT NULL,
                stand_in INTEGER NOT NULL DEFAULT 0, store_ids TEXT,
                UNIQUE (store, product_id, console));
            CREATE TABLE version_hltb (
                version_id INTEGER NOT NULL, hltb_id INTEGER NOT NULL, source TEXT NOT NULL,
                PRIMARY KEY (version_id, hltb_id));
            CREATE TABLE fetch_state (
                subject TEXT NOT NULL, source TEXT NOT NULL, status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, interval_days INTEGER NOT NULL DEFAULT 7,
                checked_at TEXT NOT NULL, next_check_at TEXT NOT NULL, last_error TEXT,
                PRIMARY KEY (subject, source)) WITHOUT ROWID;
            """
        )
        await conn.executemany(
            "INSERT INTO titles (platform, title_id, name, platforms, updated_at)"
            " VALUES (?, ?, ?, ?, '2026-01-01T00:00:00+00:00')",
            [(p, t, f"Game {t}", plat) for p, t, plat in lists],
        )
        await conn.execute(
            "UPDATE titles SET hltb_id = 500, hltb_match_score = 0.9,"
            " hltb_checked_at = '2026-02-02T10:00:00+00:00' WHERE title_id = '1'"
        )
        await conn.execute(
            "UPDATE titles SET hltb_attempts = 3, hltb_checked_at = '2026-02-02T10:00:00+00:00'"
            " WHERE title_id = '2'"
        )
        await conn.execute(
            "INSERT INTO versions (store, product_id, console, platform, title_id, name,"
            " updated_at, stand_in) VALUES ('xbox', 'BIG', 'one', 'xbox_modern', '3', 'Real',"
            " 'x', 0)"
        )
        await conn.executescript(sql)
        cursor = await conn.execute(
            "SELECT platform, title_id, store, console, stand_in FROM versions ORDER BY title_id"
        )
        made = {(r[0], r[1]): tuple(r[2:]) for r in await cursor.fetchall()}
        cursor = await conn.execute("SELECT version_id, hltb_id, source, score FROM version_hltb")
        links = [tuple(r) for r in await cursor.fetchall()]
        cursor = await conn.execute(
            "SELECT subject, status, attempts, next_check_at FROM fetch_state ORDER BY subject"
        )
        state = [tuple(r) for r in await cursor.fetchall()]
        cursor = await conn.execute("PRAGMA table_info(titles)")
        columns = {r[1] for r in await cursor.fetchall()}

    # The SQL twin of the stand-in's store and console agrees with the Python one.
    for platform, title_id, platforms in lists:
        if title_id == "3":
            assert made[(platform, title_id)] == ("xbox", "one", 0)  # it had a version already
            continue
        assert made[(platform, title_id)] == (
            store_of(platform, platforms or ""),
            console_of(platform, platforms or ""),
            1,
        ), (platform, title_id, platforms)
    assert [(link[1], link[2], link[3]) for link in links] == [(500, "auto", 0.9)]
    assert state == [
        ("xbox_modern:1", "ok", 0, "2026-02-09T10:00:00+00:00"),
        ("xbox_modern:2", "gave_up", 3, "2026-03-04T10:00:00+00:00"),
    ]
    assert not columns & {"hltb_id", "hltb_match_score", "hltb_attempts", "hltb_checked_at"}


async def test_a_regional_twin_list_is_matched_through_the_version_that_carries_it(
    repo: Repo,
) -> None:
    await repo.upsert_title("2130", "Dark Messiah Multi-Player", "steam")
    await repo.upsert_title("2100", "Dark Messiah Single Player", "steam")
    version = await repo.save_version(
        StoreVersion(
            store="steam", product_id="2100", console="steam", name="Dark Messiah of Might & Magic"
        ),
        platform="steam",
        title_id="2130",
    )
    await repo.add_store_ids(version, [("list", "steam:2100")])
    await repo._conn.commit()

    await repo.record_hltb_match("steam", "2100", 55, 0.9)

    assert await repo.list_hltb_match("steam", "2100") == (55, 0.9)
    assert await repo.list_hltb_match("steam", "2130") == (55, 0.9)  # the same product
    row = await repo.version_row(version)
    assert row["name"] == "Dark Messiah of Might & Magic" and row["stand_in"] == 0
