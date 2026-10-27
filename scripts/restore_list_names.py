"""Names for the achievement lists known only by their id, taken from
another copy of the bot's database that learned them (owner, 2026-10-27:
"name the stand-ins"). A list whose game was never polled again kept its id
as a name; a later copy of production often has the real one. The trigger
of migration 117/130 names the list's stand-in versions after it.

Only a name that is not a placeholder is taken, and only where this
database has none. Run with the viewer stopped, after a backup. `--from`
is another database, or a JSON array of `[platform, title_id, name]` —
what production's lists are called, read on the server (`--dump`, run
there, prints it; names only, nothing about anybody).

Usage:
    … -m scripts.restore_list_names --db data/games.db --from data/test.db [--dry-run]
    … -m scripts.restore_list_names --dump data/bot.db > list_names.json
    … -m scripts.restore_list_names --db data/games.db --from list_names.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

PLACEHOLDER = "(name IS NULL OR name IN ('', '?') OR name = title_id)"


def _rows(source: sqlite3.Connection) -> list[tuple]:
    """Every real list name a copy holds, under either table name."""
    tables = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    table = "achievement_list_connectors" if "achievement_list_connectors" in tables else "titles"
    return source.execute(
        f"SELECT platform, title_id, name FROM {table} WHERE NOT {PLACEHOLDER}"
        " AND platform IS NOT NULL ORDER BY platform, title_id"
    ).fetchall()


def names_from(source: sqlite3.Connection) -> dict[tuple[str, str], str]:
    return {(str(p), str(t)): str(n) for p, t, n in _rows(source)}


def names_in(path: str) -> dict[tuple[str, str], str]:
    """The names another copy knows: a database, or a `--dump`'s JSON."""
    if Path(path).suffix == ".json":
        return {
            (str(p), str(t)): str(n)
            for p, t, n in json.loads(Path(path).read_text("utf-8"))
            if p and n and str(n) not in ("?", str(t))
        }
    source = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return names_from(source)
    finally:
        source.close()


def restore(db: sqlite3.Connection, names: dict[tuple[str, str], str]) -> list[tuple]:
    """Set what `names` knows on the lists named by nothing; what was set."""
    done = []
    for platform, title_id in db.execute(
        f"SELECT platform, title_id FROM achievement_list_connectors WHERE {PLACEHOLDER}"
    ).fetchall():
        name = names.get((platform, title_id))
        if name:
            db.execute(
                "UPDATE achievement_list_connectors SET name = ?"
                " WHERE platform = ? AND title_id = ?",
                (name, platform, title_id),
            )
            done.append((platform, title_id, name))
    return done


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db")
    parser.add_argument("--from", dest="source")
    parser.add_argument("--dump", help="a database whose list names to print as JSON")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dump:
        source = sqlite3.connect(f"file:{args.dump}?mode=ro", uri=True)
        print(json.dumps([list(r) for r in _rows(source)], ensure_ascii=False))
        source.close()
        return
    if not (args.db and args.source):
        parser.error("--db and --from, or --dump")
    names = names_in(args.source)
    db = sqlite3.connect(args.db)
    done = restore(db, names)
    left = db.execute(
        f"SELECT COUNT(*) FROM achievement_list_connectors WHERE {PLACEHOLDER}"
    ).fetchone()[0]
    if args.dry_run:
        db.rollback()
    else:
        db.commit()
    db.close()
    for row in done[:20]:
        print(*row)
    print(f"{len(done)} lists named{' (dry run)' if args.dry_run else ''}; {left} still nameless")


if __name__ == "__main__":
    main()
