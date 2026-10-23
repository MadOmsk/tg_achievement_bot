"""The review tab's adviser cards (owner, 2026-10-23): one tap is an answer,
the other answers wait under «Свой ответ…», the missing-versions questions
are the octopus's."""

from __future__ import annotations

from scripts import trial_page


def test_each_advisers_answer_is_a_button_that_records_it() -> None:
    per = {
        "gemini": {"relation": "('remake_of', 'first')"},
        "gpt": {"relation": "('remake_of', 'first')"},
        "sonnet": {"relation": "('series', None)"},
    }
    html, agreed = trial_page._ask("R:1:2", "relation", list(per), per, {}, "Как связаны")
    assert not agreed
    picks = html.split("<details class=own>")[0]
    assert 'name="d:relation" value="(&#x27;remake_of&#x27;, &#x27;first&#x27;)"' in picks
    assert "1 — ремейк 2<small>gemini, gpt</small>" in picks
    assert "одна серия<small>sonnet</small>" in picks
    # The rest, and a field for one's own, only under «Свой ответ…»; no save.
    own = html.split("<details class=own>")[1]
    assert "одна игра" in own and "name='o:relation'" in own
    assert "одна игра" not in picks
    assert "сохранить" not in html


def test_an_answered_decision_says_what_was_answered() -> None:
    per = {"a": {"relation": "('same', None)"}, "b": {"relation": "('series', None)"}}
    labels = {"R:1:2|relation": "('series', None)"}
    html, _agreed = trial_page._ask("R:1:2", "relation", list(per), per, labels, "Как связаны")
    assert "✓ одна серия" in html


def test_missing_versions_wait_for_the_octopus() -> None:
    kinds = dict(trial_page.kinds())
    assert "M" not in kinds
    assert kinds["R"] == "Связь игр"
