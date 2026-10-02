"""A person's own id (#156, migration 071): `users` is rebuilt around it, and nothing
that points at a person through `tg_id` is lost on the way."""

from __future__ import annotations

import sqlite3

from bot.db.repo import Database, Repo

OLD_USERS = """
CREATE TABLE users (
    tg_id            INTEGER PRIMARY KEY,
    username         TEXT,
    first_name       TEXT,
    last_name        TEXT,
    is_excluded      INTEGER NOT NULL DEFAULT 0,
    excluded_by      INTEGER,
    excluded_at      TEXT,
    last_online_at   TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    photo_path       TEXT,
    photo_file_id    TEXT,
    photo_unique_id  TEXT,
    photo_checked_at TEXT
);
"""


def _as_before_071(path) -> None:
    """The database as it was before 071: `users` keyed by tg_id, with people and
    the rows that point at them."""
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DROP TABLE users")
        conn.executescript(OLD_USERS)
        conn.executemany(
            "INSERT INTO users (tg_id, username, created_at, updated_at) VALUES (?, ?, ?, ?)",
            [
                (222, "second", "2026-02-01T00:00:00", "2026-02-01T00:00:00"),
                (111, "first", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
            ],
        )
        conn.execute("INSERT INTO user_settings (tg_id) VALUES (111)")
        conn.execute("INSERT INTO user_settings (tg_id) VALUES (222)")
        conn.execute("DELETE FROM schema_migrations WHERE version = '071_person_id'")


async def test_migration_071_gives_everyone_an_id_and_keeps_what_points_at_them(
    tmp_path,
) -> None:
    path = tmp_path / "people.db"
    await (await Database(path).connect()).close()
    _as_before_071(path)

    database = await Database(path).connect()
    try:
        conn = database.conn
        people = await (await conn.execute("SELECT id, tg_id FROM users ORDER BY id")).fetchall()
        # Ids follow who joined first.
        assert [tuple(row) for row in people] == [(1, 111), (2, 222)]
        settings = await (await conn.execute("SELECT tg_id FROM user_settings")).fetchall()
        assert sorted(row[0] for row in settings) == [111, 222]
        assert await (await conn.execute("PRAGMA foreign_key_check")).fetchall() == []

        # Foreign keys are on again, and still reach users by tg_id.
        assert (await (await conn.execute("PRAGMA foreign_keys")).fetchone())[0] == 1
        await conn.execute("DELETE FROM users WHERE tg_id = 111")
        left = await (await conn.execute("SELECT tg_id FROM user_settings")).fetchall()
        assert [row[0] for row in left] == [222]
    finally:
        await database.close()


async def test_a_new_person_gets_the_next_id_and_may_have_no_telegram(repo: Repo) -> None:
    await repo.ensure_user(500, "someone")
    conn = repo._conn
    row = await (await conn.execute("SELECT id, tg_id FROM users WHERE tg_id = 500")).fetchone()
    assert row["id"] >= 1

    now = "2026-10-02T00:00:00"
    await conn.execute(
        "INSERT INTO users (tg_id, created_at, updated_at) VALUES (NULL, ?, ?)", (now, now)
    )
    await conn.execute(
        "INSERT INTO users (tg_id, created_at, updated_at) VALUES (NULL, ?, ?)", (now, now)
    )
    count = await (await conn.execute("SELECT COUNT(*) FROM users WHERE tg_id IS NULL")).fetchone()
    assert count[0] == 2
