"""The advisers' answers to the labelling queue, brought in (owner,
2026-10-24; the questions: `scripts/label_queue_prompt.py`).

Two advisers answered one prompt each (a Claude and a Gemini, with a web
search). Their answers go into the advice store (`data/advice`, beside the
database) as `claude` and `gemini`, where `advise_pairs apply` writes what
both say alike as their label (`claude+gemini`, weighed
`match_fit.BOTH_WEIGHT`) and leaves what they dispute to the operator.

**A blind sample is held back** (`--audit`, 20 pairs by default): pairs the
two agree on that are not put in the store at all, so the operator answers
them in «Labelling» not knowing the advisers' answer; `<prefix>.audit.json`
keeps those answers, and `--score` compares them with the operator's — how
often two advisers agreeing are right, which says what their weight should
be.

Usage:
    … -m scripts.label_queue_answers [--schema dev]
        --prefix data/advice/labelling/2026-10-24
        --claude <prefix>.claude-sonnet-medium.json --gemini <prefix>.gemini-argon.json
    … -m scripts.label_queue_answers [--schema dev] --prefix … --score
then, with the viewer stopped: … -m scripts.advise_pairs [--schema dev] apply
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from bot.config import get_settings
from bot.db import tools
from bot.services.advice import AdviceStore, decide, label_of, parse_answers, validate
from bot.util import utcnow_iso
from scripts.advise_pairs import import_answers

AUDIT_SEED = 1024


def stage(prefix: Path, claude: Path, gemini: Path, audit: int) -> None:
    questions = {
        q["pair_id"]: q
        for q in json.loads(prefix.with_suffix(".questions.json").read_text("utf-8"))
    }
    asked = {"claude": claude, "gemini": gemini}
    replies = {
        name: {
            str(item.get("pair_id")): a
            for item in parse_answers(path.read_text("utf-8"))
            if not isinstance(a := validate(item, questions), str)
        }
        for name, path in asked.items()
    }
    agreed = sorted(
        pid
        for pid in questions
        if decide(None, replies["claude"].get(pid), replies["gemini"].get(pid)).state == "agreed"
    )
    store = AdviceStore.for_db(get_settings().db_path)
    # Only pairs never asked before: an earlier round's answers are known.
    fresh = [pid for pid in agreed if pid not in store.questions()]
    held = set(random.Random(AUDIT_SEED).sample(fresh, min(audit, len(fresh))))
    store.save_questions(
        {pid: q for pid, q in questions.items() if pid not in held},
        sorted(set(questions) - held),
        utcnow_iso(),
    )
    for name, path in asked.items():
        stored, refused = import_answers(store, name, [path])
        print(f"{name}: {stored} answers stored, {len(refused)} refused")
        for line in refused:
            print(f"  {line}")
    # The held-back pairs' answers are taken out again: the store must not
    # know them (the viewer would show "agreed").
    for name in asked:
        answers = store.answers(name)
        store.save_answers(name, {k: v for k, v in answers.items() if k not in held})
    prefix.with_suffix(".audit.json").write_text(
        json.dumps(
            {
                pid: {
                    "version_id": questions[pid]["version_id"],
                    "other_id": questions[pid]["other_id"],
                    "relation": replies["claude"][pid].relation,
                    "direction": replies["claude"][pid].direction,
                }
                for pid in sorted(held)
            },
            indent=1,
        ),
        "utf-8",
    )
    print(
        f"{len(questions)} questions: {len(agreed)} agreed, {len(held)} of them held back"
        f" blind, {len(questions) - len(agreed)} disputed or unsure (the operator's)"
    )


def score(schema: str | None, prefix: Path) -> None:
    held = json.loads(prefix.with_suffix(".audit.json").read_text("utf-8"))
    conn = tools.connect(schema=schema, readonly=True)
    labels = {
        frozenset((a, b)): (a, b, relation)
        for a, b, relation in conn.execute(
            "SELECT version_id, other_id, relation FROM match_decisions WHERE decided_by = 'viewer'"
        )
    }
    conn.close()
    from bot.services.advice import Answer
    from bot.services.match_fit import LABEL_CLASS

    right = answered = 0
    for pid, a in held.items():
        mine = labels.get(frozenset((a["version_id"], a["other_id"])))
        if mine is None:
            continue
        answered += 1
        theirs = label_of(Answer(a["relation"], a["direction"], "high", ""))
        same_class = theirs is not None and LABEL_CLASS.get(theirs[0]) == LABEL_CLASS.get(mine[2])
        right += same_class
        if not same_class:
            print(f"  {pid}: you {mine[2]}, advisers {a['relation']} {a['direction'] or ''}")
    print(f"answered {answered} of {len(held)} held back; the advisers right on {right}")


def main() -> None:
    parser = argparse.ArgumentParser()
    tools.add_arguments(parser)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--claude")
    parser.add_argument("--gemini")
    parser.add_argument("--audit", type=int, default=20, help="agreed pairs held back blind")
    parser.add_argument("--score", action="store_true")
    args = parser.parse_args()
    if args.score:
        score(args.schema, Path(args.prefix))
    else:
        stage(Path(args.prefix), Path(args.claude), Path(args.gemini), args.audit)


if __name__ == "__main__":
    main()
