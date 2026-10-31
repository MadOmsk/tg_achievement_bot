"""The transfer from SQLite to PostgreSQL (#234), on a source made by the real
SQLite schema, into a database of its own: `reset_test_data` never sees it."""

from __future__ import annotations

import json
import os
import sqlite3
import zlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest

from bot.db.repo._games_db import CATALOG_TABLES, GAMES_DB_KEY
from scripts import sqlite_to_pg as tool

SECRET_EMAIL = "someone.private@example.org"
NOW = "2026-10-31T12:00:00+00:00"
DB_DIR = Path(tool.__file__).resolve().parent.parent / "bot" / "db"
BASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://localhost:5433/unlocked_tests_transfer?user=postgres"
)


@pytest.fixture
def dsn() -> Iterator[str]:
    head, _, tail = BASE_URL.rpartition("/")
    name, sep, query = tail.partition("?")
    own = f"{name}_import"
    admin = psycopg.connect(f"{head}/postgres{sep}{query}", autocommit=True)
    admin.execute(f'DROP DATABASE IF EXISTS "{own}" WITH (FORCE)')
    admin.execute(f"CREATE DATABASE \"{own}\" TEMPLATE template0 ENCODING 'UTF8'")
    try:
        yield f"{head}/{own}{sep}{query}"
    finally:
        admin.execute(f'DROP DATABASE IF EXISTS "{own}" WITH (FORCE)')
        admin.close()


def _insert(conn: sqlite3.Connection, table: str, **values: Any) -> None:
    names = ", ".join(f'"{n}"' for n in values)
    marks = ", ".join("?" * len(values))
    conn.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})", list(values.values()))


