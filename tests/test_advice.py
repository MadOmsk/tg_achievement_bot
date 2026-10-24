"""The advisers' review of the matcher's pairs (#147; owner, 2026-10-12)."""

from __future__ import annotations

import json
from pathlib import Path

from bot.services.advice import (
    ALL_THREE,
    BOTH,
    AdviceStore,
    Answer,
    audit_picked,
    decide,
    gemini_line,
    label_of,
    pair_state,
    parse_answers,
    proposal_answer,
    validate,
)
from bot.services.game_match import WEIGHTS, probabilities
from bot.services.match_fit import ADVISER_WEIGHT, Example, fit, label_weight
from scripts.advise_pairs import Facts, _write_label, apply_one, import_answers, write_batches
from scripts.catalog_viewer import _proposal_decision, load_gemini


def _a(relation: str, direction: str | None = None, confidence: str = "high") -> Answer:
    return Answer(relation, direction, confidence, "because")


MODEL_REMASTER = _a("remaster_of", "first")

# ---------------------------------------------------------------- the rule


def test_all_three_agreeing_is_the_models_label_too() -> None:
    out = decide(MODEL_REMASTER, _a("remaster_of", "first"), _a("remaster_of", "first", "medium"))
    assert (out.state, out.decided_by, out.answer.relation) == ("agreed", ALL_THREE, "remaster_of")


def test_the_advisers_agreeing_against_the_model_is_theirs() -> None:
    out = decide(MODEL_REMASTER, _a("same"), _a("same"))
    assert (out.state, out.decided_by) == ("agreed", BOTH)


def test_advisers_disagreeing_leave_it_to_the_operator() -> None:
    out = decide(MODEL_REMASTER, _a("same"), _a("remake_of", "first"))
    assert out.state == "conflict" and out.answer is None


def test_an_unsure_or_low_answer_leaves_it_to_the_operator() -> None:
    assert decide(MODEL_REMASTER, _a("same"), _a("same", confidence="low")).state == "conflict"
    assert decide(MODEL_REMASTER, _a("unsure"), _a("same")).state == "conflict"


def test_series_and_not_related_agree_and_claudes_word_is_kept() -> None:
    out = decide(_a("not_related"), _a("series"), _a("not_related"))
    assert out.state == "agreed" and out.answer.relation == "series"
    assert out.decided_by == ALL_THREE  # the model said "not related"
    assert decide(MODEL_REMASTER, _a("extra"), _a("series")).state == "agreed"


def test_a_directed_relation_must_point_the_same_way() -> None:
    assert decide(None, _a("remaster_of", "first"), _a("remaster_of", "second")).state == "conflict"
    out = decide(MODEL_REMASTER, _a("remaster_of", "second"), _a("remaster_of", "second"))
    assert (out.state, out.decided_by) == ("agreed", BOTH)  # the model had it backwards


def test_a_demo_agrees_with_a_model_that_said_one_game() -> None:
    out = decide(_a("same"), _a("demo_of", "first"), _a("demo_of", "first"))
    assert out.decided_by == ALL_THREE


def test_waiting_for_an_adviser() -> None:
    assert decide(None, None, None).state == "waiting_both"
    assert decide(None, _a("same"), None).state == "waiting_gemini"
    assert decide(None, None, _a("same")).state == "waiting_claude"


def test_an_answer_is_written_as_the_viewers_labels() -> None:
    assert label_of(_a("series")) == ("series", False)
    assert label_of(_a("not_related")) == ("other", False)
    assert label_of(_a("extra")) == ("other", False)
    assert label_of(_a("contains", "second")) == ("contains", True)
    assert label_of(_a("unsure")) is None


# ---------------------------------------------------------------- the audit


def test_the_audit_sample_is_reproducible_and_about_its_share() -> None:
    ids = [f"g:{i}:{i + 1}" for i in range(20000)]
    first = {p for p in ids if audit_picked(p, 0.05, 147)}
    again = {p for p in ids if audit_picked(p, 0.05, 147)}
    assert first == again
    assert 800 < len(first) < 1200
    assert first <= {p for p in ids if audit_picked(p, 0.1, 147)}  # a pair picked stays picked
    assert first != {p for p in ids if audit_picked(p, 0.05, 148)}
    assert not any(audit_picked(p, 0.0) for p in ids[:100])


# ---------------------------------------------------------------- export and import


def _questions() -> dict[str, dict]:
    return {
        "g:1:2": {
            "pair_id": "g:1:2",
            "type": "games",
            "audit": False,
            "model": {"relation": "remake_of", "direction": "first", "p": 0.6},
            "game_a": 1,
            "game_b": 2,
            "first": '"Dead Space" (2023)',
            "second": '"Dead Space" (2008)',
        },
        "h:steam:10:99": {
            "pair_id": "h:steam:10:99",
            "type": "hltb",
            "audit": True,
            "model": {"relation": "same", "direction": None, "p": 0.8},
            "platform": "steam",
            "title_id": "10",
            "hltb_id": 99,
            "first": "a list",
            "second": "an entry",
        },
    }


