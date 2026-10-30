"""The labelling queue, asked of the advisers (owner, 2026-10-24): a prompt
to paste into Claude and Gemini, **with a web search required**, for the
pairs the viewer's «Labelling» tab asks the operator — the rare relations
(a VR version, a compilation, a remake, a remaster), not yet answered.

Writes one prompt, `<out>.txt` (owner, 2026-10-24: one file in, one file
out — the adviser splits the work itself when its context is short), or
`--batch` questions a file, `<out>-01.txt`, … (the advisers' rules,
`advice.RULES`, plus the search, then the questions, blind: the model's
guess is not shown) and
`<out>.questions.json` (each question's id with its two versions, to read
the replies back against).

Read-only on the database, safe beside the viewer.

Usage:
    .venv/Scripts/python.exe -X utf8 -m scripts.label_queue_prompt [--schema dev]
        [--limit 400] [--batch 0] [--out data/advice/labelling/2026-10-24]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bot.db import tools
from bot.services.advice import RULES, versions_pair_id
from bot.util import utcnow_iso
from scripts.advise_pairs import load_facts, open_read_only
from scripts.catalog_viewer import label_queue

SEARCH = """For EVERY question, search the web before answering — store pages (Steam,
Microsoft Store, PlayStation Store), Wikipedia, MobyGames, HowLongToBeat — and do not
answer from memory alone: the sides come from store data that may be wrong. Add to each
answer object a "source" field: the one URL that settled it."""

ONE_FILE = """Answer every question below, {n} in all, and give the whole answer as ONE file,
labelling-answers.json: the JSON array described above, one object per question, in the
questions' order. If the questions do not all fit in what you can do in one reply, work
through them in parts as large as your context allows, and say at the end of each part
which question id you stopped at; I will reply "continue" and you go on from the next.
The final file must still hold every answer, the earlier parts' included."""


def _blind(text: str) -> str:
    """The game's text without saying where FIRST is filed now."""
    return text.replace(" (FIRST is filed in this game now)", "")


async def build(schema: str | None, limit: int) -> list[dict]:
    conn = tools.connect(schema=schema, readonly=True)
    try:
        queue, _answered, _order = label_queue(conn)
        pairs = [(int(r["subject"]), int(r["other"]), rare) for r, rare in queue]
    finally:
        conn.close()
    database = await open_read_only(schema)
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
    lines = [RULES, "", SEARCH, "", ONE_FILE.format(n=len(questions)), "", "Questions:"]
    for q in questions:
        lines.append(
            f"\nid: {q['pair_id']}  (type: {q['type']})\nFIRST: {q['first']}\nSECOND: {q['second']}"
        )
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    tools.add_arguments(parser)
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument("--batch", type=int, default=0, help="questions a file; 0: one file")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    questions = tools.run(build(args.schema, args.limit))
    out = Path(args.out or f"data/advice/labelling/{utcnow_iso()[:10]}")
    out.parent.mkdir(parents=True, exist_ok=True)
    files = []
    size = args.batch or len(questions) or 1
    for n, start in enumerate(range(0, len(questions), size), 1):
        name = f"{out.name}-{n:02}.txt" if args.batch else f"{out.name}.txt"
        path = out.parent / name
        path.write_text(prompt(questions[start : start + size]), encoding="utf-8")
        files.append(path)
    out.with_suffix(".questions.json").write_text(json.dumps(questions, indent=1), "utf-8")
    asked: dict[str, int] = {}
    for q in questions:
        asked[q["asked_for"]] = asked.get(q["asked_for"], 0) + 1
    print(f"{len(questions)} questions {asked} → {', '.join(str(f) for f in files)}")


if __name__ == "__main__":
    main()
