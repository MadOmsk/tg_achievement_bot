"""What version of this bot is running, and against which database (#56).

`A.B.C.D`, and every part answers a question somebody actually asked during
an outage:

- **A** — the architecture. Bumped by hand, on a rewrite. It is `1`.
- **B** — which line of work this build comes from. `0` on `main`; a working
  branch takes the next number, and `main` inherits it when that branch
  merges. This is the part that says "you are looking at the test bot".
- **C** — the exact commit, resolved from git at startup rather than typed
  into a file. A version you have to remember to bump is a version that is
  wrong precisely when it matters, and one edited per commit is a merge
  conflict per commit.
- **D** — the database schema this code expects: the highest migration file
  it ships. Not what the database *has* — see `schema_gap()` for that, and
  for why the difference is worth refusing to start over.

The 2026-09-14 outage is the whole reason this file exists: a script run
from the `accounts-52` worktree opened production's `bot.db`, `connect()`
applied that branch's migrations to it, and the production bot — running
older code on `main` — crashed on a schema it had never heard of. Nothing
in that chain announced a version, so nothing could have noticed.
"""

from __future__ import annotations

import subprocess
from functools import cache
from pathlib import Path

MAJOR = 1
# 0 on main; accounts-52 is the first working branch (#56's own numbering).
BRANCH = 1

MIGRATIONS = Path(__file__).resolve().parent / "db" / "migrations"
UNKNOWN_REVISION = "nogit"


@cache
def revision() -> str:
    """The short commit hash, or `nogit` when git cannot answer — a release
    tarball, a container without the .git directory. Never fatal: a version
    is a label, and refusing to start because one is incomplete would be the
    opposite of what this file is for."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN_REVISION
    revision = result.stdout.strip()
    return revision if result.returncode == 0 and revision else UNKNOWN_REVISION


@cache
def expected_schema() -> str:
    """The newest migration this code ships, as its own three-digit number.
    `000` for a checkout with no migrations at all, which is not a state the
    bot can be in but is one a test can construct."""
    numbers = sorted(path.name[:3] for path in MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql"))
    return numbers[-1] if numbers else "000"


def version() -> str:
    return f"{MAJOR}.{BRANCH}.{revision()}.{expected_schema()}"


def schema_gap(applied: str | None) -> str | None:
    """`None` when the database is at or behind what this code expects, and
    a sentence to refuse startup with when it is *ahead*.

    Behind is ordinary: migrations run and it catches up. Ahead means
    something else — a newer branch, another checkout — already changed this
    file, and running anyway is how 2026-09-14 turned a mistake into an
    outage. The check costs one query and answers the question nobody was in
    a position to ask that day.
    """
    if applied is None:
        return None  # a brand-new database, baselined by schema.sql
    if applied[:3] <= expected_schema():
        return None
    return (
        f"database schema ({applied[:3]}) is ahead of this code ({expected_schema()}) — "
        "refusing to start; run the newer code, or point DB_PATH at the right database"
    )
