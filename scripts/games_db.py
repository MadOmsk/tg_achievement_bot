"""The games database shared by prod and the test server (#229; owner,
2026-10-28): the catalog moved out of a bot's database into a file of its
own, another bot joined to it, or the two parted again.

- `split`: the catalog's tables (`CATALOG_TABLES`) move from `--db` into a
  new `--games` file, which the database then names (`app_settings`). The
  first server's catalog becomes the shared one.
- `join`: a database still holding its own catalog takes the shared file
  instead. What only it knows about achievement lists — lists, their
  achievements, Steam's and HLTB's caches, store answers, when each is due —
  is added where the shared file has no row; its games, versions, labels and
  series give way to the shared ones, except a list the shared file has no
  version for keeps its stand-in (and its HLTB link), linked into a game
  after. Then its own catalog tables are dropped.
- `leave`: the shared catalog copied back into the database, which stops
  naming the file — how the two part for a rework of the games database
  that cannot be shared (a migration that rebuilds or drops a catalog table:
  CLAUDE.md). Run on each server; afterwards one `split`s again and the other
  `join`s.

Every command needs the bot stopped and copies the database into
`backups/` first; `--dry-run` does it all on a copy in a temporary folder.

    .venv/bin/python -X utf8 -m scripts.games_db split --db data/test.db \\
        --games /srv/unlocked-games/games.db
    .venv/bin/python -X utf8 -m scripts.games_db join --db data/bot.db \\
        --games /srv/unlocked-games/games.db
    .venv/bin/python -X utf8 -m scripts.games_db leave --db data/bot.db
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from bot.db import files
from bot.db.repo._database import INDEXES_AFTER_MIGRATIONS, SCHEMA_PATH, _statements
from bot.db.repo._games_db import CATALOG_TABLES, GAMES, GAMES_DB_KEY, placed
from bot.util import utcnow_iso

# What a joining database adds where the shared file has no row: facts about
# a list or a store's answer, the same whoever learned them.
ADDED = (
    "achievement_list_connectors",
    "title_groups",
    "title_achievements",
    "steam_schema_cache",
    "steam_rarity_cache",
    "steam_apps",
    "title_guide_reads",
    "game_patches",
    "guide_channels",
    "guide_videos",
    "guide_marks",
    "hltb_entries",
    "hltb_platform_times",
    "hltb_platform_groups",
    "hltb_entry_platforms",
    "hltb_review_scores",
    "hltb_related",
    "source_payloads",
)
# Not `fetch_state`: a joining database's "asked, next due then" would stand
# for answers (DLC, versions) that give way to the shared file's, and the
# shared file would not ask again until then (2026-10-28: prod's add-on
# searches came over without their add-ons). Without it, they are asked when due.
# An HLTB entry's rows of its own: taken only for an entry the shared file
# did not have, never mixed into one it reads from a newer page.
HLTB_CHILDREN = frozenset(
    {
        "hltb_platform_times",
        "hltb_platform_groups",
        "hltb_entry_platforms",
        "hltb_review_scores",
        "hltb_related",
    }
)
# What points at a version, carried with a kept stand-in.
VERSION_CHILDREN = ("version_hltb", "dlcs")


def _tables(conn: sqlite3.Connection, schema: str) -> set[str]:
    rows = conn.execute(f"SELECT name FROM {schema}.sqlite_master WHERE type = 'table'").fetchall()
    return {r[0] for r in rows} & CATALOG_TABLES


def _columns(conn: sqlite3.Connection, schema: str, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA {schema}.table_info({table})")]


def _count(conn: sqlite3.Connection, schema: str, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {schema}.{table}").fetchone()[0])


def _make_catalog(conn: sqlite3.Connection, schema: str) -> None:
    """The catalog's tables, indexes and trigger, made in `schema` (empty)."""
    script = SCHEMA_PATH.read_text(encoding="utf-8")
    statements = [placed(s, True) for s in _statements(script)]
    statements += [placed(s, True) + ";" for s in INDEXES_AFTER_MIGRATIONS]
    kept = [s for s in statements if f"{GAMES}." in s]
    if schema != GAMES:
        kept = [s.replace(f"{GAMES}.", f"{schema}.", 1) for s in kept]
    conn.executescript("".join(kept))


