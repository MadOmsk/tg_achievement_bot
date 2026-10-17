"""Compare advisers' answers to the same question file (#147; owner,
2026-10-16: which model errs least). Each answer is cut into decisions — one
per release, link, edition, member … — and the decisions are compared across
the advisers: how many each answered in form, how often each pair agrees, and
where they differ. The operator then marks a sample of the differences
(`--labels`), and the score per adviser and kind is how often it gave the
operator's answer.

    .venv/Scripts/python.exe -X utf8 -m scripts.compare_answers \\
        --questions data/advice/argon/trial_questions.json \\
        --answers argon=…/trial_argon.jsonl sonnet=…/trial_sonnet.jsonl \\
        --out data/advice/argon/compare
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

KINDS = {
    "G": "game card",
    "M": "missing releases",
    "R": "relations",
    "D": "alike games",
    "S": "series",
    "P": "PSN groups",
    "E": "editions",
    "H": "DLC ↔ HLTB",
    "X": "refused HLTB",
}


def read_answers(path: Path) -> dict[str, dict]:
    """An adviser's file, leniently: JSON Lines, or a JSON array, inside a code
    fence or not; a broken line is skipped (and counted as unanswered)."""
    text = path.read_text(encoding="utf-8-sig")
    text = re.sub(r"^```[a-z]*\s*$", "", text, flags=re.M)
    found: dict[str, dict] = {}
    stripped = text.strip()
    if stripped.startswith("["):
        try:
            for item in json.loads(stripped):
                if isinstance(item, dict) and item.get("id"):
                    found[str(item["id"])] = item
            return found
        except ValueError:
            pass
    for line in text.splitlines():
        line = line.strip().rstrip(",")
        if not line.startswith("{"):
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict) and item.get("id"):
            found[str(item["id"])] = item
    return found


def _norm(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value.strip().lower())
    return value


def decisions(qid: str, answer: dict) -> dict[str, Any]:
    """One answer as `{decision key: value}` — the units compared."""
    kind = qid.split(":", 1)[0]
    out: dict[str, Any] = {}
    if kind == "G":
        for r in answer.get("releases") or []:
            v = r.get("v")
            out[f"v{v}.belongs"] = _norm(r.get("belongs"))
            out[f"v{v}.kind"] = _norm(r.get("kind"))
        for h in answer.get("hltb") or []:
            out[f"v{h.get('v')}.hltb{h.get('hltb')}"] = _norm(h.get("verdict"))
        for d in answer.get("dlc_hltb") or []:
            out[f"dlc{d.get('dlc')}.hltb{d.get('hltb')}"] = _norm(d.get("verdict"))
        out["missing_hltb"] = bool(answer.get("missing_hltb"))
        out["series"] = tuple(sorted(_norm(s) for s in answer.get("series") or []))
        out["facts_wrong"] = bool(answer.get("facts"))
    elif kind == "M":
        found = answer.get("missing") or []
        out["missing"] = tuple(
            sorted(f"{_norm(m.get('store'))}/{_norm(m.get('console'))}" for m in found)
        )
    elif kind in ("R", "D"):
        out["relation"] = (_norm(answer.get("relation")), _norm(answer.get("direction")))
    elif kind == "S":
        out["name_ok"] = answer.get("name_ok")
        for m in answer.get("members") or []:
            out[f"g{m.get('g')}"] = _norm(m.get("belongs"))
    elif kind == "P":
        out["addon"] = _norm(answer.get("addon"))
    elif kind == "E":
        for e in answer.get("editions") or []:
            out[f"e{e.get('e')}.kind"] = _norm(e.get("kind"))
            out[f"e{e.get('e')}.holds"] = _norm(e.get("holds_game"))
    elif kind == "H":
        out["links"] = tuple(
            sorted(f"{d.get('dlc')}->{d.get('hltb')}" for d in answer.get("links") or [])
        )
    elif kind == "X":
        out["verdict"] = _norm(answer.get("verdict"))
    return out


# A release's kind: "game", "remake" and "remaster" all say it is the game
# itself (owner, 2026-10-17: which of them is the game's role against an older
# one, asked elsewhere) — not counted as a mistake against each other.
_SAME_WORK = {"game", "remake", "remaster"}


_NONE_WORDS = {"", "()", "none", "нет", "ни в какой", "ни в какую", "—"}


def _series_set(text: str) -> frozenset[str]:
    """A series answer as a set of names, whether an adviser's tuple or the
    operator's free text ("Wizarding World, LEGO, LEGO Harry Potter")."""
    text = text.strip()
    if text.lower() in _NONE_WORDS:
        return frozenset()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    return frozenset(part.strip(" '\"").lower() for part in text.split(",") if part.strip(" '\""))


