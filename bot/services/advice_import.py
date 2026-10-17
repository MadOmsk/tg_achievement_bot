"""The advisers' answers to a full run, as labels (#147; owner, 2026-10-17:
the networks dig, the model learns from what they agree on). Three advisers
(Gemini Argon, GPT Pro, Sonnet) answer the same question files; each answer is
cut into decisions (`scripts/compare_answers.decisions`), and a decision two
or three of them gave alike becomes a label — `match_fit.UNANIMOUS` (0.8) or
`MAJORITY` (0.4). One against one against one is nobody's: the operator's
queue.

Every label is kept as it came (`adviser_labels`) and teaches the model with
its weight. Only what all three agree on is also written into the database
(owner, 2026-10-17: two of three is not sure enough to change the games) —
a pair of versions (`match_decisions`, never over the operator's), a
HowLongToBeat link refused. No database access here but through the repo.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from bot.db.repo import Repo
from bot.services.match_fit import MAJORITY, UNANIMOUS

# A release's kind, as the label a pair of versions takes against its game's
# anchor: the game itself (any edition, a remake's release …), or a part of it.
KIND_RELATION = {
    "game": "same",
    "edition": "same",
    "remaster": "same",
    "remake": "same",
    "episode": "same",
    "demo": "demo_of",
    "tool": "tool_of",
    "mode": "mode_of",
    "soundtrack": "extra_of",
}
RELATION_OF = {
    "same": "same",
    "series": "series",
    "not_related": "other",
    "remaster_of": "remaster_of",
    "remake_of": "remake_of",
    "contains": "contains",
    "vr_of": "vr_of",
}


@dataclass
class Consensus:
    question: str
    decision: str
    value: str
    source: str  # UNANIMOUS or MAJORITY
    said: dict[str, str]


@dataclass
class ApplyReport:
    labels: int = 0
    pairs: int = 0
    kept_operators: int = 0
    hltb_refused: int = 0
    dlc_hltb_refused: int = 0
    series: int = 0
    editions: int = 0
    psn_groups: int = 0
    dlc_links: int = 0
    hltb_restored: int = 0
    skipped: Counter = field(default_factory=Counter)


def consensus(question: str, per: dict[str, dict[str, object]]) -> list[Consensus]:
    """Every decision of one question that two or three advisers gave alike."""
    out = []
    keys = set().union(*(d.keys() for d in per.values())) if per else set()
    for key in sorted(keys):
        said = {name: str(answers.get(key, "—")) for name, answers in per.items()}
        value, count = Counter(said.values()).most_common(1)[0]
        if value == "—" or count < 2:
            continue
        source = UNANIMOUS if count == len(per) and count >= 3 else MAJORITY
        out.append(Consensus(question, key, value, source, said))
    return out


def _relation(value: str) -> tuple[str, str | None] | None:
    m = re.fullmatch(r"\('([a-z_]+)', (?:'([a-z]+)'|None)\)", value)
    return (m[1], m[2]) if m else None


async def apply(repo: Repo, labels: list[Consensus], run: str) -> ApplyReport:
    """Keep every label; write the pairs and the refusals."""
    report = ApplyReport()
    for c in labels:
        await repo.save_adviser_label(run, c.question, c.decision, c.value, c.source, c.said)
        report.labels += 1
    touched: set[int] = set()
    for c in labels:
        kind, _, rest = c.question.partition(":")
        if c.source != UNANIMOUS:
            report.skipped["two of three: teaches only"] += 1
            continue
        try:
            if kind == "G":
                await _game_card(repo, c, rest, report, touched)
            elif kind in ("R", "D"):
                await _games_pair(repo, c, rest, report, touched)
            elif kind == "X":
                await _refused(repo, c, rest, report)
            elif kind == "S":
                await _series(repo, c, rest, report)
            elif kind == "E":
                await _edition(repo, c, rest, report)
            elif kind == "P":
                await _psn_group(repo, c, rest, report)
            elif kind == "H":
                await _dlc_hltb(repo, c, report)
            else:
                report.skipped[f"{kind}: kept only"] += 1
        except Exception as exc:  # one label's trouble is not the run's
            report.skipped[f"error {type(exc).__name__}"] += 1
    if touched:
        from bot.services.game_link import GameLinker

        await GameLinker(repo).link_versions(sorted(touched))
    return report


async def _pair(
    repo: Repo, a: int, b: int, relation: str, c: Consensus, report: ApplyReport, touched: set[int]
) -> None:
    if a == b:
        return
    existing = await repo.decision_of_pair(a, b)
    if (
        existing is not None
        and existing["decided_by"] not in (UNANIMOUS, MAJORITY)
        and not str(existing["decided_by"]).startswith(("claude", "model"))
    ):
        report.kept_operators += 1  # the operator's word stays
        return
    features, model = await repo.pair_features(a, b)
    await repo.save_decision(a, b, relation, features=features, model=model, decided_by=c.source)
    report.pairs += 1
    touched.update((a, b))


async def _game_card(
    repo: Repo, c: Consensus, rest: str, report: ApplyReport, touched: set[int]
) -> None:
    game_id = int(rest)
    anchor = await repo.game_anchor(game_id)
    if m := re.fullmatch(r"v(\d+)\.belongs", c.decision):
        if anchor is not None and c.value == "no":
            await _pair(repo, int(m[1]), anchor, "other", c, report, touched)
        return
    if m := re.fullmatch(r"v(\d+)\.kind", c.decision):
        relation = KIND_RELATION.get(c.value)
        if anchor is not None and relation:
            await _pair(repo, int(m[1]), anchor, relation, c, report, touched)
        else:
            report.skipped[f"G kind {c.value}: kept only"] += 1
        return
    if m := re.fullmatch(r"v(\d+)\.hltb(\d+)", c.decision):
        if c.value == "wrong":
            await repo.unlink_version_hltb(int(m[1]), int(m[2]), only_auto=True)
            report.hltb_refused += 1
        return
    if c.decision == "series":
        await _game_series(repo, c, game_id, report)
        return
    if m := re.fullmatch(r"dlc(\d+)\.hltb(\d+)", c.decision):
        if c.value == "wrong":
            await repo.reject_dlc_hltb(int(m[1]), int(m[2]))
            report.dlc_hltb_refused += 1
        return
    report.skipped[f"G {c.decision.split('.')[-1]}: kept only"] += 1


async def _games_pair(
    repo: Repo, c: Consensus, rest: str, report: ApplyReport, touched: set[int]
) -> None:
    first, second = (int(x) for x in rest.split(":"))
    parsed = _relation(c.value)
    if parsed is None or parsed[0] not in RELATION_OF:
        report.skipped[f"{c.question[0]} {c.value}: kept only"] += 1
        return
    relation, direction = RELATION_OF[parsed[0]], parsed[1]
    a, b = await repo.game_anchor(first), await repo.game_anchor(second)
    if a is None or b is None:
        return
    if direction == "second":
        a, b = b, a
    await _pair(repo, a, b, relation, c, report, touched)


def _names(value: str) -> list[str]:
    value = value.strip()
    if value.startswith("(") and value.endswith(")"):
        value = value[1:-1]
    return [x.strip(" '\"") for x in value.split(",") if x.strip(" '\"")]


async def _game_series(repo: Repo, c: Consensus, game_id: int, report: ApplyReport) -> None:
    """The series a game card says it is in: each one we have takes it."""
    for name in _names(c.value):
        series_id = await repo.series_by_name(name)
        if series_id is None:
            report.skipped["G series not in the database: kept only"] += 1
            continue
        await repo.set_series_member(
            game_id, series_id, True, source="advisers", decided_by=c.source
        )
        report.series += 1


async def _series(repo: Repo, c: Consensus, rest: str, report: ApplyReport) -> None:
    if m := re.fullmatch(r"g(\d+)", c.decision):
        if c.value in ("yes", "no"):
            await repo.set_series_member(
                int(m[1]), int(rest), c.value == "yes", source="advisers", decided_by=c.source
            )
            report.series += 1
        return
    report.skipped[f"S {c.decision}: kept only"] += 1


async def _edition(repo: Repo, c: Consensus, rest: str, report: ApplyReport) -> None:
    if m := re.fullmatch(r"e(\d+)\.kind", c.decision):
        await repo.set_edition_kind(int(m[1]), c.value)
        report.editions += 1
    elif (m := re.fullmatch(r"e(\d+)\.holds", c.decision)) and c.value == "no":
        await repo.detach_edition_from_game(int(m[1]), int(rest))
        report.editions += 1


async def _psn_group(repo: Repo, c: Consensus, rest: str, report: ApplyReport) -> None:
    version_id, _, group_id = rest.partition(":")
    if c.decision != "addon" or c.value in ("None", "", "—"):
        return
    if await repo.link_trophy_group_to_addon(int(version_id), group_id, c.value):
        report.psn_groups += 1
    else:
        report.skipped["P add-on not a DLC of that version"] += 1


async def _dlc_hltb(repo: Repo, c: Consensus, report: ApplyReport) -> None:
    if c.decision != "links":
        return
    for pair in _names(c.value):
        dlc, _, hltb = pair.partition("->")
        if dlc.isdigit() and hltb.isdigit():
            await repo.link_dlc_hltb(int(dlc), int(hltb))
            report.dlc_links += 1


async def _refused(repo: Repo, c: Consensus, rest: str, report: ApplyReport) -> None:
    version_id, _, hltb_id = rest.partition(":")
    if c.decision == "verdict" and c.value == "same":
        await repo.restore_version_hltb(int(version_id), int(hltb_id))
        report.hltb_restored += 1
