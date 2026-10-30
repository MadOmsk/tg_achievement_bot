"""Import the advisers' answers to a run of question files (#147; owner,
2026-10-17): the decisions two or three of them gave alike become labels
(`adviser_labels`), and what all three agree on is written into the database
(`services/advice_import`). The database is copied into `backups/` first.

    .venv/Scripts/python.exe -X utf8 -m scripts.argon_import [--schema dev] \
        --run trial-1 --questions data/advice/argon/trial_questions.json \
        --answers argon=…/trial_gemini-argon.jsonl gpt-pro=…/trial_gpt-pro.jsonl \
                  sonnet=…/trial_sonnet-offline.jsonl [--dry-run]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from bot.db import tools
from bot.db.repo import Repo
from bot.services.advice_import import apply, consensus
from scripts.compare_answers import decisions, read_answers


def _backup(schema: str | None) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = Path("backups") / f"{schema or 'database'}-pre-advice-import-{stamp}.dump"
    return tools.backup(target, schema=schema)


def _read(questions_path: str, specs: list[str]) -> tuple[list[str], dict[str, dict]]:
    questions = [q["id"] for q in json.loads(Path(questions_path).read_text("utf-8"))]
    advisers = {}
    for spec in specs:
        name, _, path = spec.partition("=")
        advisers[name] = read_answers(Path(path))
    return questions, advisers


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    tools.add_arguments(parser)
    parser.add_argument("--run", required=True)
    parser.add_argument("--questions", required=True)
    parser.add_argument("--answers", nargs="+", required=True, help="name=path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    questions, advisers = _read(args.questions, args.answers)
    labels = []
    for q in questions:
        per = {n: decisions(q, a[q]) for n, a in advisers.items() if q in a}
        if len(per) >= 2:
            labels += consensus(q, per)
    by = Counter(c.source for c in labels)
    print(f"{len(questions)} questions, {len(labels)} labels: {dict(by)}")
    if args.dry_run:
        return 0
    print("database copied to", _backup(args.schema))
    database = await tools.open_database(schema=args.schema)
    try:
        report = await apply(Repo(database), labels, args.run)
        print(
            f"kept {report.labels}; pairs written {report.pairs}, operator's kept"
            f" {report.kept_operators}; HLTB refused {report.hltb_refused},"
            f" DLC HLTB refused {report.dlc_hltb_refused}; series {report.series},"
            f" editions {report.editions}, PSN groups {report.psn_groups},"
            f" DLC ↔ HLTB {report.dlc_links}, HLTB restored {report.hltb_restored}"
        )
        for reason, n in report.skipped.most_common():
            print(f"  {n:5d}  {reason}")
    finally:
        await database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(tools.run(main()))
