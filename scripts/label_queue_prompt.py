"""The labelling queue, asked of the advisers (owner, 2026-10-24): a prompt
to paste into Claude and Gemini, **with a web search required**, for the
pairs the viewer's «Labelling» tab asks the operator — the rare relations
(a VR version, a compilation, a remake, a remaster), not yet answered.

Writes `<out>-01.txt`, `-02.txt`, … — `--batch` questions each, as many
as one reply with a search per question carries — (the advisers' rules,
`advice.RULES`, plus the search, then the questions, blind: the model's
guess is not shown) and
`<out>.questions.json` (each question's id with its two versions, to read
the replies back against).

Read-only on the database, safe beside the viewer.

Usage:
    .venv/Scripts/python.exe -X utf8 -m scripts.label_queue_prompt --db data/games.db
        [--limit 100] [--batch 25] [--out data/advice/labelling/2026-10-24]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from pathlib import Path

from bot.services.advice import RULES, versions_pair_id
from bot.util import utcnow_iso
from scripts.advise_pairs import load_facts, open_read_only, read_only_uri
from scripts.catalog_viewer import label_queue

SEARCH = """For EVERY question, search the web before answering — store pages (Steam,
Microsoft Store, PlayStation Store), Wikipedia, MobyGames, HowLongToBeat — and do not
answer from memory alone: the sides come from store data that may be wrong. Add to each
answer object a "source" field: the one URL that settled it."""


def _blind(text: str) -> str:
    """The game's text without saying where FIRST is filed now."""
    return text.replace(" (FIRST is filed in this game now)", "")


async def build(db: Path, limit: int) -> list[dict]:
    conn = sqlite3.connect(read_only_uri(db), uri=True)
    conn.row_factory = sqlite3.Row
    try:
        queue, _answered, _order = label_queue(conn)
        pairs = [(int(r["subject"]), int(r["other"]), rare) for r, rare in queue]
    finally:
        conn.close()
    database = await open_read_only(db)
    try:
        facts = await load_facts(database.conn)
    finally:
        await database.close()
    questions: list[dict] = []
    seen: set[str] = set()
    for subject, other, rare in pairs:
        game = facts.game_of.get(other)
        if subject not in facts.versions or game is None:
            continue
        qid = versions_pair_id(subject, game)
        if qid in seen:
            continue
        seen.add(qid)
        questions.append(
            {
                "pair_id": qid,
                "type": "versions",
                "version_id": subject,
                "other_id": other,
                "game_id": game,
                "asked_for": rare,
                "first": facts.version_text(subject),
                "second": _blind(facts.game_text(game, without=subject)),
            }
        )
        if len(questions) >= limit:
            break
    return questions


def prompt(questions: list[dict]) -> str:
    lines = [RULES, "", SEARCH, "", "Questions:"]
    for q in questions:
        lines.append(
            f"\nid: {q['pair_id']}  (type: {q['type']})\nFIRST: {q['first']}\nSECOND: {q['second']}"
        )
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--batch", type=int, default=25)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    questions = asyncio.run(build(Path(args.db), args.limit))
    out = Path(args.out or f"data/advice/labelling/{utcnow_iso()[:10]}")
    out.parent.mkdir(parents=True, exist_ok=True)
    files = []
    for n, start in enumerate(range(0, len(questions), args.batch), 1):
        path = out.parent / f"{out.name}-{n:02}.txt"
        path.write_text(prompt(questions[start : start + args.batch]), encoding="utf-8")
        files.append(path)
    out.with_suffix(".questions.json").write_text(json.dumps(questions, indent=1), "utf-8")
    asked: dict[str, int] = {}
    for q in questions:
        asked[q["asked_for"]] = asked.get(q["asked_for"], 0) + 1
    print(f"{len(questions)} questions {asked} → {len(files)} files, {out}-NN.txt")


if __name__ == "__main__":
    main()
