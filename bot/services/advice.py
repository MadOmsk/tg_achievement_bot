"""The advisers' review of the games matcher's doubtful pairs (#147; owner,
2026-10-12). No database access: questions, answers and the rule that turns
them into labels.

The model scores every candidate pair and decides alone where it is sure.
Where it is not — and for a seeded 5% sample of where it is (`audit_picked`),
because pairs were found where everybody was wrong — the pair is a question
for two advisers, Claude and Gemini, who answer it without seeing the model's
guess or each other's answer. Then (`decide`):

- the model, Claude and Gemini agree → a label `model+claude+gemini` (the
  model was right; it is still a training example);
- Claude and Gemini agree, the model does not → a label `claude+gemini`;
- they disagree, or either is unsure or of low confidence → nothing is
  written: the pair is the operator's.

"Another of the series", "not related" and "not a game" all relate nothing,
so they agree with each other (Claude's word is recorded); a directed
relation agrees only in the same direction. An operator's label is never
overwritten (`scripts/advise_pairs.py` checks before writing).

The questions, each adviser's answers and what was applied are JSON files
in one folder (`AdviceStore`, `data/advice/` beside the database) — not the
database: they are a work list, and the labels they lead to are written
through the same path as the operator's.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Kinds of question: two games; a version against a game; one of our
# achievement lists against an HLTB entry; one of our DLC against an HLTB DLC.
PAIR_TYPES = ("games", "versions", "hltb", "dlc")
ADVISERS = ("claude", "gemini")

# `match_decisions.decided_by` of an adviser's label; anything else (the
# viewer's "viewer") is the operator's own and is never overwritten.
BOTH = "claude+gemini"
ALL_THREE = "model+claude+gemini"
ADVISER_SOURCES = frozenset({BOTH, ALL_THREE})

BATCH_SIZE = 10
AUDIT_FRACTION = 0.05
AUDIT_SEED = 147

# Relations one side has *of* the other: "first" when the first side is the
# demo / remaster / compilation … of the second.
DIRECTED = frozenset(
    {"demo_of", "tool_of", "mode_of", "remaster_of", "remake_of", "contains", "vr_of"}
)
# Answers that relate nothing; they agree with one another.
UNRELATED = frozenset({"series", "not_related", "extra"})
_GAME_ANSWERS = frozenset(
    {"same", "remaster_of", "remake_of", "contains", "vr_of", "unsure"} | UNRELATED
)
ALLOWED: dict[str, frozenset[str]] = {
    "games": _GAME_ANSWERS,
    "versions": _GAME_ANSWERS | {"demo_of", "tool_of", "mode_of"},
    "hltb": frozenset({"same", "not_related", "unsure"}),
    "dlc": frozenset({"same", "not_related", "unsure"}),
}
CONFIDENCES = ("high", "medium", "low")

# Words an adviser may use for an allowed answer.
_SYNONYMS = {
    "other": "not_related",
    "not related": "not_related",
    "unrelated": "not_related",
    "none": "not_related",
    "one game": "same",
    "same_game": "same",
    "not_a_game": "extra",
    "not a game": "extra",
    "remaster": "remaster_of",
    "remake": "remake_of",
    "demo": "demo_of",
    "tool": "tool_of",
    "mode": "mode_of",
    "vr": "vr_of",
    "compilation": "contains",
}

# Which of the model's classes an answer is (the model has no demo or tool:
# those are "one game" to it).
_CLASS = {
    "same": "same",
    "demo_of": "same",
    "tool_of": "same",
    "mode_of": "same",
    "remaster_of": "remaster_of",
    "remake_of": "remake_of",
    "contains": "contains",
    "vr_of": "vr_of",
    "series": "other",
    "not_related": "other",
    "extra": "other",
    "other": "other",
}


@dataclass(slots=True)
class Answer:
    relation: str
    direction: str | None = None  # "first" / "second", for a directed relation
    confidence: str = "low"
    why: str = ""

    @classmethod
    def of(cls, data: dict[str, Any] | None) -> Answer | None:
        if not data:
            return None
        return cls(
            str(data.get("relation") or ""),
            data.get("direction"),
            str(data.get("confidence") or "low"),
            str(data.get("why") or ""),
        )


def meaning(answer: Answer) -> tuple[str, str | None]:
    """What an answer says, for comparing two: the unrelated ones as one."""
    if answer.relation in UNRELATED:
        return ("unrelated", None)
    if answer.relation in DIRECTED:
        return (answer.relation, answer.direction)
    return (answer.relation, None)


def usable(answer: Answer | None) -> bool:
    """An answer that may decide: sure enough, and a direction where one is
    needed."""
    return bool(
        answer is not None
        and answer.relation
        and answer.relation != "unsure"
        and answer.confidence in ("high", "medium")
        and (answer.relation not in DIRECTED or answer.direction in ("first", "second"))
    )


def model_agrees(model: Answer | None, chosen: Answer) -> bool:
    """Whether the model said what the advisers agreed on, in its own classes."""
    if model is None or model.relation in ("", "unsure"):
        return False
    mine, theirs = _CLASS.get(model.relation), _CLASS.get(chosen.relation)
    if mine is None or mine != theirs:
        return False
    return theirs in ("same", "other") or model.direction == chosen.direction


@dataclass(slots=True)
class Outcome:
    # waiting_both / waiting_claude / waiting_gemini / conflict / agreed
    state: str
    answer: Answer | None = None
    decided_by: str | None = None
    reason: str = ""


def decide(model: Answer | None, claude: Answer | None, gemini: Answer | None) -> Outcome:
    """The rule (owner, 2026-10-12): see the module's text."""
    if claude is None and gemini is None:
        return Outcome("waiting_both")
    if claude is None:
        return Outcome("waiting_claude")
    if gemini is None:
        return Outcome("waiting_gemini")
    for name, answer in (("Claude", claude), ("Gemini", gemini)):
        if not usable(answer):
            return Outcome("conflict", reason=f"{name} is not sure")
    if meaning(claude) != meaning(gemini):
        return Outcome("conflict", reason="Claude and Gemini disagree")
    by = ALL_THREE if model_agrees(model, claude) else BOTH
    return Outcome("agreed", claude, by)


