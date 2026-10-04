"""A person's own id (#156): `users` is rebuilt around it (071), the tables about a
person move onto it (078), and nothing that pointed at a person through `tg_id` is
lost on the way."""

from __future__ import annotations

import sqlite3

import pytest

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


# user_settings as it was before 078, pointing at users(tg_id).
OLD_USER_SETTINGS = """
CREATE TABLE user_settings (
    tg_id            INTEGER PRIMARY KEY REFERENCES users(tg_id) ON DELETE CASCADE,
    rarity_mode      TEXT    NOT NULL DEFAULT 'all',
    muted_title_ids  TEXT    NOT NULL DEFAULT '[]',
    tz_offset_min    INTEGER,
    show_profile_links INTEGER NOT NULL DEFAULT 0,
    show_secrets     INTEGER NOT NULL DEFAULT 0,
    locale           TEXT    NOT NULL DEFAULT 'ru',
    notify_followers INTEGER NOT NULL DEFAULT 1
);
"""


def _as_before_071(path) -> None:
    """The database as it was before 071: `users` keyed by tg_id, with people and
    the rows that point at them."""
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DROP TABLE users")
        for table in ("user_settings", "account_links", "tokens", "subscriptions"):
            conn.execute(f"DROP TABLE {table}")
        conn.execute("DROP TABLE notification_throttle")
        conn.executescript(OLD_USERS)
        conn.executescript(OLD_USER_SETTINGS)
        conn.executescript(BEFORE_078)
        conn.executemany(
            "INSERT INTO users (tg_id, username, created_at, updated_at) VALUES (?, ?, ?, ?)",
            [
                (222, "second", "2026-02-01T00:00:00", "2026-02-01T00:00:00"),
                (111, "first", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
            ],
        )
        conn.execute("INSERT INTO user_settings (tg_id) VALUES (111)")
        conn.execute("INSERT INTO user_settings (tg_id) VALUES (222)")
        conn.execute(
            "DELETE FROM schema_migrations"
            " WHERE version IN ('071_person_id', '078_person_id_tables')"
        )


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
        # 078 then moved the settings onto the person id.
        settings = await (
            await conn.execute(
                "SELECT u.tg_id FROM user_settings s JOIN users u ON u.id = s.person_id"
            )
        ).fetchall()
        assert sorted(row[0] for row in settings) == [111, 222]
        assert await (await conn.execute("PRAGMA foreign_key_check")).fetchall() == []

        # Foreign keys are on again: deleting a person takes their settings.
        assert (await (await conn.execute("PRAGMA foreign_keys")).fetchone())[0] == 1
        await conn.execute("DELETE FROM users WHERE tg_id = 111")
        left = await (
            await conn.execute(
                "SELECT u.tg_id FROM user_settings s JOIN users u ON u.id = s.person_id"
            )
        ).fetchall()
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


# The other four tables as they were before 078, each pointing at users(tg_id).
BEFORE_078 = """
CREATE TABLE account_links (
    tg_id       INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    platform    TEXT NOT NULL,
    external_id TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    linked_at   TEXT NOT NULL,
    unlinked_at TEXT,
    publishes   INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (tg_id, platform, external_id),
    FOREIGN KEY (platform, external_id) REFERENCES accounts(platform, external_id)
);
CREATE UNIQUE INDEX idx_links_one_active_per_platform
    ON account_links(tg_id, platform) WHERE is_active = 1 AND platform <> 'psn';
CREATE UNIQUE INDEX idx_links_one_owner
    ON account_links(platform, external_id) WHERE is_active = 1;
CREATE TABLE tokens (
    tg_id             INTEGER PRIMARY KEY REFERENCES users(tg_id) ON DELETE CASCADE,
    refresh_token_enc BLOB NOT NULL,
    status            TEXT NOT NULL DEFAULT 'active',
    fail_count        INTEGER NOT NULL DEFAULT 0,
    last_refresh_at   TEXT,
    invalid_at        TEXT,
    notify_count      INTEGER NOT NULL DEFAULT 0,
    last_notified_at  TEXT,
    created_at        TEXT NOT NULL
);
CREATE TABLE subscriptions (
    chat_id     INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    tg_id       INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (chat_id, tg_id)
);
CREATE TABLE notification_throttle (
    tg_id             INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    chat_id           INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    window_started_at TEXT    NOT NULL,
    count_in_window   INTEGER NOT NULL DEFAULT 0,
    throttled         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tg_id, chat_id)
);
"""

NOW = "2026-10-01T00:00:00+00:00"


def _as_before_078(path) -> None:
    """The five tables as they were before 078, with a row or more in each."""
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        for table in ("account_links", "tokens", "subscriptions", "notification_throttle"):
            conn.execute(f"DROP TABLE {table}")
        conn.execute("DROP TABLE user_settings")
        conn.executescript(BEFORE_078)
        conn.executescript(OLD_USER_SETTINGS)
        conn.execute("INSERT INTO chats (chat_id, title, created_at) VALUES (-100, 'c', ?)", (NOW,))
        conn.executemany(
            "INSERT INTO accounts (platform, external_id, first_seen_at, updated_at)"
            " VALUES (?, ?, ?, ?)",
            [("xbox", "x1", NOW, NOW), ("psn", "p1", NOW, NOW), ("psn", "p2", NOW, NOW)],
        )
        conn.executemany(
            "INSERT INTO account_links (tg_id, platform, external_id, linked_at)"
            " VALUES (?, ?, ?, ?)",
            [(111, "xbox", "x1", NOW), (222, "psn", "p1", NOW), (222, "psn", "p2", NOW)],
        )
        conn.execute(
            "INSERT INTO tokens (tg_id, refresh_token_enc, created_at) VALUES (111, ?, ?)",
            (b"token", NOW),
        )
        conn.executemany(
            "INSERT INTO user_settings (tg_id, rarity_mode) VALUES (?, ?)",
            [(111, "rare"), (222, "all")],
        )
        conn.execute(
            "INSERT INTO subscriptions (chat_id, tg_id, created_at) VALUES (-100, 222, ?)", (NOW,)
        )
        conn.execute(
            "INSERT INTO notification_throttle (tg_id, chat_id, window_started_at)"
            " VALUES (222, -100, ?)",
            (NOW,),
        )
        conn.execute("DELETE FROM schema_migrations WHERE version = '078_person_id_tables'")


async def test_migration_078_moves_the_tables_about_a_person_onto_their_id(tmp_path) -> None:
    path = tmp_path / "people.db"
    database = await Database(path).connect()
    seed = Repo(database)
    await seed.ensure_user(111, "first")
    await seed.ensure_user(222, "second")
    await database.close()
    _as_before_078(path)

    database = await Database(path).connect()
    try:
        repo = Repo(database)
        conn = database.conn
        assert await (await conn.execute("PRAGMA foreign_key_check")).fetchall() == []
        # Read back through the repo, which still takes Telegram ids at its door.
        link = await repo.get_platform_link(111, "xbox")
        assert link is not None and link.external_id == "x1"
        psn = [link.external_id for link in await repo.platform_links_for(222, "psn")]
        assert psn == ["p1", "p2"]
        assert await repo.get_token(111) is not None
        settings = await repo.get_user_settings(111)
        assert settings is not None and settings.rarity_mode == "rare"
        assert await repo.is_subscribed(-100, 222)
        assert await repo.get_flood_state(222, -100) is not None
        # The index came back under its own name: still one Xbox account a person.
        await conn.execute(
            "INSERT INTO accounts (platform, external_id, first_seen_at, updated_at)"
            " VALUES ('xbox', 'x1b', ?, ?)",
            (NOW, NOW),
        )
        with pytest.raises(sqlite3.IntegrityError):
            await conn.execute(
                "INSERT INTO account_links (person_id, platform, external_id, linked_at)"
                " VALUES ((SELECT id FROM users WHERE tg_id = 111), 'xbox', 'x1b', ?)",
                (NOW,),
            )
    finally:
        await database.close()