def test_export_and_import_round_trip(tmp_path: Path) -> None:
    store = AdviceStore(tmp_path / "advice")
    questions = _questions()
    store.save_questions(questions, list(questions), "2026-10-12T00:00:00Z")
    written = write_batches(store, store.questions(), list(questions), tmp_path / "batches")
    assert written == {"claude": 1, "gemini": 1}
    text = (tmp_path / "batches" / "gemini" / "batch_01.txt").read_text(encoding="utf-8")
    assert "id: g:1:2" in text and "id: h:steam:10:99" in text
    assert "remake_of 0.6" not in text and '"p"' not in text  # the model's guess is not shown

    reply = tmp_path / "gemini.txt"
    reply.write_text(
        "Here you go:\n```json\n"
        + json.dumps(
            [
                {"pair_id": "g:1:2", "relation": "remake_of", "direction": "first",
                 "confidence": "high", "why": "rebuilt"},
                {"pair_id": "h:steam:10:99", "relation": "same", "direction": None,
                 "confidence": "medium", "why": "same game"},
                {"pair_id": "g:9:9", "relation": "same", "confidence": "high"},
                {"pair_id": "g:1:2", "relation": "remaster_of", "confidence": "high"},
                {"pair_id": "h:steam:10:99", "relation": "remake_of", "direction": "first"},
            ]
        )
        + "\n```\nHope it helps.",
        encoding="utf-8",
    )  # fmt: skip
    stored, refused = import_answers(store, "gemini", [reply])
    assert stored == 2 and len(refused) == 3
    assert store.answers("gemini")["g:1:2"] == Answer("remake_of", "first", "high", "rebuilt")

    claude = tmp_path / "claude.json"
    claude.write_text(
        json.dumps([{"pair_id": "g:1:2", "relation": "remake_of", "direction": "first",
                     "confidence": "medium", "why": "x"}]),
        encoding="utf-8",
    )  # fmt: skip
    import_answers(store, "claude", [claude])
    state = pair_state("g:2:1", store.directory)  # either way round
    assert (state.state, state.decided_by) == ("agreed", ALL_THREE)
    assert pair_state("h:steam:10:99", store.directory).state == "waiting_claude"
    # A second export does not ask an adviser again what it answered.
    written = write_batches(store, store.questions(), list(questions), tmp_path / "batches")
    assert written == {"claude": 1, "gemini": 0}


def test_answers_are_read_from_prose_and_checked() -> None:
    found = parse_answers('Sure! [{"pair_id": "g:1:2", "relation": "Not related"}] bye')
    assert found == [{"pair_id": "g:1:2", "relation": "Not related"}]
    answer = validate(found[0], _questions())
    assert isinstance(answer, Answer) and answer.relation == "not_related"
    assert answer.confidence == "low"  # none given: never decides alone


def test_the_viewer_reads_the_conflicts_as_the_advisers_meant_them(tmp_path: Path) -> None:
    for answer, model, decision in (
        (_a("remake_of", "first"), "remake_of", "remake_of"),
        (_a("remake_of", "second"), "remake_of", "remake_of:flip"),
        (_a("remaster_of", "second"), "remake_of", "remaster_of:flip"),
        (_a("extra"), "remake_of", "other"),
        (_a("series"), "remake_of", "series"),
    ):
        assert _proposal_decision(proposal_answer(answer, model), model) == decision
    (tmp_path / "answers.txt").write_text(
        "\n".join(
            line
            for line in (
                gemini_line(1, _a("contains", "second")),
                gemini_line(2, _a("extra")),
                gemini_line(3, _a("unsure")),
            )
            if line
        ),
        encoding="utf-8",
    )
    read = load_gemini(tmp_path)
    assert read[1]["decision"] == "contains:flip"
    assert read[2]["decision"] == "other"
    assert 3 not in read  # "unsure" is no decision to offer


# ---------------------------------------------------------------- applying


class _Repo:
    def __init__(self) -> None:
        self.saved: list[tuple] = []

    async def pair_features(self, a: int, b: int) -> tuple[None, None]:
        return None, None

    async def save_decision(self, a: int, b: int, relation: str, **kw: object) -> None:
        self.saved.append((a, b, relation, kw["decided_by"]))


def _facts(labels: list[dict]) -> Facts:
    facts = Facts()
    for v, g in ((10, 1), (11, 1), (20, 2)):
        facts.versions[v] = {"platform": None, "title_id": None}
        facts.game_of[v] = g
        facts.members[g].append(v)
    facts.games = {1: {"anchor_version_id": 10}, 2: {"anchor_version_id": 20}}
    facts.labels = labels
    return facts


