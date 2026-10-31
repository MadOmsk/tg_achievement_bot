"""What the database layer does when things go wrong (#234)."""

from __future__ import annotations

import psycopg
import pytest

from bot.db import postgres, tools
from bot.db.repo import Database, Repo
from bot.db.repo._database import EmptySchemaError
from tests.conftest import TEST_SCHEMA


async def test_a_literal_percent_survives_a_statement_with_no_parameters(
    database: Database,
) -> None:
    cursor = await database.conn.execute("SELECT '50%' AS a, 7 % 4 AS b")
    row = await cursor.fetchone()
    assert (row["a"], row["b"]) == ("50%", 3)
    with tools.connect(database._dsn, schema=TEST_SCHEMA) as conn:
        assert conn.execute("SELECT '50%'").fetchone()[0] == "50%"


async def test_a_failure_caught_inside_a_block_does_not_commit_as_if_nothing_happened(
    repo: Repo,
) -> None:
    conn = repo._conn
    with pytest.raises(psycopg.errors.InFailedSqlTransaction):
        async with repo.transaction():
            await conn.execute(
                "INSERT INTO app_settings (key, value, updated_at) VALUES ('k', 'v', 'x')"
            )
            with pytest.raises(psycopg.errors.DivisionByZero):
                await conn.execute("SELECT 1 / 0")
    cursor = await conn.execute("SELECT 1 FROM app_settings WHERE key = 'k'")
    assert await cursor.fetchone() is None


async def test_a_lost_connection_is_told_and_a_closed_one_is_not(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    told: list[Exception] = []
    monkeypatch.setattr(postgres, "on_connection_lost", told.append)
    connection = await postgres.Connection.connect(database._dsn)
    pid = connection.raw.info.backend_pid
    with tools.connect(database._dsn, schema=TEST_SCHEMA) as other:
        other.execute("SELECT pg_terminate_backend(?)", (pid,))
    with pytest.raises(psycopg.OperationalError):
        await connection.execute("SELECT 1")
    assert len(told) == 1
    await connection.close()

    told.clear()
    closed = await postgres.Connection.connect(database._dsn)
    await closed.close()
    with pytest.raises(psycopg.OperationalError):
        await closed.execute("SELECT 1")
    assert told == []


async def test_a_bot_refuses_an_empty_schema_unless_told_it_is_new(database: Database) -> None:
    with tools.connect(database._dsn, schema=TEST_SCHEMA) as admin:
        admin.execute("DROP SCHEMA IF EXISTS not_imported CASCADE")
    empty = Database(database._dsn, schema="not_imported", new_ok=False)
    with pytest.raises(EmptySchemaError):
        await empty.connect()
    with tools.connect(database._dsn, schema=TEST_SCHEMA) as admin:
        row = admin.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'not_imported'"
        ).fetchone()
        assert row[0] == 0
        admin.execute("DROP SCHEMA IF EXISTS not_imported CASCADE")
    # One with its tables is no new database, whatever it was told.
    kept = await Database(database._dsn, schema=TEST_SCHEMA, new_ok=False).connect()
    await kept.close()


def test_a_password_stays_off_the_command_line() -> None:
    address, env = tools.tool_target("postgresql://role:s3cret@localhost:5432/unlocked")
    assert "s3cret" not in address
    assert "unlocked" in address
    assert env["PGPASSWORD"] == "s3cret"