def _fresh(path: Path) -> sqlite3.Connection:
    """A database as a new bot made it: schema.sql, its migrations baselined."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript((DB_DIR / "schema.sql").read_text(encoding="utf-8"))
    # The old bring-up's own table, not in schema.sql.
    conn.execute(
        "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    for migration in sorted((DB_DIR / "migrations").glob("*.sql")):
        _insert(conn, "schema_migrations", version=migration.stem, applied_at=NOW)
    return conn


def _fill_server(conn: sqlite3.Connection) -> None:
    # Ids with gaps, a person without Telegram, every date form.
    _insert(conn, "users", id=5, tg_id=500, handle="Alpha", created_at=NOW, updated_at=NOW)
    _insert(
        conn,
        "users",
        id=9,
        email=SECRET_EMAIL,
        handle="Бета".encode().decode(),
        created_at="2026-10-31T12:00:00Z",
        updated_at="2026-10-31 12:00:00",
    )
    for external in ("x2", "x1", "x3"):
        _insert(
            conn,
            "accounts",
            platform="xbox",
            external_id=external,
            display_name=f"Name {external}",
            first_seen_at=NOW,
            updated_at=NOW,
        )
    # Links in an order no key would give: `seq` must keep it.
    for person, external in ((9, "x2"), (5, "x1"), (5, "x3")):
        _insert(
            conn,
            "account_links",
            person_id=person,
            platform="xbox",
            external_id=external,
            is_active=0 if external == "x3" else 1,
            linked_at=NOW,
        )
    _insert(
        conn,
        "seen_achievements",
        platform="xbox_modern",
        xuid="x1",
        title_id="100",
        achievement_id="1",
        created_at=NOW,
        rarity_percent=0.1 + 0.2,
    )
    _insert(
        conn, "favorite_games", person_id=5, game_id=1, anchor_key="steam:100:steam", created_at=NOW
    )
    _insert(conn, "pass_items", item_id=7, kind="game", game_id=1, title="Prize", created_at=NOW)
    _insert(conn, "app_settings", key="some_setting", value="42", updated_at=NOW)


def _fill_catalog(conn: sqlite3.Connection, title: str = "100", game_id: int = 1) -> None:
    version_id = game_id * 10
    _insert(
        conn,
        "achievement_list_connectors",
        platform="steam",
        title_id=title,
        name="Игра",
        updated_at=NOW,
    )
    # An order no key would give.
    for achievement in ("z", "a", "m"):
        _insert(
            conn,
            "title_achievements",
            platform="steam",
            title_id=title,
            achievement_id=achievement,
            name_en=f"Name {achievement}",
            rarity_percent=12.5,
            updated_at=NOW,
        )
    _insert(
        conn,
        "versions",
        version_id=version_id,
        store="steam",
        product_id=title,
        console="steam",
        platform="steam",
        title_id=title,
        name="Game",
        updated_at=NOW,
    )
    _insert(
        conn,
        "games",
        game_id=game_id,
        name="Game",
        anchor_version_id=version_id,
        created_at=NOW,
        updated_at=NOW,
    )
    conn.execute(
        "UPDATE versions SET game_id = ?, role = 'version' WHERE version_id = ?",
        (game_id, version_id),
    )
    _insert(conn, "dlcs", version_id=version_id, store_id=f"d{title}", name="DLC", updated_at=NOW)
    _insert(
        conn,
        "editions",
        edition_id=game_id,
        store="steam",
        store_id=f"e{title}",
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    for store_id in ("9", "1", "5"):
        _insert(conn, "edition_items", edition_id=game_id, store_id=store_id, item_kind="game")
    hltb = int(title) + 1000
    _insert(
        conn, "hltb_entries", hltb_id=hltb, name="Game", release_world="2021-03-04", checked_at=NOW
    )
    _insert(conn, "hltb_platform_times", hltb_id=hltb, platform="PC", comp_main=3600)
    _insert(conn, "version_hltb", version_id=version_id, hltb_id=hltb, source="auto", score=0.97)
    _insert(
        conn,
        "source_payloads",
        subject=f"steam:{title}",
        source="steam_store",
        fetched_at=NOW,
        sha256="0" * 64,
        payload=zlib.compress(b"\x00\xffbinary payload"),
    )
    _insert(
        conn,
        "fetch_state",
        subject=f"steam:{title}",
        source="store",
        status="ok",
        checked_at=NOW,
        next_check_at=NOW,
    )


def _source(tmp_path: Path, name: str = "bot.db", fill: bool = True) -> Path:
    """One file, as on the dev server."""
    path = tmp_path / name
    conn = _fresh(path)
    if fill:
        _fill_server(conn)
        _fill_catalog(conn)
    conn.commit()
    conn.close()
    return path


def _split_source(tmp_path: Path, name: str, catalog_fill=_fill_catalog) -> tuple[Path, Path]:
    """As on the VPS: the server's file names its catalog's. `games` is a
    separate file with only the catalog's tables, and the server's lacks them."""
    db, games = tmp_path / f"{name}.db", tmp_path / f"{name}.games.db"
    conn = _fresh(db)
    _fill_server(conn)
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in CATALOG_TABLES:
        conn.execute(f"DROP TABLE {table}")
    _insert(conn, "app_settings", key=GAMES_DB_KEY, value=str(games), updated_at=NOW)
    conn.commit()
    conn.close()
    conn = _fresh(games)
    conn.execute("PRAGMA foreign_keys = OFF")
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    for table in tables:
        if table not in CATALOG_TABLES and not table.startswith("sqlite_"):
            conn.execute(f"DROP TABLE {table}")
    catalog_fill(conn)
    conn.commit()
    conn.close()
    return db, games


def _edit(path: Path, statement: str, *params: Any) -> None:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA ignore_check_constraints = ON")
    conn.execute(statement, params)
    conn.commit()
    conn.close()


def _rows(dsn: str, query: str, *params: Any) -> list[tuple[Any, ...]]:
    with psycopg.connect(dsn) as pg:
        return pg.execute(query, params or None).fetchall()


def _run(dsn: str, statement: str, *params: Any) -> None:
    with psycopg.connect(dsn) as pg:
        pg.execute(statement, params or None)


def test_full_import_then_verify(tmp_path: Path, dsn: str, capsys: pytest.CaptureFixture) -> None:
    db = _source(tmp_path)
    result = tool.run_import(db, None, dsn, "prod")
    assert result.catalog == "imported"
    assert result.tables["users"] == 2
    assert result.tables["schema_migrations"] == 147
    assert tool.run_verify(db, None, dsn, "prod") == []

    # Values as they were, in every kind of column.
    assert _rows(dsn, "SELECT email FROM prod.users WHERE id = 9") == [(SECRET_EMAIL,)]
    assert _rows(dsn, "SELECT updated_at FROM prod.users WHERE id = 9") == [
        ("2026-10-31 12:00:00",)
    ]
    assert _rows(dsn, "SELECT rarity_percent, account_platform FROM prod.seen_achievements") == [
        (0.1 + 0.2, "xbox")
    ]
    assert _rows(dsn, "SELECT payload FROM games.source_payloads")[0][0] == zlib.compress(
        b"\x00\xffbinary payload"
    )
    assert _rows(dsn, "SELECT release_year FROM games.hltb_entries") == [(2021,)]
    assert _rows(dsn, "SELECT value FROM prod.app_settings WHERE key = 'some_setting'") == [("42",)]

    # Nothing of a person's in the report.
    assert SECRET_EMAIL not in capsys.readouterr().out


def test_a_split_source_and_its_file_setting(tmp_path: Path, dsn: str) -> None:
    db, _games = _split_source(tmp_path, "bot")
    tool.run_import(db, None, dsn, "prod")
    assert tool.run_verify(db, None, dsn, "prod") == []
    assert _rows(dsn, "SELECT 1 FROM prod.app_settings WHERE key = %s", GAMES_DB_KEY) == []
    assert _rows(dsn, "SELECT COUNT(*) FROM games.versions") == [(1,)]


def test_a_copy_elsewhere_names_its_games_file(tmp_path: Path, dsn: str) -> None:
    db, games = _split_source(tmp_path, "bot")
    moved = games.rename(tmp_path / "elsewhere.db")
    with pytest.raises(tool.TransferError, match="--games"):
        tool.run_import(db, None, dsn, "prod")
    tool.run_import(db, moved, dsn, "prod")
    assert tool.run_verify(db, moved, dsn, "prod") == []


@pytest.mark.parametrize(
    ("change", "table"),
    [
        ("UPDATE prod.users SET handle = 'Changed' WHERE id = 9", "users"),
        ("UPDATE prod.users SET email = NULL WHERE id = 9", "users"),
        # 0.1 + 0.2 and 0.3 are nearest doubles, which a rounded text form blurs.
        ("UPDATE prod.seen_achievements SET rarity_percent = 0.3", "seen_achievements"),
        ("INSERT INTO prod.chats (chat_id, created_at) VALUES (77, 'x')", "chats"),
    ],
)
def test_verify_catches_a_changed_row_in_postgres(
    tmp_path: Path, dsn: str, change: str, table: str
) -> None:
    db = _source(tmp_path)
    tool.run_import(db, None, dsn, "prod")
    _run(dsn, change)
    assert any(w.startswith(table) for w in tool.run_verify(db, None, dsn, "prod"))


def test_verify_names_columns_and_keeps_values_to_itself(
    tmp_path: Path, dsn: str, capsys: pytest.CaptureFixture
) -> None:
    db = _source(tmp_path)
    tool.run_import(db, None, dsn, "prod")
    _run(dsn, "UPDATE prod.users SET email = 'other@example.org' WHERE id = 9")
    capsys.readouterr()
    wrong = tool.run_verify(db, None, dsn, "prod")
    assert any("email (1)" in w and "[(9,)]" in w for w in wrong)
    out = capsys.readouterr().out
    assert SECRET_EMAIL not in out
    assert "other@example.org" not in out


def test_verify_catches_a_row_gone_a_type_flip_and_a_catalog_change(
    tmp_path: Path, dsn: str
) -> None:
    db = _source(tmp_path)
    tool.run_import(db, None, dsn, "prod")
    _run(dsn, "DELETE FROM games.fetch_state")
    _run(dsn, "UPDATE games.hltb_entries SET comp_main = 0")
    _run(dsn, "UPDATE games.source_payloads SET payload = '\\x00'")
    wrong = "\n".join(tool.run_verify(db, None, dsn, "prod"))
    assert "fetch_state" in wrong
    assert "hltb_entries" in wrong
    assert "source_payloads" in wrong


def test_null_and_empty_text_are_told_apart(tmp_path: Path, dsn: str) -> None:
    db = _source(tmp_path)
    tool.run_import(db, None, dsn, "prod")
    _run(dsn, "UPDATE prod.users SET last_name = '' WHERE id = 5")
    assert any(w.startswith("users") for w in tool.run_verify(db, None, dsn, "prod"))


def test_seq_keeps_the_order_rows_came_in(tmp_path: Path, dsn: str) -> None:
    db = _source(tmp_path)
    tool.run_import(db, None, dsn, "prod")
    names = _rows(dsn, "SELECT achievement_id FROM games.title_achievements ORDER BY seq")
    assert [r[0] for r in names] == ["z", "a", "m"]
    items = _rows(dsn, "SELECT store_id FROM games.edition_items ORDER BY seq")
    assert [r[0] for r in items] == ["9", "1", "5"]
    links = _rows(dsn, "SELECT external_id FROM prod.account_links ORDER BY seq")
    assert [r[0] for r in links] == ["x2", "x1", "x3"]


def test_counters_go_on_after_the_import(tmp_path: Path, dsn: str) -> None:
    db = _source(tmp_path)
    tool.run_import(db, None, dsn, "prod")
    made = _rows(
        dsn,
        "INSERT INTO prod.users (tg_id, created_at, updated_at) VALUES (600, 'x', 'x')"
        " RETURNING id",
    )
    assert made == [(10,)]
    # A table with nothing in it starts at 1.
    assert _rows(
        dsn,
        "INSERT INTO games.series (name, created_at, updated_at) VALUES ('s', 'x', 'x')"
        " RETURNING series_id",
    ) == [(1,)]
    assert _rows(
        dsn,
        "INSERT INTO games.versions (store, product_id, console, updated_at)"
        " VALUES ('s', 'p', 'c', 'x') RETURNING version_id",
    ) == [(11,)]
    assert _rows(
        dsn,
        "INSERT INTO games.title_achievements (platform, title_id, achievement_id, updated_at)"
        " VALUES ('psn', 't', 'a', 'x') RETURNING seq",
    ) == [(4,)]
    assert tool.run_verify(db, None, dsn, "prod") != []  # the rows are extra, the counters fine


def test_a_group_s_negative_chat_id_leaves_the_counter_at_its_start(
    tmp_path: Path, dsn: str
) -> None:
    db = _source(tmp_path)
    _edit(db, "UPDATE chats SET chat_id = -chat_id WHERE chat_id > 0")
    tool.run_import(db, None, dsn, "prod")
    assert tool.run_verify(db, None, dsn, "prod") == []


def test_a_counter_goes_past_a_deleted_highest_row(tmp_path: Path, dsn: str) -> None:
    db = _source(tmp_path)
    _edit(db, "INSERT OR REPLACE INTO sqlite_sequence (name, seq) VALUES ('users', 500)")
    tool.run_import(db, None, dsn, "prod")
    made = _rows(
        dsn,
        "INSERT INTO prod.users (tg_id, created_at, updated_at) VALUES (600, 'x', 'x')"
        " RETURNING id",
    )
    assert made == [(501,)]


def test_bring_up_works_on_copies_and_leaves_the_source_alone(tmp_path: Path, dsn: str) -> None:
    db = _source(tmp_path)
    _edit(db, "ALTER TABLE push_subscriptions DROP COLUMN origin")
    _edit(db, "DELETE FROM schema_migrations WHERE version LIKE '143%'")
    copy, _ = tool.run_bring_up(db, None, tmp_path / "up")

    def has(path: Path) -> tuple[bool, bool]:
        conn = sqlite3.connect(path)
        try:
            columns = [r[1] for r in conn.execute("PRAGMA table_info(push_subscriptions)")]
            done = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version LIKE '143%'"
            ).fetchone()
            return "origin" in columns, done is not None
        finally:
            conn.close()

    assert has(db) == (False, False)
    assert has(copy) == (True, True)
    tool.run_import(copy, None, dsn, "prod")
    assert tool.run_verify(copy, None, dsn, "prod") == []


def test_verify_catches_a_counter_left_behind(tmp_path: Path, dsn: str) -> None:
    db = _source(tmp_path)
    tool.run_import(db, None, dsn, "prod")
    _run(dsn, "ALTER TABLE prod.users ALTER COLUMN id RESTART WITH 1")
    assert any("users.id" in w for w in tool.run_verify(db, None, dsn, "prod"))


def test_the_bot_comes_up_on_what_was_imported(tmp_path: Path, dsn: str) -> None:
    from bot.db import tools
    from bot.db.repo import Database

    db = _source(tmp_path)
    tool.run_import(db, None, dsn, "prod")

    async def bring_up() -> int:
        database = await Database(dsn, schema="prod").connect()
        try:
            cursor = await database.conn.execute("SELECT COUNT(*) FROM schema_migrations")
            return (await cursor.fetchone())[0]
        finally:
            await database.close()

    assert tools.run(bring_up()) == 150


@pytest.mark.parametrize(
    ("kind", "statement", "params"),
    [
        ("text_in_numeric", "UPDATE users SET is_excluded = 'yes' WHERE id = 5", ()),
        ("real_in_integer", "UPDATE users SET is_excluded = 1.5 WHERE id = 5", ()),
        ("blob_in_numeric", "UPDATE users SET is_excluded = x'00ff' WHERE id = 5", ()),
        ("nul_in_text", "UPDATE users SET first_name = ? WHERE id = 5", ("a\0b",)),
        ("broken_utf8", "UPDATE users SET first_name = CAST(x'ff41' AS TEXT) WHERE id = 5", ()),
        ("blob_in_text", "UPDATE users SET first_name = x'41' WHERE id = 5", ()),
        ("orphan", "DELETE FROM users WHERE id = 9", ()),
        ("source_only_table", "CREATE TABLE left_over (x)", ()),
        ("source_only_column", "ALTER TABLE users ADD COLUMN old_thing TEXT", ()),
        ("migrations_missing", "DELETE FROM schema_migrations WHERE version LIKE '143%'", ()),
    ],
)
def test_preflight_finds_it_and_refuses(
    tmp_path: Path,
    dsn: str,
    capsys: pytest.CaptureFixture,
    kind: str,
    statement: str,
    params: tuple,
) -> None:
    db = _source(tmp_path)
    _edit(db, statement, *params)
    with pytest.raises(tool.TransferError, match="refused"):
        tool.run_import(db, None, dsn, "prod")
    assert kind in capsys.readouterr().out
    # Nothing landed, the target's schemas not even made.
    assert not _rows(
        dsn, "SELECT 1 FROM information_schema.tables WHERE table_schema IN ('prod', 'games')"
    )


@pytest.mark.parametrize(
    ("statement", "params", "check", "expected"),
    [
        (
            "UPDATE users SET is_excluded = '1' WHERE id = 5",
            (),
            "SELECT is_excluded FROM prod.users WHERE id = 5",
            [(1,)],
        ),
        (
            "UPDATE users SET first_name = ? WHERE id = 5",
            ("a\0b",),
            "SELECT first_name FROM prod.users WHERE id = 5",
            [("ab",)],
        ),
        (
            "UPDATE users SET first_name = CAST(x'ff41' AS TEXT) WHERE id = 5",
            (),
            "SELECT first_name FROM prod.users WHERE id = 5",
            [("�A",)],
        ),
        # A person gone: the links hanging on them go, the seen rows stay.
        (
            "DELETE FROM users WHERE id = 9",
            (),
            "SELECT external_id FROM prod.account_links ORDER BY seq",
            [("x1",), ("x3",)],
        ),
        # ON DELETE SET NULL: the row stays, its reference goes.
        (
            "UPDATE pass_items SET created_by = 12345",
            (),
            "SELECT created_by FROM prod.pass_items",
            [(None,)],
        ),
    ],
)
def test_accepted_problems_are_repaired_and_verify_agrees(
    tmp_path: Path, dsn: str, statement: str, params: tuple, check: str, expected: list
) -> None:
    db = _source(tmp_path)
    _edit(db, statement, *params)
    tool.run_import(db, None, dsn, "prod", accept=True)
    assert _rows(dsn, check) == expected
    assert tool.run_verify(db, None, dsn, "prod", accept=True) == []


def test_orphans_that_hang_on_orphans_go_too(tmp_path: Path, dsn: str) -> None:
    db = _source(tmp_path)
    _edit(db, "UPDATE games SET merged_into = 999")  # set null? no: no action
    _edit(db, "UPDATE versions SET of_version_id = 12345")
    tool.run_import(db, None, dsn, "prod", accept=True)
    # games.merged_into has no action: the game goes, and its relations with it.
    assert _rows(dsn, "SELECT COUNT(*) FROM games.games") == [(0,)]
    assert _rows(dsn, "SELECT of_version_id, game_id FROM games.versions") == [(None, None)]
    assert tool.run_verify(db, None, dsn, "prod", accept=True) == []


def test_what_no_flag_can_answer_is_refused(tmp_path: Path, dsn: str) -> None:
    db = tmp_path / "bot.db"
    conn = _fresh(db)
    conn.execute("PRAGMA foreign_keys = OFF")
    # A NOT NULL of PostgreSQL's that an old file never had.
    conn.execute("ALTER TABLE users RENAME TO users_old")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, created_at TEXT, updated_at TEXT)")
    conn.execute("INSERT INTO users (id) VALUES (1)")
    conn.execute("DROP TABLE users_old")
    conn.commit()
    conn.close()
    with pytest.raises(tool.TransferError, match="no flag"):
        tool.run_import(db, None, dsn, "prod", accept=True)


def test_postgres_own_refusal_never_quotes_the_row(tmp_path: Path, dsn: str) -> None:
    db = _source(tmp_path)
    # A CHECK of PostgreSQL's, reached past the preflight: its message would
    # print the whole row.
    _edit(db, "UPDATE users SET activity_visible = 'bad', email = ? WHERE id = 9", SECRET_EMAIL)
    with pytest.raises(tool.TransferError) as refused:
        tool.run_import(db, None, dsn, "prod")
    assert SECRET_EMAIL not in str(refused.value)
    assert "23514" in str(refused.value)


def test_a_filled_schema_is_refused(tmp_path: Path, dsn: str) -> None:
    db = _source(tmp_path)
    tool.run_import(db, None, dsn, "prod")
    with pytest.raises(tool.TransferError, match="has rows in"):
        tool.run_import(db, None, dsn, "prod")


def test_a_failed_import_leaves_nothing(tmp_path: Path, dsn: str) -> None:
    db = _source(tmp_path)
    _edit(db, "UPDATE users SET activity_visible = 'bad' WHERE id = 9")
    with pytest.raises(tool.TransferError):
        tool.run_import(db, None, dsn, "prod")
    assert not _rows(
        dsn, "SELECT 1 FROM information_schema.tables WHERE table_schema IN ('prod', 'games')"
    )


def test_a_dry_run_writes_nothing_and_moves_no_counter(tmp_path: Path, dsn: str) -> None:
    db = _source(tmp_path)
    tool.run_import(db, None, dsn, "prod", dry_run=True)
    assert not _rows(
        dsn, "SELECT 1 FROM information_schema.tables WHERE table_schema IN ('prod', 'games')"
    )
    tool.run_import(db, None, dsn, "prod")
    assert tool.run_verify(db, None, dsn, "prod") == []


def test_the_source_is_not_written(tmp_path: Path, dsn: str) -> None:
    db = _source(tmp_path)
    _edit(db, "UPDATE pass_items SET created_by = 12345")
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    before = db.read_bytes()
    tool.run_import(db, None, dsn, "prod", accept=True)
    assert db.read_bytes() == before


def test_a_second_server_on_the_same_catalog(tmp_path: Path, dsn: str, capsys) -> None:
    prod, games = _split_source(tmp_path, "bot")
    test = tmp_path / "test.db"
    conn = _fresh(test)
    _fill_server(conn)
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in CATALOG_TABLES:
        conn.execute(f"DROP TABLE {table}")
    _insert(conn, "app_settings", key=GAMES_DB_KEY, value=str(games), updated_at=NOW)
    conn.commit()
    conn.close()

    assert tool.run_import(prod, None, dsn, "prod").catalog == "imported"
    capsys.readouterr()
    assert tool.run_import(test, None, dsn, "test").catalog == "identical"
    assert "skipped" in capsys.readouterr().out
    assert _rows(dsn, "SELECT COUNT(*) FROM games.versions") == [(1,)]
    assert _rows(dsn, "SELECT COUNT(*) FROM test.users") == [(2,)]
    assert tool.run_verify(test, None, dsn, "test") == []
    assert tool.run_verify(prod, None, dsn, "prod") == []


def _second_catalog(conn: sqlite3.Connection) -> None:
    """The same game under other ids, and a list only this server knew, whose
    ids collide with the first server's."""
    _insert(
        conn,
        "achievement_list_connectors",
        platform="steam",
        title_id="100",
        name="Игра",
        updated_at=NOW,
    )
    _insert(
        conn,
        "versions",
        version_id=10,
        store="psn",
        product_id="other",
        console="ps5",
        name="Unrelated, under the first server's id",
        updated_at=NOW,
    )
    _insert(
        conn,
        "versions",
        version_id=33,
        store="steam",
        product_id="100",
        console="steam",
        platform="steam",
        title_id="100",
        name="Game",
        updated_at=NOW,
    )
    _insert(
        conn, "games", game_id=3, name="Game", anchor_version_id=33, created_at=NOW, updated_at=NOW
    )
    conn.execute("UPDATE versions SET game_id = 3, role = 'version' WHERE version_id = 33")
    # Only this server's: a list, its achievements, and a version under the
    # id the first server gave its own game's version.
    _insert(
        conn,
        "achievement_list_connectors",
        platform="steam",
        title_id="200",
        name="Вторая",
        updated_at=NOW,
    )
    for achievement in ("b", "a"):
        _insert(
            conn,
            "title_achievements",
            platform="steam",
            title_id="200",
            achievement_id=achievement,
            updated_at=NOW,
        )
    _insert(
        conn,
        "versions",
        version_id=1,
        store="steam",
        product_id="200",
        console="steam",
        platform="steam",
        title_id="200",
        name="Second",
        stand_in=1,
        updated_at=NOW,
    )
    _insert(
        conn, "games", game_id=1, name="Second", anchor_version_id=1, created_at=NOW, updated_at=NOW
    )
    conn.execute("UPDATE versions SET game_id = 1, role = 'version' WHERE version_id = 1")
    _insert(conn, "dlcs", dlc_id=1, version_id=1, store_id="d200", name="Its DLC", updated_at=NOW)
    _insert(conn, "hltb_entries", hltb_id=1100, name="First server's entry, older", checked_at=NOW)
    _insert(conn, "hltb_platform_times", hltb_id=1100, platform="PS5", comp_main=1)
    _insert(conn, "hltb_entries", hltb_id=2200, name="Second", checked_at=NOW)
    _insert(conn, "hltb_platform_times", hltb_id=2200, platform="PC", comp_main=2)
    _insert(conn, "version_hltb", version_id=1, hltb_id=2200, source="auto", score=0.9)
    # Stands for answers that give way: never carried.
    _insert(
        conn,
        "fetch_state",
        subject="steam:200",
        source="store",
        status="ok",
        checked_at=NOW,
        next_check_at=NOW,
    )


