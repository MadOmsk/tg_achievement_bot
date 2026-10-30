"""Names for the achievement lists known only by their id, taken from
another copy of the bot's database that learned them (owner, 2026-10-27:
"name the stand-ins"). A list whose game was never polled again kept its id
as a name; a later copy of production often has the real one. The trigger
of migration 117/130 names the list's stand-in versions after it.

Only a name that is not a placeholder is taken, and only where this
catalog has none. Run with the viewer stopped, after a backup. `--from`
is another database's address, or a JSON array of `[platform, title_id,
name]` — what production's lists are called, read on the server (`--dump`,
run there, prints it; names only, nothing about anybody).

Usage:
    … -m scripts.restore_list_names --from postgresql://…/other [--dry-run]
    … -m scripts.restore_list_names --dump > list_names.json
    … -m scripts.restore_list_names --from list_names.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bot.db import tools

PLACEHOLDER = "(name IS NULL OR name IN ('', '?') OR name = title_id)"


def _rows(source: tools.Connection) -> list[tuple]:
    """Every real list name a copy holds."""
    return source.execute(
        f"SELECT platform, title_id, name FROM achievement_list_connectors WHERE NOT {PLACEHOLDER}"
        " AND platform IS NOT NULL ORDER BY platform, title_id"
    ).fetchall()


def names_from(source: tools.Connection) -> dict[tuple[str, str], str]:
    return {(str(p), str(t)): str(n) for p, t, n in _rows(source)}


def names_in(path: str, schema: str | None = None) -> dict[tuple[str, str], str]:
    """The names another copy knows: a database's address, or a `--dump`'s JSON."""
    if Path(path).suffix == ".json":
        return {
            (str(p), str(t)): str(n)
            for p, t, n in json.loads(Path(path).read_text("utf-8"))
            if p and n and str(n) not in ("?", str(t))
        }
    source = tools.connect(path, schema=schema, readonly=True)
    try:
        return names_from(source)
    finally:
        source.close()


def restore(db: tools.Connection, names: dict[tuple[str, str], str]) -> list[tuple]:
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
    tools.add_arguments(parser)
    parser.add_argument("--from", dest="source")
    parser.add_argument("--dump", action="store_true", help="print the list names as JSON")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dump:
        source = tools.connect(schema=args.schema, readonly=True)
        print(json.dumps([list(r) for r in _rows(source)], ensure_ascii=False))
        source.close()
        return
    if not args.source:
        parser.error("--from, or --dump")
    names = names_in(args.source, args.schema)
    db = tools.connect(schema=args.schema)
    db.begin()
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
