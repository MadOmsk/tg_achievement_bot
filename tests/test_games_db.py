"""One games database for prod and the test server (#229)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bot.db import files
from bot.db.repo import Database, Repo
from bot.db.repo._games_db import GAMES_DB_KEY, placed
from bot.services.stores import StoreVersion
from scripts import games_db


def test_only_the_catalogs_own_objects_are_placed_in_games() -> None:
    assert placed("CREATE TABLE IF NOT EXISTS versions (x)", True).startswith(
        "CREATE TABLE IF NOT EXISTS games.versions"
    )
    assert placed("-- a note\nCREATE INDEX IF NOT EXISTS idx_v ON versions(x)", True) == (
        "-- a note\nCREATE INDEX IF NOT EXISTS games.idx_v ON versions(x)"
    )
    assert "games.list_name" in placed(
        "CREATE TRIGGER IF NOT EXISTS list_name AFTER UPDATE OF name"
        " ON achievement_list_connectors BEGIN SELECT 1; END",
        True,
    )
    for statement in ("CREATE TABLE users (x)", "CREATE INDEX i ON users(x)"):
        assert placed(statement, True) == statement
    assert placed("CREATE TABLE versions (x)", False) == "CREATE TABLE versions (x)"


async def _one_file(path: Path, title_id: str) -> None:
    """A bot's database as before #229, with one list and its version."""
    database = await Database(path).connect()
    repo = Repo(database)
    await repo.upsert_title(title_id, f"Game {title_id}", "steam")
    await repo.save_version(
        StoreVersion(store="steam", product_id=title_id, console="steam", name="Game"),
        platform="steam",
        title_id=title_id,
    )
    await database.close()


def _count(path: Path, table: str) -> int:
    conn = files.connect(path, readonly=True)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_split_join_and_leave(tmp_path: Path) -> None:
    test_db, prod_db, shared = tmp_path / "test.db", tmp_path / "bot.db", tmp_path / "games.db"
    await _one_file(test_db, "10")
    await _one_file(prod_db, "20")  # a list only prod's people played

    games_db.split(test_db, shared)
    plain = sqlite3.connect(test_db)
    assert plain.execute(
        "SELECT name FROM sqlite_master WHERE name IN ('versions', 'users')"
    ).fetchall() == [("users",)]
    assert files.games_of(plain) == shared.resolve()
    plain.close()

    kept = games_db.join(prod_db, shared)
    assert len(kept) == 1  # its stand-in kept, to be linked into a game
    assert _count(test_db, "achievement_list_connectors") == 2
    assert _count(prod_db, "versions") == 2

    # Both bots come up on the one file and see each other's writes.
    test_bot = await Database(test_db).connect()
    prod_bot = await Database(prod_db).connect()
    try:
        assert test_bot.games_path == prod_bot.games_path == shared.resolve()
        await Repo(test_bot).upsert_title("30", "Found on test", "steam")
        cursor = await prod_bot.conn.execute(
            "SELECT name FROM achievement_list_connectors WHERE title_id = '30'"
        )
        assert (await cursor.fetchone())[0] == "Found on test"
    finally:
        await test_bot.close()
        await prod_bot.close()

    games_db.leave(prod_db)
    plain = sqlite3.connect(prod_db)
    assert files.games_of(plain) is None
    assert plain.execute("SELECT COUNT(*) FROM achievement_list_connectors").fetchone()[0] == 3
    plain.close()


@pytest.mark.asyncio
async def test_a_missing_games_file_stops_start_up(tmp_path: Path) -> None:
    db = tmp_path / "bot.db"
    await _one_file(db, "10")
    games_db.split(db, tmp_path / "games.db")
    (tmp_path / "games.db").unlink()
    with pytest.raises(Exception, match="not found"):
        await Database(db).connect()


@pytest.mark.asyncio
async def test_a_copy_names_its_own_games_copy(tmp_path: Path) -> None:
    db = tmp_path / "bot.db"
    await _one_file(db, "10")
    games_db.split(db, tmp_path / "games.db")
    copy = files.backup(db, tmp_path / "copy.db")
    conn = sqlite3.connect(copy)
    assert conn.execute("SELECT value FROM app_settings WHERE key = ?", (GAMES_DB_KEY,)).fetchone()[
        0
    ] == str(files.copy_of(copy).resolve())
    conn.close()
    assert _count(copy, "versions") == 1