def _copy(
    conn: sqlite3.Connection, table: str, src: str, dst: str, *, ignore: bool, where: str = ""
) -> int:
    """Rows of `table` from `src` into `dst`, by the columns both have."""
    theirs = set(_columns(conn, dst, table))
    cols = [c for c in _columns(conn, src, table) if c in theirs]
    missing = set(_columns(conn, src, table)) - theirs
    if missing:
        raise SystemExit(f"{dst}.{table} lacks {sorted(missing)}: bring both to one migration")
    names = ", ".join(cols)
    verb = "INSERT OR IGNORE" if ignore else "INSERT"
    before = _count(conn, dst, table)
    conn.execute(f"{verb} INTO {dst}.{table} ({names}) SELECT {names} FROM {src}.{table} {where}")
    return _count(conn, dst, table) - before


def _drop(conn: sqlite3.Connection, schema: str) -> None:
    for table in sorted(_tables(conn, schema)):
        conn.execute(f"DROP TABLE {schema}.{table}")


def _named(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT value FROM main.app_settings WHERE key = ?", (GAMES_DB_KEY,)
    ).fetchone()
    return row[0] if row else None


def _name(conn: sqlite3.Connection, games: Path | None) -> None:
    if games is None:
        conn.execute("DELETE FROM main.app_settings WHERE key = ?", (GAMES_DB_KEY,))
    else:
        conn.execute(
            "INSERT OR REPLACE INTO main.app_settings (key, value, updated_at) VALUES (?, ?, ?)",
            (GAMES_DB_KEY, str(games), utcnow_iso()),
        )


def _open(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db, isolation_level=None)
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def split(db: Path, games: Path) -> None:
    if games.exists() and games.stat().st_size:
        raise SystemExit(f"{games} exists: `join` takes a shared file, `split` makes one")
    conn = _open(db)
    if _named(conn):
        raise SystemExit(f"{db} already keeps its games in {_named(conn)}")
    own = _tables(conn, "main")
    games.parent.mkdir(parents=True, exist_ok=True)
    conn.execute(f"ATTACH DATABASE ? AS {GAMES}", (str(games),))
    conn.execute(f"PRAGMA {GAMES}.journal_mode = WAL")
    _make_catalog(conn, GAMES)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")
    try:
        for table in sorted(own):
            moved = _copy(conn, table, "main", GAMES, ignore=False)
            print(f"  {table:28} {moved:8}")
        _drop(conn, "main")
        _name(conn, games.resolve())
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    _check(conn)
    conn.execute(f"DETACH DATABASE {GAMES}")
    conn.execute("VACUUM")
    conn.close()
    print(f"{db} keeps its games in {games.resolve()}")


def join(db: Path, games: Path) -> list[int]:
    """The shared file taken; returns the kept stand-ins' new ids."""
    if not games.exists():
        raise SystemExit(f"{games} not found: `split` makes it")
    conn = _open(db)
    if _named(conn):
        raise SystemExit(f"{db} already keeps its games in {_named(conn)}")
    conn.execute(f"ATTACH DATABASE ? AS {GAMES}", (str(games),))
    own = _tables(conn, "main")
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")
    kept: list[int] = []
    try:
        conn.execute("CREATE TEMP TABLE shared_hltb AS SELECT hltb_id FROM games.hltb_entries")
        for table in ADDED:
            if table in own:
                where = (
                    "WHERE hltb_id NOT IN (SELECT hltb_id FROM temp.shared_hltb)"
                    if table in HLTB_CHILDREN
                    else ""
                )
                added = _copy(conn, table, "main", GAMES, ignore=True, where=where)
                print(f"  {table:28} +{added}")
        if "versions" in own:
            kept = _keep_stand_ins(conn)
        _drop(conn, "main")
        _name(conn, games.resolve())
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    _check(conn)
    conn.execute(f"DETACH DATABASE {GAMES}")
    conn.execute("VACUUM")
    conn.close()
    print(f"kept stand-ins of lists the shared file has no version for: {len(kept)}")
    print(f"{db} keeps its games in {games.resolve()}")
    return kept


