"""The operator's own answers, asked again of the advisers (owner,
2026-10-24): a prompt to paste into Claude and Gemini, **with a web search
required**, so a slip of the operator's (a «different game» meant as «another
of the series») shows where they disagree.

Reads the operator's answers in `label_log` since a moment — the latest
answer per pair still standing (one taken back is left out), and every
series answer — and writes:

- `<out>.txt`: the advisers' rules (`advice.RULES`, plus the series
  question and the search), then the questions, **without the operator's
  answers**;
- `<out>.key.json`: the operator's answer per question id, to compare the
  replies against.

Read-only on the database, safe beside the viewer.

Usage:
    .venv/Scripts/python.exe -X utf8 -m scripts.recheck_labels --db data/games.db
        [--since 2026-10-24T00:00] [--out data/advice/recheck/2026-10-24]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from bot.services.advice import RULES, versions_pair_id
from bot.util import utcnow_iso
from scripts.advise_pairs import _rows, load_facts, open_read_only

SEARCH = """For EVERY question, search the web before answering — store pages (Steam,
Microsoft Store, PlayStation Store), Wikipedia, MobyGames, HowLongToBeat — and do not
answer from memory alone: the sides come from store data that may be wrong. Add to each
answer object a "source" field: the one URL that settled it."""

SERIES_RULES = """One more type of question:
- series: one game (FIRST) against a series of ours (SECOND: its name and the games in
  it). member (FIRST belongs in this series: its franchise, a local series inside it, or
  for a LEGO game the series LEGO) | not_member | unsure. direction is null."""


def _filed_note(text: str) -> str:
    """The game's text without saying where FIRST is filed now: the
    advisers answer blind."""
    return text.replace(" (FIRST is filed in this game now)", "")


async def build(db: Path, since: str) -> tuple[list[dict], dict[str, dict]]:
    database = await open_read_only(db)
    try:
        conn = database.conn
        facts = await load_facts(conn)
        log = await _rows(
            conn,
            "SELECT log_id, subject, event, version_id, other_id, relation, game_id,"
            " series_id, member FROM label_log WHERE decided_by = 'viewer'"
            " AND decided_at >= ? ORDER BY log_id",
            (since,),
        )
        series = {
            int(r["series_id"]): r for r in await _rows(conn, "SELECT series_id, name FROM series")
        }
        series_games = await _rows(
            conn, "SELECT series_id, game_id FROM game_series WHERE member = 1"
        )
    finally:
        await database.close()

    standing: dict[frozenset, dict] = {}
    for row in log:
        if row["subject"] != "pair" or row["event"] not in ("label", "undo"):
            continue
        pair = frozenset((row["version_id"], row["other_id"]))
        if row["event"] == "undo":
            standing.pop(pair, None)
        else:
            standing[pair] = row
    members: dict[int, list[int]] = {}
    for r in series_games:
        members.setdefault(int(r["series_id"]), []).append(int(r["game_id"]))

    questions: list[dict] = []
    key: dict[str, dict] = {}
    for row in standing.values():
        subject, other = int(row["version_id"]), int(row["other_id"])
        game = facts.game_of.get(other)
        if subject not in facts.versions or game is None:
            continue
        qid = versions_pair_id(subject, game)
        questions.append(
            {
                "pair_id": qid,
                "type": "versions",
                "first": facts.version_text(subject),
                "second": _filed_note(facts.game_text(game, without=subject)),
            }
        )
        key[qid] = {"relation": row["relation"], "version_id": subject, "other_id": other}
    for row in log:
        if row["subject"] != "series" or row["event"] != "label":
            continue
        game, sid = int(row["game_id"]), int(row["series_id"])
        game = facts.current_game(game)
        if sid not in series or game not in facts.games:
            continue
        qid = f"s:{game}:{sid}"
        others = [
            str((facts.games.get(g) or {}).get("name") or g)
            for g in members.get(sid, [])
            if g != game
        ]
        questions.append(
            {
                "pair_id": qid,
                "type": "series",
                "first": _filed_note(facts.game_text(game)),
                "second": f'the series "{series[sid]["name"]}"; its games: '
                + ("; ".join(others[:15]) or "none yet"),
            }
        )
        key[qid] = {"member": bool(row["member"]), "game_id": game, "series_id": sid}
    return questions, key


def prompt(questions: list[dict]) -> str:
    lines = [RULES, "", SERIES_RULES, "", SEARCH, "", "Questions:"]
    for q in questions:
        lines.append(
            f"\nid: {q['pair_id']}  (type: {q['type']})\nFIRST: {q['first']}\nSECOND: {q['second']}"
        )
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--since", default=utcnow_iso()[:10] + "T00:00")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    questions, key = asyncio.run(build(Path(args.db), args.since))
    out = Path(args.out or f"data/advice/recheck/{args.since[:10]}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".txt").write_text(prompt(questions), encoding="utf-8")
    out.with_suffix(".key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    kinds = {t: sum(1 for q in questions if q["type"] == t) for t in ("versions", "series")}
    print(f"{len(questions)} questions {kinds} → {out.with_suffix('.txt')}")


if __name__ == "__main__":
    main()
