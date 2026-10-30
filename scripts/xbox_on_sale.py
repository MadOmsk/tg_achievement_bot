"""Mend whether Xbox products are on sale (2026-10-26).

Xbox gives each price period its own availability, with its own end; a
stored answer re-read later was judged against the day of the re-read, so
every period was over and 404 games read as off sale. The parser now judges
an answer as of when it was given (`xbox_catalog.sold(product, now)`); this
mends what was written before, without asking the store:

- `recompute` reads the kept Xbox answers (`source_payloads`) and sets
  `on_sale` of the versions, add-ons and editions they describe as of when
  each was given — a dry run unless `--apply`;
- `export` writes every Xbox product's `on_sale` as a JSON file, and
  `apply` sets them on a server whose catalog has not the raw answers.

Run `--apply` and `apply` with the bot stopped.

Usage:
    … -m scripts.xbox_on_sale recompute --schema dev [--apply]
    … -m scripts.xbox_on_sale export --schema dev --out sale.json
    … -m scripts.xbox_on_sale apply --schema test --file sale.json
"""

from __future__ import annotations

import argparse
import json
import zlib
from collections import Counter
from pathlib import Path

from bot.db import tools
from bot.services.stores import xbox_catalog

XBOX_VERSION = "version_id IN (SELECT version_id FROM versions WHERE store = 'xbox')"
# What says whether an Xbox product is on sale: (table, its product id, which rows).
TABLES = (
    ("versions", "product_id", "store = 'xbox'"),
    ("dlcs", "store_id", XBOX_VERSION),
    ("editions", "store_id", "store = 'xbox'"),
)


def _products(conn: tools.Connection):
    """Every kept Xbox product with when its answer was given."""
    for _subject, at, payload in conn.execute(
        "SELECT subject, fetched_at, payload FROM source_payloads WHERE source = 'xbox_catalog'"
    ):
        data = json.loads(zlib.decompress(payload).decode("utf-8"))
        if isinstance(data, dict):
            data = (data.get("editions") or []) + (data.get("addons") or [])
        for product in data or []:
            if isinstance(product, dict) and product.get("ProductId"):
                yield str(product["ProductId"]), at, product


def recompute(schema: str | None, *, apply: bool) -> None:
    conn = tools.connect(schema=schema)
    sale: dict[str, int] = {}
    for product_id, at, product in _products(conn):
        # A product seen in several answers is on sale if any said so then.
        sale[product_id] = max(sale.get(product_id, 0), int(xbox_catalog.sold(product, at)))
    moved: Counter[str] = Counter()
    if apply:
        conn.begin()
    for table, key, where in TABLES:
        for row_key, on_sale in conn.execute(f"SELECT {key}, on_sale FROM {table} WHERE {where}"):
            now = sale.get(str(row_key))
            if now is None or now == on_sale:
                continue
            moved[f"{table} {on_sale} -> {now}"] += 1
            if apply:
                conn.execute(
                    f"UPDATE {table} SET on_sale = ? WHERE {key} = ? AND {where}", (now, row_key)
                )
    if apply:
        conn.commit()
    conn.close()
    for line, n in sorted(moved.items()):
        print(f"  {line}: {n}")
    print("applied" if apply else "dry run: nothing written (--apply to write)")


def export(schema: str | None, out: Path) -> None:
    conn = tools.connect(schema=schema, readonly=True)
    rows = {
        "versions": conn.execute(
            "SELECT DISTINCT product_id, on_sale FROM versions WHERE store = 'xbox'"
            " AND on_sale IS NOT NULL"
        ).fetchall(),
        "dlcs": conn.execute(
            "SELECT DISTINCT d.store_id, d.on_sale FROM dlcs d JOIN versions v USING (version_id)"
            " WHERE v.store = 'xbox' AND d.on_sale IS NOT NULL"
        ).fetchall(),
        "editions": conn.execute(
            "SELECT store_id, on_sale FROM editions WHERE store = 'xbox' AND on_sale IS NOT NULL"
        ).fetchall(),
    }
    conn.close()
    plain = {table: [list(row) for row in found] for table, found in rows.items()}
    out.write_text(json.dumps(plain), encoding="utf-8")
    print(f"{out}: " + ", ".join(f"{k} {len(v)}" for k, v in rows.items()))


def apply_file(schema: str | None, file: Path) -> None:
    rows = json.loads(file.read_text(encoding="utf-8"))
    conn = tools.connect(schema=schema)
    changed: Counter[str] = Counter()
    conn.begin()
    for table, key, where in TABLES:
        for row_key, on_sale in rows.get(table, []):
            cursor = conn.execute(
                f"UPDATE {table} SET on_sale = ? WHERE {key} = ? AND {where}"
                " AND on_sale IS DISTINCT FROM ?",
                (on_sale, row_key, on_sale),
            )
            changed[table] += cursor.rowcount
    conn.commit()
    conn.close()
    print("changed: " + ", ".join(f"{k} {n}" for k, n in changed.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    re_ = sub.add_parser("recompute")
    tools.add_arguments(re_)
    re_.add_argument("--apply", action="store_true")
    ex = sub.add_parser("export")
    tools.add_arguments(ex)
    ex.add_argument("--out", required=True)
    ap = sub.add_parser("apply")
    tools.add_arguments(ap)
    ap.add_argument("--file", required=True)
    args = parser.parse_args()
    if args.command == "recompute":
        recompute(args.schema, apply=args.apply)
    elif args.command == "export":
        export(args.schema, Path(args.out))
    else:
        apply_file(args.schema, Path(args.file))


if __name__ == "__main__":
    main()
