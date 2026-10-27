"""Pairs of versions put in front of the operator in «Labelling» by hand
(owner, 2026-10-24: the disputed joins a change of the matcher made), each
with what the model says of it now. They come first in the queue until
answered.

Read-only on the database (the requests are kept in the advice store beside
it, `label_requests.json`), safe beside the viewer.

Usage:
    … -m scripts.request_labels --db data/games.db 605:9745 1099:5884
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from bot.db.repo import Repo
from bot.services.advice import AdviceStore
from bot.services.game_link import load_candidates
from bot.services.game_match import compare
from scripts.advise_pairs import open_read_only


async def verdicts(db: Path, pairs: list[tuple[int, int]]) -> list[dict]:
    database = await open_read_only(db)
    try:
        cands = await load_candidates(Repo(database), sorted({v for p in pairs for v in p}))
    finally:
        await database.close()
    rows = []
    for a, b in pairs:
        if a not in cands or b not in cands:
            print(f"{a}:{b}: no such version")
            continue
        v = compare(cands[a], cands[b])
        rows.append(
            {
                "subject": v.subject,
                "other": v.other,
                "relation": v.relation,
                "p": round(v.p, 3),
                "probs": json.dumps({k: round(x, 3) for k, x in v.probs.items()}),
                "features": json.dumps(v.features),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("pairs", nargs="+", help="version:version")
    args = parser.parse_args()
    pairs = [tuple(int(x) for x in p.split(":")) for p in args.pairs]
    rows = asyncio.run(verdicts(Path(args.db), pairs))  # type: ignore[arg-type]
    store = AdviceStore.for_db(Path(args.db))
    store.save_label_requests(store.label_requests() + rows)
    print(f"{len(rows)} pairs asked for")


if __name__ == "__main__":
    main()
