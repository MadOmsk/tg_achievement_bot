"""What version of this bot is running, and against which database (#56).

`A.B.C.D`, and every part answers a question somebody actually asked during
an outage:

- **A** — the architecture. Bumped by hand, on a rewrite. It is `1`.
- **B** — which line of work this build comes from, derived from the branch
  at startup: `TRUNK_LINE` on `main`, one above it anywhere else. This is the
  part that says "you are looking at the test bot", and it is computed rather
  than stored because a hand-edited constant stopped saying it — `main`
  inherited the number whenever a branch merged, so after the Mini App went
  in both bots reported `1.2`.
- **C** — how many commits this branch has made since it left `main`,
  counted from git at startup rather than typed into a file (owner's call,
  2026-09-16: a short number that grows by one per commit reads better than
  a hash nobody can order at a glance). It is `0` on `main` itself, so a
  build from the trunk says so. A version you have to remember to bump is
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

#: The line of work `main` is on, and the only part of this file a person
#: edits — on a rewrite, or when the owner decides a release deserves its own
#: number. Production has been `2` since the Mini App merged.
TRUNK_LINE = 2

#: The branch that *is* production (2026-09-18): merging into it is the
#: release, and everything else is by definition a line of work above it.
TRUNK = "main"

MIGRATIONS = Path(__file__).resolve().parent / "db" / "migrations"
REPO = Path(__file__).resolve().parents[1]
UNKNOWN_REVISION = "?"

#: Where this branch is measured from. `origin/main` first: a deployment's
#: own local `main` is usually stale (nothing checks it out there), and a
#: stale baseline would quietly give the same commit two different numbers
#: on two machines.
BASE_REFS = ("origin/main", "main")


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = result.stdout.strip()
    return output if result.returncode == 0 and output else None


@cache
def revision() -> str:
    """Commits made on this branch since it left `main`.

    Counted from the *merge base*, not from the tip of `main`: the question
    is "how far has this branch come", and measuring against a trunk that
    has moved on since would answer a different one — and a different number
    every time somebody else merges something.

    `?` when git cannot answer at all (a release tarball, a container with
    no .git). Never fatal: a version is a label, and refusing to start
    because one is incomplete would be the opposite of what this file is
    for.
    """
    base = next((ref for ref in BASE_REFS if _git("rev-parse", "--verify", "--quiet", ref)), None)
    if base is None:
        return UNKNOWN_REVISION
    fork_point = _git("merge-base", base, "HEAD")
    if fork_point is None:
        return UNKNOWN_REVISION
    return _git("rev-list", "--count", f"{fork_point}..HEAD") or "0"


@cache
def line() -> int:
    """Which line of work this build comes from: **B**.

    `TRUNK_LINE` on `main`, one above it anywhere else — so production reads
    `1.2.…` and the test bot reads `1.3.…`, and "which bot am I looking at"
    is answerable from the version alone. That was the whole point of B and
    it had quietly stopped working: B used to be a constant edited by hand,
    which `main` inherited whenever a branch merged, so after the Mini App
    went in both bots reported `1.2` and were indistinguishable.

    Derived rather than stored, and derived *here* rather than in
    `scripts/xbox-deploy.sh` where the owner first asked for it: a deploy
    script that rewrote this file on the server would leave the checkout
    dirty, and its own `git merge --ff-only` would refuse the next deploy.
    Nothing to remember, nothing to commit, and it is right on a developer's
    machine too.

    A checkout with no git (a tarball, a container) falls back to the trunk's
    number — `revision()` already renders `?` in that case, which is the part
    that says "do not trust this label".
    """
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if branch is None:
        return TRUNK_LINE
    return TRUNK_LINE if branch == TRUNK else TRUNK_LINE + 1


@cache
def expected_schema() -> str:
    """The newest migration this code ships, as its own three-digit number.
    `000` for a checkout with no migrations at all, which is not a state the
    bot can be in but is one a test can construct."""
    numbers = sorted(path.name[:3] for path in MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql"))
    return numbers[-1] if numbers else "000"


def version() -> str:
    return f"{MAJOR}.{line()}.{revision()}.{expected_schema()}"


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
