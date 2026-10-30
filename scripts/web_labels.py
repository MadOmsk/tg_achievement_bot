"""Labels from a web-checked answer file (owner, 2026-10-24: "search the
web yourself, set the labels yourself" — and they are not below the
operator's: they replace theirs, the old one kept in `label_log`).

The file is a JSON array of `{"a", "b", "relation", "direction",
"confidence", "why", "source"}`: `relation` one of same / enhanced /
remaster_of / remake_of / demo_of / extra_of / contains / series /
not_related, `direction` "a" or "b" for the side that is the enhanced /
remaster / … one. Only high and medium confidence answers are written, as
`decided_by = claude-web`; each pair's versions are linked again after. An
answer marked `"searched": false` is never written (owner, 2026-10-25: the
point is that the agent looked it up — an answer from memory is not a label).

Two more kinds of answer (`scripts/review_questions.py`): `{"type": "hltb",
"version_id", "hltb_id", "verdict": "same" | "wrong"}` — a confirmed link
becomes the operator's (`manual`), a wrong automatic
HLTB link becomes a refusal — and `{"type": "series", "game_id",
"series_id", "verdict": "yes" | "no"}` — a game said to be in a series or
not, as the advisers' word (never over the operator's).
`--source gemini-web` writes another adviser's answers (Gemini Argon,
owner 2026-10-25): those never replace a label a pair already has, unless
`--overrule` (owner, 2026-10-27: Gemini's answer taken where two advisers
differed).
Run with the viewer stopped (one linker at a time).

Usage:
    … -m scripts.web_labels [--schema dev] answers.json [more.json …] [--dry-run]
        [--source gemini-web]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bot.db import tools
from bot.db.repo import Repo
from bot.services.game_link import GameLinker
from bot.services.game_match import MODEL
from bot.services.label_conflicts import around, conflicts
from scripts.catalog_viewer import _put_in_series

SOURCE = "claude-web"
RELATIONS = {
    "same": "same",
    "enhanced": "enhanced_of",
    "enhanced_of": "enhanced_of",
    "mode_of": "mode_of",
    "remaster_of": "remaster_of",
    "remake_of": "remake_of",
    "demo_of": "demo_of",
    "tool_of": "tool_of",
    "extra_of": "extra_of",
    "pass_of": "pass_of",
    "vr_of": "vr_of",
    "contains": "contains",
    "series": "series",
    "not_related": "other",
}
DIRECTED = {
    "enhanced_of",
    "remaster_of",
    "remake_of",
    "vr_of",
    "demo_of",
    "tool_of",
    "mode_of",
    "extra_of",
    "pass_of",
    "contains",
}


def usable(answer: dict) -> bool:
    return answer.get("confidence") in ("high", "medium") and answer.get("searched") is not False


def label_of(answer: dict) -> tuple[int, int, str, str] | None:
    """(subject, other, relation, the series it names) of one answer, or
    None when it is not to be written."""
    if not usable(answer):
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
    series = str(answer.get("series_name") or "").strip() if relation == "series" else ""
    return a, b, relation, series


async def write(
    schema: str | None,
    labels: list[tuple[int, int, str, str]],
    others: list[dict] | None = None,
    source: str = SOURCE,
    overrule: bool | None = None,
) -> None:
    database = await tools.open_database(schema=schema)
    try:
        repo = Repo(database)
        if overrule is None:
            overrule = source == SOURCE
        if not overrule:
            held = {
                frozenset((int(d["version_id"]), int(d["other_id"])))
                for d in await repo.decisions_among(
                    sorted({v for a, b, *_ in labels for v in (a, b)})
                )
            }
            labels = [lab for lab in labels if frozenset(lab[:2]) not in held]
            print(f"{len(labels)} of them on pairs with no label yet")
        for answer in others or []:
            if answer["type"] == "hltb" and answer.get("verdict") == "wrong":
                await repo.unlink_version_hltb(
                    int(answer["version_id"]), int(answer["hltb_id"]), only_auto=True
                )
            elif answer["type"] == "hltb" and answer.get("verdict") == "same":
                # Confirmed: no longer an automatic guess, never asked again.
                await repo.link_version_hltb(
                    int(answer["version_id"]), int(answer["hltb_id"]), source="manual"
                )
            elif answer["type"] == "series" and answer.get("verdict") in ("yes", "no"):
                await repo.set_series_member(
                    int(answer["game_id"]),
                    int(answer["series_id"]),
                    answer["verdict"] == "yes",
                    source="advisers",
                    decided_by=source,
                )
        for a, b, relation, _series in labels:
            features, model = await repo.pair_features(a, b)
            await repo.save_decision(
                a,
                b,
                relation,
                features=features,
                model=model or MODEL,
                decided_by=source,
                overrule=overrule,
            )
        await GameLinker(repo).link_versions(sorted({v for a, b, *_ in labels for v in (a, b)}))
        touched = {v for a, b, *_ in labels for v in (a, b)}
        clash = around(conflicts(await repo.all_decisions()), touched)
        if clash:
            print(f"{len(clash)} contradiction(s) among these answers: see /conflicts")
        # "Another game of the series" says which, as the viewer's answer does.
        for a, b, _relation, series in labels:
            if series:
                await _put_in_series(repo, "", [series], (a, b))
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    tools.add_arguments(parser)
    parser.add_argument("files", nargs="+")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", default=SOURCE)
    parser.add_argument(
        "--overrule", action="store_true", help="replace the labels pairs have, whoever's"
    )
    args = parser.parse_args()
    labels, others = [], []
    for path in args.files:
        for answer in json.loads(Path(path).read_text("utf-8")):
            if answer.get("type") in ("hltb", "series"):
                if usable(answer):
                    others.append(answer)
                continue
            label = label_of(answer)
            print(
                ("  " if label else "- ") + f"{answer['a']}:{answer['b']} {answer['relation']}"
                f" {answer.get('direction') or ''} {answer.get('confidence')}"
            )
            if label:
                labels.append(label)
    print(f"{len(labels)} labels, {len(others)} HLTB and series answers")
    if not args.dry_run:
        tools.run(write(args.schema, labels, others, args.source, args.overrule or None))


if __name__ == "__main__":
    main()
