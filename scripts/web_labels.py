"""Labels from a web-checked answer file (owner, 2026-10-24: "search the
web yourself, set the labels yourself" — and they are not below the
operator's: they replace theirs, the old one kept in `label_log`).

The file is a JSON array of `{"a", "b", "relation", "direction",
"confidence", "why", "source"}`: `relation` one of same / enhanced /
remaster_of / remake_of / demo_of / extra_of / contains / series /
not_related, `direction` "a" or "b" for the side that is the enhanced /
remaster / … one. Only high and medium confidence answers are written, as
`decided_by = claude-web`; each pair's versions are linked again after.
Run with the viewer stopped (one linker at a time).

Usage:
    … -m scripts.web_labels --db data/games.db answers.json [more.json …] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from bot.db.repo import Database, Repo
from bot.services.game_link import GameLinker
from bot.services.game_match import MODEL

SOURCE = "claude-web"
RELATIONS = {
    "same": "same",
    "enhanced": "enhanced_of",
    "remaster_of": "remaster_of",
    "remake_of": "remake_of",
    "demo_of": "demo_of",
    "tool_of": "tool_of",
    "extra_of": "extra_of",
    "contains": "contains",
    "series": "series",
    "not_related": "other",
}
DIRECTED = {"enhanced_of", "remaster_of", "remake_of", "demo_of", "tool_of", "extra_of", "contains"}


def label_of(answer: dict) -> tuple[int, int, str] | None:
    """(subject, other, relation) of one answer, or None when it is not to
    be written."""
    if answer.get("confidence") not in ("high", "medium"):
        return None
    relation = RELATIONS.get(str(answer.get("relation")))
    if relation is None:
        return None
    a, b = int(answer["a"]), int(answer["b"])
    if relation in DIRECTED:
        if answer.get("direction") == "b":
            a, b = b, a
        elif answer.get("direction") != "a":
            return None
    return a, b, relation


async def write(db: Path, labels: list[tuple[int, int, str]]) -> None:
    database = await Database(db).connect()
    try:
        repo = Repo(database)
        for a, b, relation in labels:
            features, model = await repo.pair_features(a, b)
            await repo.save_decision(
                a,
                b,
                relation,
                features=features,
                model=model or MODEL,
                decided_by=SOURCE,
                overrule=True,
            )
        await GameLinker(repo).link_versions(sorted({v for a, b, _ in labels for v in (a, b)}))
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("files", nargs="+")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    labels = []
    for path in args.files:
        for answer in json.loads(Path(path).read_text("utf-8")):
            label = label_of(answer)
            print(
                ("  " if label else "- ") + f"{answer['a']}:{answer['b']} {answer['relation']}"
                f" {answer.get('direction') or ''} {answer.get('confidence')}"
            )
            if label:
                labels.append(label)
    print(f"{len(labels)} labels")
    if not args.dry_run:
        asyncio.run(write(Path(args.db), labels))


if __name__ == "__main__":
    main()