def _alike(key: str, said: str, label: str) -> bool:
    if key.endswith(".kind") and said in _SAME_WORK and label in _SAME_WORK:
        return True
    if key == "series":
        return _series_set(said) == _series_set(label)
    return said == label


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--questions", required=True)
    parser.add_argument("--answers", nargs="+", required=True, help="name=path")
    parser.add_argument("--out", required=True)
    parser.add_argument("--labels", help="the operator's answers (JSON), to score against")
    args = parser.parse_args()
    questions = [q["id"] for q in json.loads(Path(args.questions).read_text("utf-8"))]
    advisers = {}
    for spec in args.answers:
        name, _, path = spec.partition("=")
        advisers[name] = read_answers(Path(path))
    labels = json.loads(Path(args.labels).read_text("utf-8")) if args.labels else {}

    lines = [
        "# Advisers compared",
        "",
        f"{len(questions)} questions; advisers: {', '.join(advisers)}",
        "",
    ]
    lines += [
        "## Answered in form",
        "",
        "| adviser | " + " | ".join(KINDS) + " | all |",
        "|---" * (len(KINDS) + 2) + "|",
    ]
    for name, answers in advisers.items():
        row, total = [], 0
        for kind in KINDS:
            ids = [q for q in questions if q.startswith(kind + ":")]
            got = sum(1 for q in ids if q in answers)
            total += got
            row.append(f"{got}/{len(ids)}")
        lines.append(f"| {name} | " + " | ".join(row) + f" | {total}/{len(questions)} |")

    per: dict[str, dict[str, dict[str, Any]]] = {
        name: {q: decisions(q, a) for q, a in answers.items()} for name, answers in advisers.items()
    }
    agree: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0, 0])
    unanimous: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    differences: list[dict] = []
    scores: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for q in questions:
        kind = q.split(":", 1)[0]
        keys = set().union(*(per[n].get(q, {}).keys() for n in advisers))
        for key in sorted(keys):
            said = {n: per[n].get(q, {}).get(key, "—") for n in advisers}
            for a, b in combinations(advisers, 2):
                agree[(kind, a, b)][1] += 1
                agree[(kind, a, b)][0] += said[a] == said[b]
            unanimous[kind][1] += 1
            if len(set(map(str, said.values()))) == 1:
                unanimous[kind][0] += 1
            else:
                differences.append(
                    {"question": q, "decision": key, "said": {n: str(v) for n, v in said.items()}}
                )
            label = labels.get(f"{q}|{key}")
            if label is not None:
                for n in advisers:
                    scores[(kind, n)][1] += 1
                    scores[(kind, n)][0] += _alike(key, str(said[n]), str(label))

    lines += ["", "## Decisions all advisers agree on", "", "| kind | agree |", "|---|---|"]
    for kind, label in KINDS.items():
        a, n = unanimous[kind]
        if n:
            lines.append(f"| {kind} {label} | {a}/{n} ({a * 100 // n}%) |")
    lines += ["", "## Pairwise agreement", ""]
    pairs = list(combinations(advisers, 2))
    lines += [
        "| kind | " + " | ".join(f"{a} ~ {b}" for a, b in pairs) + " |",
        "|---" * (len(pairs) + 1) + "|",
    ]
    for kind, label in KINDS.items():
        cells = []
        for a, b in pairs:
            same, n = agree[(kind, a, b)]
            cells.append(f"{same * 100 // n}%" if n else "—")
        lines.append(f"| {kind} {label} | " + " | ".join(cells) + " |")
    if scores:
        lines += [
            "",
            "## Against the operator's labels",
            "",
            "| kind | " + " | ".join(advisers) + " |",
            "|---" * (len(advisers) + 1) + "|",
        ]
        for kind, label in KINDS.items():
            cells = []
            for n in advisers:
                right, total = scores[(kind, n)]
                cells.append(f"{right}/{total}" if total else "—")
            lines.append(f"| {kind} {label} | " + " | ".join(cells) + " |")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text("\n".join(lines) + "\n", "utf-8")
    (out / "differences.json").write_text(
        json.dumps(differences, ensure_ascii=False, indent=1), "utf-8"
    )
    print("\n".join(lines))
    print(f"\n{len(differences)} differing decisions → {out / 'differences.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