def label_of(answer: Answer) -> tuple[str, bool] | None:
    """The label an agreed answer writes (`match_decisions.relation`), and
    whether it reads the other way round (the second side is the subject)."""
    if answer.relation == "series":
        return ("series", False)
    if answer.relation in UNRELATED:
        return ("other", False)
    if answer.relation == "same":
        return ("same", False)
    if answer.relation in DIRECTED:
        return (answer.relation, answer.direction == "second")
    return None


# ---------------------------------------------------------------- pair ids


def games_pair_id(game_a: int, game_b: int) -> str:
    return f"g:{game_a}:{game_b}"


def versions_pair_id(version_id: int, game_id: int) -> str:
    """A version against a game: the model's subject, and the game the other
    version of the pair is in (what the viewer's /review row shows)."""
    return f"v:{version_id}:{game_id}"


def hltb_pair_id(platform: str, title_id: str, hltb_id: int) -> str:
    return f"h:{platform}:{title_id}:{hltb_id}"


def dlc_pair_id(dlc_id: int, hltb_id: int) -> str:
    return f"d:{dlc_id}:{hltb_id}"


def pair_type(pair_id: str) -> str | None:
    return {"g": "games", "v": "versions", "h": "hltb", "d": "dlc"}.get(pair_id.split(":", 1)[0])


def audit_picked(pair_id: str, fraction: float = AUDIT_FRACTION, seed: int = AUDIT_SEED) -> bool:
    """Whether a pair the model was sure about is in the audit sample: a hash
    of the seed and the pair, so the same pairs are picked on every run and a
    pair picked once stays picked as the population grows."""
    if fraction <= 0:
        return False
    digest = hashlib.sha256(f"{seed}:{pair_id}".encode()).hexdigest()
    return int(digest[:12], 16) / float(16**12) < fraction


# ---------------------------------------------------------------- prompts