def _second_server(tmp_path: Path) -> Path:
    db, _games = _split_source(tmp_path, "test", _second_catalog)
    # This server's person favored game 3 here, game 1 there, 99 nowhere.
    _edit(db, "DELETE FROM favorite_games")
    _edit(db, "UPDATE pass_items SET game_id = 3")
    _edit(
        db,
        "INSERT INTO favorite_games (person_id, game_id, anchor_key, created_at)"
        f" VALUES (5, 3, 'steam:100:steam', '{NOW}'), (9, 99, 'gone:1:x', '{NOW}')",
    )
    return db


def test_a_differing_catalog_is_refused_with_its_counts(
    tmp_path: Path, dsn: str, capsys: pytest.CaptureFixture
) -> None:
    prod = _source(tmp_path)
    tool.run_import(prod, None, dsn, "prod")
    test = _second_server(tmp_path)
    capsys.readouterr()
    with pytest.raises(tool.TransferError, match="--merge-catalog"):
        tool.run_import(test, None, dsn, "test")
    out = capsys.readouterr().out
    assert "achievement_list_connectors" in out
    assert "stand-ins for lists 1" in out
    assert not _rows(dsn, "SELECT 1 FROM information_schema.tables WHERE table_schema = 'test'")
    assert _rows(dsn, "SELECT COUNT(*) FROM games.versions") == [(1,)]


