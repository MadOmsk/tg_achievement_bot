"""Carry the games catalog from one database to another (#147; owner,
2026-10-25: production collects the very games the development catalog
holds, so its links, labels and weights are carried over and the weights
go on being taught as it runs).

The catalog — versions, games and how they relate, editions and DLC, the
HLTB side, series, the labels and their log, the model's fitted weights,
when each source is next due, the octopus's queue — points outside itself
only by an achievement list's (platform, title_id), the same in every
database. So it travels whole:

- `export` copies those tables from a database into a file of their own
  (the raw store answers, `source_payloads`, stay behind: the heaviest, and
  a server asks again when they are due);
- `import` replaces the target's catalog with the file's, in one
  transaction. People, accounts, achievements, chats and publications are
  not touched. A list the target has and the file does not keeps its own
  stand-in version (and its HLTB link); those are linked into games after.
  Tables keyed by their subject alone (`fetch_state`, the HLTB entries)
  keep the target's rows the file has no answer for.

Both databases must be at the same migration. Run `import` with the bot
stopped; a copy of the target is made first, beside it.

Usage:
    .venv/Scripts/python.exe -X utf8 -m scripts.catalog_transfer export \\
        --db data/games.db --out catalog.db [--tables match_weights] [--except octopus_queue]
    .venv/Scripts/python.exe -X utf8 -m scripts.catalog_transfer import \\
        --db data/bot.db --file catalog.db [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import time
from pathlib import Path

# Parents before children; the order only matters for reading the counts.
TABLES = (
    "games",
    "versions",
    "game_relations",
    "editions",
    "edition_items",
    "dlcs",
    "hltb_entries",
    "hltb_entry_platforms",
    "hltb_platform_groups",
    "hltb_platform_times",
    "hltb_related",
    "hltb_review_scores",
    "version_hltb",
    "dlc_hltb",
    "series",
    "game_series",
    "match_decisions",
    "adviser_labels",
    "label_log",
    "match_pairs",
    "match_weights",
    "fetch_state",
    "octopus_queue",
)
# Keyed by their own subject, not by a version: the target's rows the file
# has no answer for are kept.
MERGED = frozenset(
    {
        "fetch_state",
        "hltb_entries",
        "hltb_entry_platforms",
        "hltb_platform_groups",
        "hltb_platform_times",
        "hltb_related",
        "hltb_review_scores",
    }
)
# What points at a version, re-pointed when a kept stand-in gets a new id.
VERSION_CHILDREN = ("version_hltb", "dlcs")


def _migration(conn: sqlite3.Connection, schema: str = "main") -> str:
    return str(conn.execute(f"SELECT MAX(version) FROM {schema}.schema_migrations").fetchone()[0])


def _columns(conn: sqlite3.Connection, table: str, schema: str = "main") -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA {schema}.table_info({table})")]


def _count(conn: sqlite3.Connection, table: str, schema: str = "main") -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {schema}.{table}").fetchone()[0])


def export(db: Path, out: Path, tables: tuple[str, ...]) -> None:
    if out.exists():
        raise SystemExit(f"{out} exists")
    conn = sqlite3.connect(out)
    conn.execute("ATTACH DATABASE ? AS src", (str(db),))
    conn.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO schema_migrations VALUES (?)", (_migration(conn, "src"),))
    for table in tables:
        conn.execute(f"CREATE TABLE {table} AS SELECT * FROM src.{table}")
        print(f"  {table:22} {_count(conn, table):7}")
    conn.commit()
    conn.execute("DETACH DATABASE src")
    conn.execute("VACUUM")
    conn.close()
    print(f"{out}: {out.stat().st_size / 1e6:.1f} MB at {_migration(sqlite3.connect(out))}")


def _keyed(conn: sqlite3.Connection, table: str) -> bool:
    """Whether a row has a key of its own (so INSERT OR REPLACE replaces)."""
    if any(r[5] for r in conn.execute(f"PRAGMA table_info({table})")):
        return True
    return any(r[2] for r in conn.execute(f"PRAGMA index_list({table})"))


def import_(db: Path, file: Path, *, dry_run: bool) -> list[int]:
    """The catalog replaced; returns the kept stand-ins' new ids."""
    conn = sqlite3.connect(db, isolation_level=None)
    conn.execute("ATTACH DATABASE ? AS src", (str(file),))
    here, there = _migration(conn), _migration(conn, "src")
    if here != there:
        raise SystemExit(f"migrations differ: {db} is at {here}, {file} at {there}")
    tables = [
        t
        for t in TABLES
        if conn.execute(
            "SELECT 1 FROM src.sqlite_master WHERE type = 'table' AND name = ?", (t,)
        ).fetchone()
    ]
    whole = "versions" in tables
    before = {t: _count(conn, t) for t in tables}
    if not dry_run:
        backup = db.with_name(f"{db.stem}-pre-catalog-{time.strftime('%Y%m%d-%H%M%S')}.db")
        target = sqlite3.connect(backup)
        conn.backup(target)
        target.close()
        print(f"backup: {backup}")
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")
    kept: list[int] = []
    try:
        saved: dict[str, list[tuple]] = {}
        if whole:
            # The target's lists the file has no version for keep theirs.
            cols = [c for c in _columns(conn, "versions") if c != "version_id"]
            rows = conn.execute(
                f"SELECT version_id, {', '.join(cols)} FROM versions v WHERE platform IS NOT NULL"
                " AND NOT EXISTS (SELECT 1 FROM src.versions s"
                "  WHERE s.platform = v.platform AND s.title_id = v.title_id)"
            ).fetchall()
            saved["versions"] = rows
            ids = [r[0] for r in rows]
            for child in VERSION_CHILDREN:
                marks = ",".join("?" * len(ids)) or "NULL"
                saved[child] = conn.execute(
                    f"SELECT * FROM {child} WHERE version_id IN ({marks})", ids
                ).fetchall()
        for table in tables:
            cols = [c for c in _columns(conn, table) if c in set(_columns(conn, table, "src"))]
            names = ", ".join(cols)
            if table in MERGED and _keyed(conn, table):
                conn.execute(
                    f"INSERT OR REPLACE INTO {table} ({names}) SELECT {names} FROM src.{table}"
                )
            else:
                conn.execute(f"DELETE FROM {table}")
                conn.execute(f"INSERT INTO {table} ({names}) SELECT {names} FROM src.{table}")
        if whole and saved["versions"]:
            cols = [c for c in _columns(conn, "versions") if c != "version_id"]
            new_id: dict[int, int] = {}
            for old, *values in saved["versions"]:
                row = dict(zip(cols, values, strict=True))
                row.update(game_id=None, of_version_id=None)
                same = conn.execute(
                    "SELECT version_id, platform FROM versions"
                    " WHERE store = ? AND product_id = ? AND console = ?",
                    (row["store"], row["product_id"], row["console"]),
                ).fetchone()
                if same is not None:
                    # The file knows this product, just not as this list's.
                    if same[1] is None:
                        conn.execute(
                            "UPDATE versions SET platform = ?, title_id = ? WHERE version_id = ?",
                            (row["platform"], row["title_id"], same[0]),
                        )
                    new_id[old] = int(same[0])
                    continue
                cursor = conn.execute(
                    f"INSERT INTO versions ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                    list(row.values()),
                )
                new_id[old] = int(cursor.lastrowid)
            for child in VERSION_CHILDREN:
                cols = _columns(conn, child)
                at = cols.index("version_id")
                for row in saved[child]:
                    values = list(row)
                    values[at] = new_id[values[at]]
                    conn.execute(
                        f"INSERT OR IGNORE INTO {child} ({', '.join(cols)})"
                        f" VALUES ({', '.join('?' * len(cols))})",
                        values,
                    )
            kept = sorted(new_id.values())
        broken = conn.execute("PRAGMA foreign_key_check").fetchall()
        if broken:
            raise SystemExit(f"foreign keys broken: {broken[:5]} ({len(broken)})")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    for table in tables:
        print(f"  {table:22} {before[table]:7} -> {_count(conn, table):7}")
    print(f"kept stand-ins of lists the file does not have: {len(kept)}")
    conn.execute("ROLLBACK" if dry_run else "COMMIT")
    conn.execute("PRAGMA foreign_keys = ON")
    ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"integrity: {ok}{' (dry run: nothing written)' if dry_run else ''}")
    conn.close()
    return [] if dry_run else kept


async def link(db: Path, version_ids: list[int]) -> None:
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
    sub = parser.add_subparsers(dest="command", required=True)
    out = sub.add_parser("export")
    out.add_argument("--db", required=True)
    out.add_argument("--out", required=True)
    out.add_argument("--tables", nargs="*", default=list(TABLES))
    out.add_argument("--except", dest="skip", nargs="*", default=[], help="tables left out")
    into = sub.add_parser("import")
    into.add_argument("--db", required=True)
    into.add_argument("--file", required=True)
    into.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.command == "export":
        unknown = (set(args.tables) | set(args.skip)) - set(TABLES)
        if unknown:
            raise SystemExit(f"not catalog tables: {sorted(unknown)}")
        chosen = tuple(t for t in TABLES if t in args.tables and t not in args.skip)
        export(Path(args.db), Path(args.out), chosen)
        return
    kept = import_(Path(args.db), Path(args.file), dry_run=args.dry_run)
    if kept:
        asyncio.run(link(Path(args.db), kept))


if __name__ == "__main__":
    main()
