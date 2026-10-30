"""Pairs of versions put in front of the operator in «Labelling» by hand
(owner, 2026-10-24: the disputed joins a change of the matcher made), each
with what the model says of it now. They come first in the queue until
answered.

Read-only on the database (the requests are kept in the advice store beside
it, `label_requests.json`), safe beside the viewer.

Usage:
    … -m scripts.request_labels --schema dev 605:9745 1099:5884
"""

from __future__ import annotations

import argparse
import json

from bot.config import get_settings
from bot.db import tools
from bot.db.repo import Repo
from bot.services.advice import AdviceStore
from bot.services.game_link import load_candidates
from bot.services.game_match import compare


async def verdicts(schema: str | None, pairs: list[tuple[int, int]]) -> list[dict]:
    database = await tools.open_database(schema=schema)
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
    tools.add_arguments(parser)
    parser.add_argument("pairs", nargs="+", help="version:version")
    args = parser.parse_args()
    pairs = [tuple(int(x) for x in p.split(":")) for p in args.pairs]
    rows = tools.run(verdicts(args.schema, pairs))  # type: ignore[arg-type]
    store = AdviceStore.for_db(get_settings().db_path)
    store.save_label_requests(store.label_requests() + rows)
    print(f"{len(rows)} pairs asked for")


if __name__ == "__main__":
    main()