RULES = """You check pairs for a video game database. Each question has an id (copy it
exactly), a type, a FIRST side and a SECOND side.

Types and the answers each allows:
- games: two games, each with its releases.
  same | remaster_of | remake_of | contains | vr_of | series | not_related | extra | unsure
- versions: one release (FIRST) against a game (SECOND, with its releases).
  same | demo_of | tool_of | mode_of | remaster_of | remake_of | contains | vr_of | series
  | not_related | extra | unsure
- hltb: one of our games (FIRST) against a HowLongToBeat entry (SECOND).
  same (the entry is this very game) | not_related (another game, a DLC, another release
  of the series) | unsure
- dlc: one of our DLC (FIRST) against a HowLongToBeat DLC entry (SECOND).
  same | not_related | unsure

What the answers mean:
- same: one game. A port is the same game however late (PS4 and PS5, Xbox One and Series,
  PC and console, another store, a re-listing); a GOTY / Complete / Deluxe edition is the
  same game.
- demo_of: a demo, beta, trial, playtest or tech test of the other. tool_of: an editor,
  creation kit, SDK or dedicated server for it. mode_of: a launcher of one mode of it
  ("Call of Duty: Black Ops II - Zombies").
- remaster_of: the same game re-released with better technology, its design kept; an
  enhanced re-release counts. A remaster of a remake is a remaster of the remake (Gears of
  War: Reloaded is a remaster of Gears of War: Ultimate Edition).
- remake_of: rebuilt from the ground up (Resident Evil 4 of 2023 is a remake of Resident
  Evil 4 of 2005). A remake is an original of its own.
- contains: a compilation or collection that holds the other; a compilation holds at least
  two games.
- vr_of: the VR version of the other.
- series: different games of one series: sequels, prequels, spin-offs, a reboot that is a
  new game.
- not_related: unrelated.
- extra: one side is not a game at all: a soundtrack, an artbook, a companion app, a
  video, an Insider build.
- unsure: you cannot tell.

Direction, for demo_of, tool_of, mode_of, remaster_of, remake_of, contains and vr_of only:
"first" when FIRST is the demo / tool / mode / remaster / remake / compilation / VR
version of SECOND, "second" when SECOND is that of FIRST; null for every other answer.

The sides are described from store data, which may be incomplete or wrong (a store's date
is often a re-release). Rely on what you know about the real games. When you are not
sure, say confidence "low" or answer "unsure": a wrong sure answer costs more than an
unsure one.

Reply with only a JSON array, one object per question, nothing else:
[{"pair_id": "<id>", "relation": "<answer>", "direction": "first" | "second" | null,
  "confidence": "high" | "medium" | "low", "why": "at most 20 words"}]"""

_ADVISER_NOTE = {
    "claude": (
        "Answer from your own knowledge, on your own: do not read other files in the advice"
        " folder (other advisers' answers) and do not browse."
    ),
    "gemini": "A ```json code block is fine.",
}


def prompt(questions: list[dict[str, Any]], adviser: str) -> str:
    """One batch's text, ready to paste: the rules, then each question."""
    lines = [RULES, _ADVISER_NOTE.get(adviser, ""), "", "Questions:"]
    for q in questions:
        lines.append(
            f"\nid: {q['pair_id']}  (type: {q['type']})\nFIRST: {q['first']}\nSECOND: {q['second']}"
        )
    return "\n".join(lines).strip() + "\n"


def batches(pair_ids: list[str], size: int = BATCH_SIZE) -> list[list[str]]:
    return [pair_ids[i : i + size] for i in range(0, len(pair_ids), size)]


# ---------------------------------------------------------------- reading answers

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_answers(text: str) -> list[dict[str, Any]]:
    """Every answer object in an adviser's reply: a JSON array (or several in
    code blocks), prose around it ignored."""
    chunks = _FENCE.findall(text) or [text]
    found: list[dict[str, Any]] = []
    for chunk in chunks:
        chunk = chunk.strip()
        try:
            data = json.loads(chunk)
        except json.JSONDecodeError:
            start, end = chunk.find("["), chunk.rfind("]")
            if start < 0 or end <= start:
                continue
            try:
                data = json.loads(chunk[start : end + 1])
            except json.JSONDecodeError:
                continue
        if isinstance(data, dict):
            data = data.get("answers") or [data]
        found += [d for d in data if isinstance(d, dict)]
    return found


def validate(item: dict[str, Any], questions: dict[str, dict[str, Any]]) -> Answer | str:
    """An adviser's answer checked against its question: the Answer, or why
    it is refused."""
    pair_id = str(item.get("pair_id") or item.get("id") or "").strip()
    question = questions.get(pair_id)
    if question is None:
        return f"{pair_id or '?'}: no such question"
    relation = str(item.get("relation") or "").strip().lower()
    relation = _SYNONYMS.get(relation, relation).replace(" ", "_")
    if relation not in ALLOWED[question["type"]]:
        return f"{pair_id}: {relation or '(none)'} is no answer for a {question['type']} question"
    direction = item.get("direction")
    direction = str(direction).strip().lower() if direction not in (None, "") else None
    if relation in DIRECTED:
        if direction not in ("first", "second"):
            return f"{pair_id}: {relation} needs a direction (first / second)"
    else:
        direction = None
    confidence = str(item.get("confidence") or "low").strip().lower()
    if confidence not in CONFIDENCES:
        confidence = "low"
    return Answer(relation, direction, confidence, str(item.get("why") or "").strip())


# ---------------------------------------------------------------- the viewer's /proposals


def proposal_answer(answer: Answer, model_relation: str) -> str:
    """An answer about two games in the grammar of the viewer's proposals
    file (`catalog_viewer._proposal_decision`)."""
    if answer.relation == "same":
        return "same"
    if answer.relation == "series":
        return "series"
    if answer.relation in UNRELATED:
        return "not_related"
    if answer.relation in DIRECTED:
        if answer.relation == model_relation:
            return "confirm" if answer.direction == "first" else "flip"
        return f"other_relation:{answer.relation} {answer.direction}"
    return "unsure"