def test_a_merge_maps_its_ids(tmp_path: Path, dsn: str) -> None:
    prod = _source(tmp_path)
    tool.run_import(prod, None, dsn, "prod")
    test = _second_server(tmp_path)
    before = _rows(dsn, "SELECT version_id, name, game_id FROM games.versions")

    result = tool.run_import(test, None, dsn, "test", merge=True)
    assert result.catalog == "merged"

    # The first server's rows stand; the kept stand-in has a new id, not 1.
    assert (
        _rows(dsn, "SELECT version_id, name, game_id FROM games.versions WHERE version_id = 10")
        == before
    )
    kept = _rows(dsn, "SELECT version_id FROM games.versions WHERE product_id = '200'")
    assert kept == [(result.kept[0],)]
    new_id = result.kept[0]
    assert new_id not in (1, 10, 33)

    # What pointed at it came along, under the new id.
    assert _rows(
        dsn, "SELECT version_id, hltb_id FROM games.version_hltb WHERE hltb_id = 2200"
    ) == [(new_id, 2200)]
    assert _rows(dsn, "SELECT version_id, name FROM games.dlcs WHERE store_id = 'd200'") == [
        (new_id, "Its DLC")
    ]
    # Facts added; seq going on after the catalog's own.
    assert _rows(
        dsn,
        "SELECT achievement_id, seq FROM games.title_achievements WHERE title_id = '200'"
        " ORDER BY seq",
    ) == [("b", 4), ("a", 5)]
    # An entry the catalog had keeps its own rows; a new one brings its.
    assert _rows(dsn, "SELECT name FROM games.hltb_entries WHERE hltb_id = 1100") == [("Game",)]
    assert _rows(dsn, "SELECT platform FROM games.hltb_platform_times WHERE hltb_id = 1100") == [
        ("PC",)
    ]
    assert _rows(dsn, "SELECT comp_main FROM games.hltb_platform_times WHERE hltb_id = 2200") == [
        (2,)
    ]
    # A version under the first server's id, of no list: gave way, did not collide.
    assert not _rows(dsn, "SELECT 1 FROM games.versions WHERE product_id = 'other'")
    assert not _rows(dsn, "SELECT 1 FROM games.fetch_state WHERE subject = 'steam:200'")
    # Linked into a game after.
    linked = _rows(dsn, "SELECT game_id FROM games.versions WHERE version_id = %s", new_id)
    assert linked[0][0] is not None
    assert linked[0][0] != 1

    # The server's own catalog ids now name the catalog's game: 3 here is 1 there.
    assert _rows(dsn, "SELECT game_id FROM test.favorite_games") == [(1,)]
    assert _rows(dsn, "SELECT game_id FROM test.pass_items") == [(1,)]

    # A new row's counter is free.
    assert (
        _rows(
            dsn,
            "INSERT INTO games.versions (store, product_id, console, updated_at)"
            " VALUES ('s', 'p', 'c', 'x') RETURNING version_id",
        )[0][0]
        > new_id
    )
    _run(dsn, "DELETE FROM games.versions WHERE store = 's'")

    assert tool.run_verify(test, None, dsn, "test", merge=True) == []
    # The first server's rows untouched.
    assert tool.run_verify(prod, None, dsn, "prod", merge=True) == []
    # Held to exact, the two catalogs differ.
    assert tool.run_verify(test, None, dsn, "test") != []


