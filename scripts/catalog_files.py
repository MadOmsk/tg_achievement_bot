"""The catalog's labels and weights as files in git (owner, 2026-10-27: one
training for production, the test server and the dev server). Version ids
are each database's own, so a label is written by its versions' keys
(`store:product id:console`, `Repo.labels_by_key`) and read back into any
copy of the catalog; the fitted weights go with it, and come in as the
active set.

- `catalog/labels.jsonl` — one label a line, sorted, so a diff shows what
  was labelled;
- `catalog/weights.json` — the active fitted weights, with their gate.

`export` writes both from a database, after a labelling session or a fit;
`import` brings both into another: a label it lacks or holds otherwise is
set as the file has it (who gave it and when kept), a key no version has
there is counted and left (that copy has not collected it), and the pairs
touched are linked again. Run with the viewer stopped, after a backup.

Usage:
    … -m scripts.catalog_files export [--schema dev]
    … -m scripts.catalog_files import [--schema dev] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bot.db import tools
from bot.db.repo import Repo
from bot.services.game_link import GameLinker
from bot.services.game_match import MODEL

ROOT = Path(__file__).resolve().parent.parent / "catalog"
LABELS = ROOT / "labels.jsonl"
WEIGHTS = ROOT / "weights.json"


def label_lines(labels: list[dict]) -> list[str]:
    """One JSON line a label, sorted by its keys; a label whose version has no
    key (nothing to find it by elsewhere) is left out."""
    rows = [
        {"a": r["a"], "b": r["b"], "relation": r["relation"], "by": r["decided_by"],
         "at": r["decided_at"]}
        for r in labels
        if r["a"] and r["b"]
    ]  # fmt: skip
    rows.sort(key=lambda r: (r["a"], r["b"]))
    return [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows]


async def export(repo: Repo) -> tuple[int, bool]:
    ROOT.mkdir(exist_ok=True)
    lines = label_lines(await repo.labels_by_key())
    LABELS.write_text("\n".join(lines) + "\n", "utf-8")
    active = await repo.active_match_weights()
    if active is not None:
        weights_id, weights = active
        meta = next(
            (w for w in await repo.match_weights_list() if w["weights_id"] == weights_id), {}
        )
        WEIGHTS.write_text(
            json.dumps(
                {
                    "gate_before": meta.get("gate_before"),
                    "gate_after": meta.get("gate_after"),
                    "labels": meta.get("labels"),
                    "note": meta.get("note"),
                    "created_at": meta.get("created_at"),
                    "weights": weights,
                },
                ensure_ascii=False,
                indent=1,
                sort_keys=True,
            )
            + "\n",
            "utf-8",
        )
    return len(lines), active is not None


async def import_files(repo: Repo, *, dry_run: bool = False) -> dict[str, int]:
    counts = {"labels": 0, "set": 0, "unchanged": 0, "missing": 0, "weights": 0}
    held = {
        frozenset((r["a"], r["b"])): (r["a"], r["relation"]) for r in await repo.labels_by_key()
    }
    touched: set[int] = set()
    lines = LABELS.read_text("utf-8").splitlines() if LABELS.exists() else []
    for line in filter(None, lines):
        label = json.loads(line)
        counts["labels"] += 1
        if held.get(frozenset((label["a"], label["b"]))) == (label["a"], label["relation"]):
            counts["unchanged"] += 1
            continue
        a, b = await repo.version_by_key(label["a"]), await repo.version_by_key(label["b"])
        if a is None or b is None:
            counts["missing"] += 1
            continue
        counts["set"] += 1
        if dry_run:
            continue
        features, model = await repo.pair_features(a, b)
        await repo.save_decision(
            a, b, label["relation"], features=features, model=model or MODEL,
            decided_by=label["by"], overrule=True, decided_at=label["at"],
        )  # fmt: skip
        touched |= {a, b}
    if WEIGHTS.exists():
        shipped = json.loads(WEIGHTS.read_text("utf-8"))
        active = await repo.active_match_weights()
        if active is None or active[1] != shipped["weights"]:
            counts["weights"] = 1
            if not dry_run:
                await repo.add_match_weights(
                    shipped["weights"],
                    gate_before=shipped.get("gate_before"),
                    gate_after=shipped.get("gate_after"),
                    labels=int(shipped.get("labels") or 0),
                    note=f"from catalog/weights.json: {shipped.get('note') or ''}".strip(),
                    activate=True,
                )
    if touched and not dry_run:
        await GameLinker(repo).link_versions(sorted(touched))
    return counts


async def run(command: str, schema: str | None, dry_run: bool) -> None:
    database = await tools.open_database(schema=schema)
    try:
        repo = Repo(database)
        if command == "export":
            labels, weights = await export(repo)
            print(f"{labels} labels → {LABELS}" + (f", weights → {WEIGHTS}" if weights else ""))
        else:
            print(await import_files(repo, dry_run=dry_run))
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("export", "import"))
    tools.add_arguments(parser)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    tools.run(run(args.command, args.schema, args.dry_run))


if __name__ == "__main__":
    main()