async def test_an_operators_label_is_never_overwritten() -> None:
    repo = _Repo()
    operator = {"version_id": 11, "other_id": 20, "relation": "other", "decided_by": "viewer"}
    facts = _facts([operator])
    q = _questions()["g:1:2"]
    done = await apply_one(repo, facts, q, _a("remake_of", "first"), BOTH, dry_run=False)  # type: ignore[arg-type]
    assert done["state"] == "operator" and not repo.saved
    assert await _write_label(repo, _facts([operator]), 20, 11, "same", BOTH, False) == "operator"  # type: ignore[arg-type]
    assert not repo.saved


async def test_an_advisers_label_may_be_answered_again() -> None:
    repo = _Repo()
    before = {"version_id": 10, "other_id": 20, "relation": "other", "decided_by": BOTH}
    facts = _facts([before])
    q = _questions()["g:1:2"]
    done = await apply_one(repo, facts, q, _a("remake_of", "second"), ALL_THREE, dry_run=False)  # type: ignore[arg-type]
    assert done["state"] == "applied"
    assert repo.saved == [(20, 10, "remake_of", ALL_THREE)]  # "second": game 2 is the remake


# ---------------------------------------------------------------- the fit


def test_the_operators_labels_outweigh_the_advisers() -> None:
    from bot.services.match_fit import MAJORITY, UNANIMOUS

    # Owner, 2026-10-17: the operator 0.9, three advisers 0.8, two of three 0.4.
    assert label_weight("viewer") == 0.9
    assert label_weight(UNANIMOUS) == label_weight(ALL_THREE) == 0.8
    assert label_weight(MAJORITY) == ADVISER_WEIGHT == 0.4
    assert label_weight(BOTH) == 0.7
    f = {"bias": 1.0, "name": 0.1, "years_near": 1.0}
    examples = [Example(dict(f), "same", label_weight("viewer")) for _ in range(10)] + [
        Example(dict(f), "other", label_weight(BOTH)) for _ in range(10)
    ]
    fitted = fit(examples, WEIGHTS, strength=0.01, rate=0.2, epochs=400)
    probs = probabilities(f, fitted)
    assert probs["same"] > probs["other"]


async def test_three_advisers_agreeing_write_a_pair_two_only_teach(repo) -> None:
    from bot.services.advice_import import apply, consensus
    from bot.services.match_fit import MAJORITY, UNANIMOUS
    from bot.services.stores import StoreVersion

    a = await repo.save_version(
        StoreVersion(store="steam", product_id="1", console="steam", name="Game"),
        platform=None,
        title_id=None,
    )
    b = await repo.save_version(
        StoreVersion(store="psn", product_id="2", console="ps4", name="Game Demo"),
        platform=None,
        title_id=None,
    )
    game = await repo.create_game("Game", 2020, a)
    await repo.write_members({a: (game, "version", None, None), b: (game, "version", None, None)})
    per = {
        "argon": {f"v{b}.kind": "demo", f"v{b}.belongs": "yes"},
        "gpt": {f"v{b}.kind": "demo", f"v{b}.belongs": "yes"},
        "sonnet": {f"v{b}.kind": "demo", f"v{b}.belongs": "no"},
    }
    labels = consensus(f"G:{game}", per)
    assert {(c.decision, c.value, c.source) for c in labels} == {
        (f"v{b}.kind", "demo", UNANIMOUS),
        (f"v{b}.belongs", "yes", MAJORITY),
    }
    report = await apply(repo, labels, "test")
    assert report.labels == 2 and report.pairs == 1
    label = await repo.decision_of_pair(a, b)
    assert label["relation"] == "demo_of" and label["decided_by"] == UNANIMOUS


async def test_a_psn_group_all_three_name_takes_its_add_on(repo) -> None:
    from bot.services.advice_import import apply, consensus
    from bot.services.stores import StoreDlc, StoreVersion

    v = await repo.save_version(
        StoreVersion(store="psn", product_id="9", console="ps4", name="Game"),
        platform=None,
        title_id=None,
    )
    await repo._conn.execute(
        "INSERT INTO dlcs (version_id, trophy_group_id, name, kind, updated_at)"
        " VALUES (?, '001', 'The Heist', 'dlc', 'now')",
        (v,),
    )
    await repo._conn.commit()
    await repo.save_dlc(v, StoreDlc(store_id="UP1-CUSA1_00-HEIST", name="The Heist"))
    per = {n: {"addon": "up1-cusa1_00-heist"} for n in ("a", "b", "c")}  # lower-cased
    report = await apply(repo, consensus(f"P:{v}:001", per), "test")
    assert report.psn_groups == 1
    cursor = await repo._conn.execute("SELECT store_id, trophy_group_id FROM dlcs")
    assert [tuple(r) for r in await cursor.fetchall()] == [("UP1-CUSA1_00-HEIST", "001")]