def gemini_line(n: int, answer: Answer) -> str | None:
    """Gemini's answer as the viewer's `--gemini` files have it
    (`n|relation|direction|confidence|why`); none for "unsure", which the
    viewer would offer as a decision."""
    if answer.relation == "unsure":
        return None
    relation = "not_related" if answer.relation == "extra" else answer.relation
    why = answer.why.replace("|", "/").replace("\n", " ")
    return f"{n}|{relation}|{answer.direction or '-'}|{answer.confidence}|{why}"


# ---------------------------------------------------------------- the store


@dataclass(slots=True)
class PairState:
    pair_id: str
    type: str | None
    # unknown / waiting_both / waiting_claude / waiting_gemini / conflict /
    # agreed (not applied yet) / applied / operator / recorded (agreed, kept
    # here: no way to write it yet)
    state: str
    decided_by: str | None = None
    model: dict[str, Any] | None = None
    claude: dict[str, Any] | None = None
    gemini: dict[str, Any] | None = None
    reason: str = ""
    audit: bool = False
    applied: dict[str, Any] | None = field(default=None)


class AdviceStore:
    """`questions.json`, `claude.json`, `gemini.json`, `applied.json` in one
    folder. Each write replaces its file whole."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    @classmethod
    def for_db(cls, db_path: Path) -> AdviceStore:
        """The store beside a database: `<its folder>/advice`."""
        return cls(Path(db_path).resolve().parent / "advice")

    def _read(self, name: str) -> dict[str, Any]:
        path = self.directory / name
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, name: str, data: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, self.directory / name)

    def questions(self) -> dict[str, dict[str, Any]]:
        return self._read("questions.json").get("pairs", {})

    def last_export(self) -> list[str]:
        return list(self._read("questions.json").get("current", []))

    def save_questions(
        self, pairs: dict[str, dict[str, Any]], current: list[str], exported_at: str
    ) -> None:
        """Questions merged into those kept: a pair asked again gets its fresh
        description and the model's fresh answer; one not asked any more is
        kept for its answers."""
        kept = self.questions()
        kept.update(pairs)
        self._write(
            "questions.json", {"exported_at": exported_at, "current": current, "pairs": kept}
        )

    def answers(self, adviser: str) -> dict[str, Answer]:
        raw = self._read(f"{adviser}.json")
        return {k: a for k, v in raw.items() if (a := Answer.of(v)) is not None}

    def save_answers(self, adviser: str, answers: dict[str, Answer]) -> None:
        self._write(f"{adviser}.json", {k: asdict(v) for k, v in answers.items()})

    def applied(self) -> dict[str, dict[str, Any]]:
        return self._read("applied.json")

    def save_applied(self, applied: dict[str, dict[str, Any]]) -> None:
        self._write("applied.json", applied)

    def state(self, pair_id: str) -> PairState:
        return _state(
            pair_id,
            self.questions(),
            self.answers("claude"),
            self.answers("gemini"),
            self.applied(),
        )


def _state(
    pair_id: str,
    questions: dict[str, dict[str, Any]],
    claude: dict[str, Answer],
    gemini: dict[str, Answer],
    applied: dict[str, dict[str, Any]],
) -> PairState:
    if pair_id not in questions and pair_id.startswith("g:"):
        # A pair of games asked the other way round.
        _, a, b = pair_id.split(":")
        if games_pair_id(int(b), int(a)) in questions:
            pair_id = games_pair_id(int(b), int(a))
    q = questions.get(pair_id)
    if q is None:
        return PairState(pair_id, pair_type(pair_id), "unknown")
    c, g = claude.get(pair_id), gemini.get(pair_id)
    model = q.get("model") or None
    outcome = decide(Answer.of(model), c, g)
    done = applied.get(pair_id)
    state = outcome.state
    if done:
        state = str(done.get("state") or "applied")
    return PairState(
        pair_id,
        q["type"],
        state,
        decided_by=(done or {}).get("decided_by") or outcome.decided_by,
        model=model,
        claude=asdict(c) if c else None,
        gemini=asdict(g) if g else None,
        reason=outcome.reason or str((done or {}).get("reason") or ""),
        audit=bool(q.get("audit")),
        applied=done,
    )


def pair_state(pair_id: str, directory: Path) -> PairState:
    """Where one pair stands with the advisers, from the store's files alone
    (for the viewer: `pair_state(pair_id, AdviceStore.for_db(db).directory)`).
    "operator" is known only for a pair `apply` found the operator had
    answered; the viewer knows its own labels better."""
    return AdviceStore(directory).state(pair_id)