def test_a_catalog_with_nothing_new_is_skipped(tmp_path: Path, dsn: str, capsys) -> None:
    prod = _source(tmp_path)
    tool.run_import(prod, None, dsn, "prod")
    # The bot, or the first server, learned more meanwhile.
    _run(dsn, "UPDATE games.versions SET name = 'Learned since'")
    test, _games = _split_source(tmp_path, "test")
    capsys.readouterr()
    result = tool.run_import(test, None, dsn, "test")
    assert result.catalog == "nothing_lacking"
    assert "nothing games lacks" in capsys.readouterr().out
    assert _rows(dsn, "SELECT name FROM games.versions") == [("Learned since",)]
    assert tool.run_verify(test, None, dsn, "test", merge=True) == []
    assert tool.run_verify(test, None, dsn, "test") != []


def test_the_command_exits_as_it_found(tmp_path: Path, dsn: str, monkeypatch) -> None:
    db = _source(tmp_path)
    base = ["sqlite_to_pg", "--db", str(db), "--dsn", dsn, "--schema", "dev"]

    def run(mode: str) -> int:
        monkeypatch.setattr("sys.argv", [base[0], mode, *base[1:]])
        return tool.main()

    assert run("preflight") == 0
    assert run("import") == 0
    assert run("verify") == 0
    assert run("import") == 2  # the schema is filled
    _run(dsn, "UPDATE dev.users SET handle = 'Changed' WHERE id = 5")
    assert run("verify") == 1


