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
- **C** — a count of commits, read from git at startup rather than typed
  into a file (owner's call, 2026-09-16: a short number that grows by one per
  commit reads better than a hash nobody can order at a glance). It measures
  a different distance on each side:

  * on a working branch, **since it left `main`** — how far this line of work
    has come, which is what somebody looking at the test bot wants to know;
  * on `main`, **since the newest release tag, counted along first parents**
    — which release production is on. One per release rather than one per
    commit that rode in with it: a merge is one thing going out. It used to
    be `0` there always, because `main` does not depart from itself, so four
    different production builds went out on 2026-09-18 all calling
    themselves `v1.2.0.050` — and this string is printed in `/help` and at
    startup precisely so an incident can tell builds apart.

  A version you have to remember to bump is wrong precisely when it matters,
  and one edited per commit is a merge conflict per commit.
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
#: number. Production has been `3` since release 1.3.
TRUNK_LINE = 3

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

#: What a release tag looks like. Production counts from the newest one
#: reachable from HEAD; until the next tag exists the number simply keeps
#: growing, which is the honest answer to "how much has gone out since".
TAG_PATTERN = "v[0-9]*"


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
    """How far this build is from whatever it is measured against.

    On `main` that is the newest release tag, so the number says which
    release production is on; anywhere else it is the merge base with
    `main`, so it says how far a line of work has come. The merge base
    rather than the tip of `main`, or somebody else merging something would
    renumber this branch's builds.

    `?` when git cannot answer at all (a release tarball, a container with
    no .git). Never fatal: a version is a label, and refusing to start
    because one is incomplete would be the opposite of what this file is
    for. A `main` carrying no tag yet answers `0` rather than counting from
    the root commit, which would be a four-digit number meaning nothing.
    """
    if line() == TRUNK_LINE:
        tag = _release_tag()
        if tag is None:
            return "0"
        # --first-parent: one per *release*, not one per commit that rode in
        # with it. A merge of a five-commit branch is one thing going out,
        # and counting it as six would make the number grow by the size of
        # whatever happened to be merged rather than by how many times
        # production changed. Measured on 2026-09-18: 3 against 19.
        return _git("rev-list", "--count", "--first-parent", f"{tag}..HEAD") or "0"
    fork_point = _fork_point()
    if fork_point is None:
        return UNKNOWN_REVISION
    # Every commit, not first-parent: on a working branch the question is how
    # much work has accumulated, and each commit is a piece of it.
    return _git("rev-list", "--count", f"{fork_point}..HEAD") or "0"


def _fork_point() -> str | None:
    base = next((ref for ref in BASE_REFS if _git("rev-parse", "--verify", "--quiet", ref)), None)
    return _git("merge-base", base, "HEAD") if base else None


def _release_tag() -> str | None:
    """The newest release tag reachable from HEAD.

    Found by walking history (`git describe`) rather than by sorting names:
    a tag marks where a release actually happened, and the commit graph
    cannot disagree with itself the way a version-sort can.
    """
    return _git("describe", "--tags", "--abbrev=0", "--match", TAG_PATTERN)


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