def _keep_stand_ins(conn: sqlite3.Connection) -> list[int]:
    """This database's versions of lists no shared version stands for go
    into the shared file, unlinked, with what points at them."""
    cols = [c for c in _columns(conn, "main", "versions") if c != "version_id"]
    rows = conn.execute(
        f"SELECT version_id, {', '.join(cols)} FROM main.versions v"
        " WHERE platform IS NOT NULL AND NOT EXISTS (SELECT 1 FROM games.versions s"
        "  WHERE s.platform = v.platform AND s.title_id = v.title_id)"
    ).fetchall()
    new_id: dict[int, int] = {}
    for old, *values in rows:
        row = dict(zip(cols, values, strict=True))
        row.update(game_id=None, of_version_id=None)
        same = conn.execute(
            "SELECT version_id, platform FROM games.versions"
            " WHERE store = ? AND product_id = ? AND console = ?",
            (row["store"], row["product_id"], row["console"]),
        ).fetchone()
        if same is not None:
            # The shared file knows this product, just not as this list's.
            if same[1] is None:
                conn.execute(
                    "UPDATE games.versions SET platform = ?, title_id = ? WHERE version_id = ?",
                    (row["platform"], row["title_id"], same[0]),
                )
            new_id[old] = int(same[0])
            continue
        cursor = conn.execute(
            f"INSERT INTO games.versions ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
            list(row.values()),
        )
        new_id[old] = int(cursor.lastrowid)
    for child in VERSION_CHILDREN:
        cols = [c for c in _columns(conn, "main", child) if c != "dlc_id"]
        at = cols.index("version_id")
        marks = ",".join("?" * len(new_id)) or "NULL"
        for values in conn.execute(
            f"SELECT {', '.join(cols)} FROM main.{child} WHERE version_id IN ({marks})",
            list(new_id),
        ).fetchall():
            values = list(values)
            values[at] = new_id[values[at]]
            conn.execute(
                f"INSERT OR IGNORE INTO games.{child} ({', '.join(cols)})"
                f" VALUES ({', '.join('?' * len(cols))})",
                values,
            )
    return sorted(set(new_id.values()))


def leave(db: Path) -> None:
    conn = _open(db)
    named = _named(conn)
    if not named:
        raise SystemExit(f"{db} keeps its own catalog already")
    conn.execute("ATTACH DATABASE ? AS shared", (named,))
    conn.execute("PRAGMA foreign_keys = OFF")
    _make_catalog(conn, "main")
    conn.execute("BEGIN")
    try:
        for table in sorted(_tables(conn, "shared")):
            copied = _copy(conn, table, "shared", "main", ignore=False)
            print(f"  {table:28} {copied:8}")
        _name(conn, None)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("DETACH DATABASE shared")
    _check(conn)
    conn.close()
    print(f"{db} keeps its own catalog again (a copy of {named})")


def _sqlite_copy(source: Path, target: Path) -> None:
    src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _check(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    broken = conn.execute("PRAGMA foreign_key_check").fetchall()
    if broken:
        raise SystemExit(f"foreign keys broken: {broken[:5]} ({len(broken)})")
    for schema in ("main", *([GAMES] if _attached(conn, GAMES) else [])):
        ok = conn.execute(f"PRAGMA {schema}.integrity_check").fetchone()[0]
        print(f"integrity of {schema}: {ok}")


def _attached(conn: sqlite3.Connection, name: str) -> bool:
    return any(r[1] == name for r in conn.execute("PRAGMA database_list"))


async def _link(db: Path, version_ids: list[int]) -> None:
    """Put the kept stand-ins into games, with the weights now active."""
    from bot.db.repo import Database, Repo
    from bot.services.game_link import GameLinker

    database = await Database(db).connect()
    try:
        report = await GameLinker(Repo(database)).link_versions(version_ids)
        print(f"linked {len(version_ids)} kept versions: {len(report.games)} games touched")
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=("split", "join", "leave"))
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--games", type=Path, help="the shared file (split, join)")
    parser.add_argument("--dry-run", action="store_true", help="on a copy, in a temporary folder")
    args = parser.parse_args()
    if args.command != "leave" and args.games is None:
        parser.error(f"{args.command} needs --games")

    db, games = args.db, args.games
    workdir = None
    if args.dry_run:
        workdir = Path(tempfile.mkdtemp(prefix="games-db-"))
        files.backup(db, workdir / db.name)
        db = workdir / db.name
        named = files.games_of(sqlite3.connect(db))
        if games is not None and games.exists() and named is None:
            _sqlite_copy(games, workdir / games.name)  # the shared file `join` reads
        if games is not None:
            games = workdir / games.name
        print(f"dry run in {workdir}")
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        Path("backups").mkdir(exist_ok=True)
        copy = Path("backups") / f"{db.stem}-pre-games-{args.command}-{stamp}.db"
        print("database copied to", files.backup(db, copy))

    try:
        if args.command == "split":
            split(db, games)
        elif args.command == "join":
            kept = join(db, games)
            if kept:
                asyncio.run(_link(db, kept))
        else:
            leave(db)
    finally:
        if workdir is not None:
            shutil.rmtree(workdir, ignore_errors=True)
            print("dry run: nothing written")


if __name__ == "__main__":
    main()
