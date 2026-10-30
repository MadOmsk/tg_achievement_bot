"""The way scripts open the database (#234)."""

from __future__ import annotations

import psycopg
import pytest

from bot.db import tools
from bot.db.repo import Database
from tests.conftest import TEST_SCHEMA


async def test_a_script_reads_the_bot_s_schema_with_the_bot_s_face(database: Database) -> None:
    await database.conn.execute(
        "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)", ("k", "7", "now")
    )
    with tools.connect(database._dsn, schema=TEST_SCHEMA) as conn:
        row = conn.execute("SELECT key, value FROM app_settings WHERE key = ?", ("k",)).fetchone()
        assert row["value"] == "7"
        assert row[0] == "k"
        # The search path reaches the catalog too, unqualified.
        assert conn.execute("SELECT COUNT(*) FROM versions").fetchone()[0] == 0


async def test_a_read_only_connection_is_refused_a_write(database: Database) -> None:
    with tools.connect(database._dsn, schema=TEST_SCHEMA, readonly=True) as conn:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute("INSERT INTO app_settings (key, value, updated_at) VALUES ('a', 'b', 'c')")


async def test_a_block_rolls_back(database: Database) -> None:
    with tools.connect(database._dsn, schema=TEST_SCHEMA) as conn:
        conn.begin()
        conn.execute("INSERT INTO app_settings (key, value, updated_at) VALUES ('a', 'b', 'c')")
        conn.rollback()
        assert conn.execute("SELECT 1 FROM app_settings WHERE key = 'a'").fetchone() is None


async def test_open_database_brings_nothing_up(database: Database) -> None:
    opened = await tools.open_database(database._dsn, schema=TEST_SCHEMA)
    try:
        cursor = await opened.conn.execute("SELECT COUNT(*) FROM schema_migrations")
        assert (await cursor.fetchone())[0] >= 0
    finally:
        await opened.close()
