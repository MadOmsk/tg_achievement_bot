"""The version string, and the check that refuses a database from the future
(#56)."""

from __future__ import annotations

import pytest

from bot import version as version_module
from bot.db.repo._database import Database, SchemaTooNewError
from bot.version import (
    MAJOR,
    TRUNK,
    TRUNK_LINE,
    expected_schema,
    is_test,
    is_trunk,
    line,
    schema_gap,
    version,
)


def test_the_version_names_the_branch_and_the_schema_it_expects() -> None:
    parts = version().split(".")

    assert parts[0] == str(MAJOR)
    assert parts[1] == str(line())
    # Commits since this branch left main — a number, or "?" where git
    # cannot answer at all (a tarball, a container with no .git).
    assert parts[2].isdigit() or parts[2] == "?"
    assert parts[3] == expected_schema()
    assert parts[3].isdigit() and len(parts[3]) == 3


def _on_branch(monkeypatch, name: str | None) -> None:
    """Pretend git reports this branch, leaving every other git call alone."""
    real = version_module._git

    def fake(*args: str):
        if args[:2] == ("rev-parse", "--abbrev-ref"):
            return name
        return real(*args)

    line.cache_clear()
    monkeypatch.setattr(version_module, "_git", fake)


def test_working_branches_read_one_minor_above_production(monkeypatch) -> None:
    """Production is on TRUNK_LINE; the test bot already reads the line its
    work will ship in (owner, 2026-09-24)."""
    _on_branch(monkeypatch, TRUNK)
    assert line() == TRUNK_LINE
    assert is_trunk() is True
    assert is_test() is False

    _on_branch(monkeypatch, "test")
    assert line() == TRUNK_LINE + 1
    assert is_trunk() is False
    assert is_test() is True
    line.cache_clear()


def test_every_working_branch_is_a_test_one(monkeypatch) -> None:
    for name in ("test", "feature/whatever", "HEAD", "dev"):
        _on_branch(monkeypatch, name)
        assert line() == TRUNK_LINE + 1, name
        assert is_trunk() is False, name
        assert is_test() is True, name
    line.cache_clear()


def test_without_git_it_falls_back_to_the_trunk(monkeypatch) -> None:
    """A tarball or a container with no .git. `revision()` already renders
    `?` there, which is the part that says the label is not to be trusted."""
    _on_branch(monkeypatch, None)
    assert line() == TRUNK_LINE
    assert is_trunk() is False
    assert is_test() is True
    line.cache_clear()


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


def _git_answers(monkeypatch, answers: dict[tuple[str, ...], str | None]) -> list[tuple[str, ...]]:
    """Stand in for git, and record what was asked."""
    asked: list[tuple[str, ...]] = []

    def fake(*args: str):
        asked.append(args)
        for prefix, answer in answers.items():
            if args[: len(prefix)] == prefix:
                return answer
        return None

    version_module.line.cache_clear()
    version_module.revision.cache_clear()
    monkeypatch.setattr(version_module, "_git", fake)
    return asked


def test_production_counts_from_the_newest_release_tag(monkeypatch) -> None:
    """The gap this closes: `main` does not depart from itself, so C was 0
    there forever — four different production builds went out on 2026-09-18
    all calling themselves v1.2.0.050."""
    asked = _git_answers(
        monkeypatch,
        {
            ("rev-parse", "--abbrev-ref"): TRUNK,
            ("describe",): "v1.2.0",
            ("rev-list", "--count"): "7",
        },
    )

    assert version_module.revision() == "7"
    assert any(args[0] == "describe" for args in asked)
    # --first-parent: one per release, not one per commit that rode in with
    # it. Measured on the day this was written: 3 releases against 19
    # commits, and the number is meant to say which release is running.
    assert ("rev-list", "--count", "--first-parent", "v1.2.0..HEAD") in asked
    version_module.revision.cache_clear()
    version_module.line.cache_clear()


def test_production_without_a_tag_yet_says_zero(monkeypatch) -> None:
    """Rather than counting from the root commit, which would be a
    four-digit number meaning nothing at all."""
    _git_answers(monkeypatch, {("rev-parse", "--abbrev-ref"): TRUNK})

    assert version_module.revision() == "0"
    version_module.revision.cache_clear()
    version_module.line.cache_clear()


def test_a_working_branch_still_counts_from_where_it_left_main(monkeypatch) -> None:
    """Unchanged, and deliberately not the tag: on the test bot the useful
    number is how far this line of work has come."""
    asked = _git_answers(
        monkeypatch,
        {
            ("rev-parse", "--abbrev-ref"): "test",
            ("rev-parse", "--verify"): "origin/main",
            ("merge-base",): "abc123",
            ("rev-list", "--count"): "3",
        },
    )

    assert version_module.revision() == "3"
    # Every commit here, not first parents: on a working branch the question
    # is how much work has accumulated.
    assert ("rev-list", "--count", "abc123..HEAD") in asked
    assert not any(args[0] == "describe" for args in asked), "a branch must not read the tag"
    version_module.revision.cache_clear()
    version_module.line.cache_clear()
