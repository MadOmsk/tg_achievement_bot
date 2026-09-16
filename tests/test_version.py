"""The version string, and the check that refuses a database from the future
(#56)."""

from __future__ import annotations

import pytest

from bot.db.repo._database import Database, SchemaTooNewError
from bot.version import BRANCH, MAJOR, expected_schema, schema_gap, version


def test_the_version_names_the_branch_and_the_schema_it_expects() -> None:
    parts = version().split(".")

    assert parts[0] == str(MAJOR)
    assert parts[1] == str(BRANCH)
    # Commits since this branch left main — a number, or "?" where git
    # cannot answer at all (a tarball, a container with no .git).
    assert parts[2].isdigit() or parts[2] == "?"
    assert parts[3] == expected_schema()
    assert parts[3].isdigit() and len(parts[3]) == 3


def test_the_revision_counts_from_the_fork_point_not_from_main_s_tip() -> None:
    """Measured against the merge base, so somebody else merging into main
    does not renumber this branch's builds."""
    import subprocess

    from bot.version import REPO, revision

    base = subprocess.run(
        ["git", "merge-base", "origin/main", "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if not base:
        return  # no origin/main here (a shallow CI checkout) — nothing to compare
    expected = subprocess.run(
        ["git", "rev-list", "--count", f"{base}..HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()

    assert revision() == expected


def test_a_database_behind_the_code_is_normal() -> None:
    """Every upgrade passes through this state; it is what migrations are
    for."""
    assert schema_gap("001_initial") is None
    assert schema_gap(f"{expected_schema()}_whatever") is None


def test_a_database_that_is_never_been_migrated_is_normal() -> None:
    assert schema_gap(None) is None


def test_a_database_ahead_of_the_code_is_refused() -> None:
    """The 2026-09-14 outage: a newer branch's migrations landed in
    production's own file, and the running bot then crashed on tables it had
    never heard of."""
    complaint = schema_gap("999_from_the_future")

    assert complaint is not None
    assert "999" in complaint and expected_schema() in complaint


async def test_connecting_to_a_newer_database_aborts_instead_of_migrating(tmp_path) -> None:
    database = await Database(tmp_path / "bot.db").connect()
    await database.conn.execute(
        "INSERT INTO schema_migrations (version, applied_at) VALUES ('999_future', '2026-09-16')"
    )
    await database.conn.commit()
    await database.close()

    with pytest.raises(SchemaTooNewError):
        await Database(tmp_path / "bot.db").connect()


async def test_a_migration_whose_column_schema_sql_already_added_is_not_fatal(tmp_path) -> None:
    """The collision a big version jump causes, found by rehearsing the
    accounts-52 merge against a copy of production (2026-09-16).

    schema.sql runs first and creates missing tables in their *finished*
    shape; the migrations then run. A table that did not exist yet is
    therefore born with the columns a later migration meant to add — and
    that migration used to die on "duplicate column name", which on the
    production deploy would not have been a rehearsal.
    """
    database = await Database(tmp_path / "bot.db").connect()
    await database.conn.execute("CREATE TABLE later (id TEXT PRIMARY KEY, name_ru TEXT)")
    await database.conn.commit()
    await database.close()

    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "900_add_name_ru.sql").write_text(
        "ALTER TABLE later ADD COLUMN name_ru TEXT;", encoding="utf-8"
    )

    import bot.db.repo._database as database_module

    original = database_module.MIGRATIONS_DIR
    database_module.MIGRATIONS_DIR = migrations
    try:
        reopened = await Database(tmp_path / "bot.db").connect()  # must not raise
        await reopened.close()
    finally:
        database_module.MIGRATIONS_DIR = original


async def test_a_migration_that_fails_for_any_other_reason_still_stops_startup(tmp_path) -> None:
    """The swallow above is exactly one error wide."""
    database = await Database(tmp_path / "bot.db").connect()
    await database.close()

    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "901_broken.sql").write_text("SELECT * FROM nothing_at_all;", encoding="utf-8")

    import bot.db.repo._database as database_module

    original = database_module.MIGRATIONS_DIR
    database_module.MIGRATIONS_DIR = migrations
    try:
        with pytest.raises(Exception, match="nothing_at_all"):
            await Database(tmp_path / "bot.db").connect()
    finally:
        database_module.MIGRATIONS_DIR = original