def test_a_merge_keeps_a_favorite_and_a_prize_whose_anchor_changed(
    tmp_path: Path, dsn: str
) -> None:
    tool.run_import(_source(tmp_path), None, dsn, "prod")
    test = _second_server(tmp_path)
    conn = sqlite3.connect(tmp_path / "test.games.db")
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "INSERT INTO versions (version_id, store, product_id, console, name, game_id, role,"
        " updated_at, stand_in) VALUES (77, 'list', 'old', 'steam', 'x', 3, 'version', ?, 1)",
        (NOW,),
    )
    conn.execute("UPDATE games SET anchor_version_id = 77 WHERE game_id = 3")
    conn.commit()
    conn.close()
    _edit(test, "UPDATE favorite_games SET anchor_key = 'list:old:steam' WHERE game_id = 3")
    tool.run_import(test, None, dsn, "test", merge=True)
    assert _rows(dsn, "SELECT COUNT(*) FROM test.favorite_games") == [(1,)]
    assert _rows(dsn, "SELECT game_id IS NOT NULL FROM test.pass_items") == [(True,)]


def test_a_merge_maps_the_game_a_waiting_change_names(tmp_path: Path, dsn: str) -> None:
    tool.run_import(_source(tmp_path), None, dsn, "prod")
    test = _second_server(tmp_path)
    _edit(test, "UPDATE pass_items SET pending = ?", json.dumps({"game_id": 3, "title": "t"}))
    tool.run_import(test, None, dsn, "test", merge=True)
    ((game, pending),) = _rows(dsn, "SELECT game_id, pending FROM test.pass_items")
    assert json.loads(pending) == {"game_id": game, "title": "t"}


def test_a_merge_never_rewinds_the_catalog_s_counters(tmp_path: Path, dsn: str) -> None:
    tool.run_import(_source(tmp_path), None, dsn, "prod")
    seq = _rows(dsn, "SELECT pg_get_serial_sequence('games.games', 'game_id')")[0][0]
    _run(dsn, f"SELECT setval('{seq}', 5000, true)")
    tool.run_import(_second_server(tmp_path), None, dsn, "test", merge=True)
    assert _rows(dsn, f"SELECT last_value FROM {seq}")[0][0] >= 5000
