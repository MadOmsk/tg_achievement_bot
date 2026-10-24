"""The review tab's adviser cards (owner, 2026-10-23): one tap is an answer,
the other answers wait under «Own answer…», the missing-versions questions
are the octopus's."""

from __future__ import annotations

from scripts import trial_page


def test_each_advisers_answer_is_a_button_that_records_it() -> None:
    per = {
        "gemini": {"relation": "('remake_of', 'first')"},
        "gpt": {"relation": "('remake_of', 'first')"},
        "sonnet": {"relation": "('series', None)"},
    }
    html, agreed = trial_page._ask("R:1:2", "relation", list(per), per, {}, "How are they related")
    assert not agreed
    picks = html.split("<details class=own>")[0]
    assert 'name="d:relation" value="(&#x27;remake_of&#x27;, &#x27;first&#x27;)"' in picks
    assert "1 is a remake of 2<small>gemini, gpt</small>" in picks
    assert "one series<small>sonnet</small>" in picks
    # The rest, and a field for one's own, only under «Own answer…»; no save.
    own = html.split("<details class=own>")[1]
    assert "one game" in own and "name='o:relation'" in own
    assert "one game" not in picks
    assert "save" not in html


def test_an_answered_decision_says_what_was_answered() -> None:
    per = {"a": {"relation": "('same', None)"}, "b": {"relation": "('series', None)"}}
    labels = {"R:1:2|relation": "('series', None)"}
    html, _agreed = trial_page._ask(
        "R:1:2", "relation", list(per), per, labels, "How are they related"
    )
    assert "✓ one series" in html


def test_missing_versions_wait_for_the_octopus() -> None:
    kinds = dict(trial_page.kinds())
    assert "M" not in kinds
    assert kinds["R"] == "Games related"


def test_one_series_says_which() -> None:
    """LEGO Harry Potter and LEGO Batman meet only in LEGO (owner,
    2026-10-24): "one series" is a button per series both games are in."""
    per = {"a": {"relation": "('series', None)"}, "b": {"relation": "('not_related', None)"}}
    series = [(304, "LEGO"), (4, "STAR WARS Dark Forces")]
    html, _agreed = trial_page._ask(
        "R:5541:2724", "relation", list(per), per, {}, "How are they related", series
    )
    picks = html.split("<details class=own>")[0]
    assert 'value="(&#x27;series&#x27;, None)#304">one series — LEGO<small>a</small>' in picks
    assert "one series — STAR WARS Dark Forces" in picks
    # Another series, by name, under «Own answer…».
    assert "list=series-names" in html and "#new" in html

    labels = {"R:5541:2724|relation": "('series', None)", "R:5541:2724|relation.series": "304"}
    html, _agreed = trial_page._ask(
        "R:5541:2724", "relation", list(per), per, labels, "How are they related", series
    )
    assert "✓ one series — LEGO" in html


def test_several_series_are_typed_by_commas() -> None:
    assert trial_page.series_names(" LEGO, Batman ,,LEGO ") == ["LEGO", "Batman"]
    assert trial_page.series_names("") == []


def test_an_edition_no_longer_the_games_own_is_not_asked() -> None:
    """The trial is a snapshot: FIFA 16's bundles throw Plants vs. Zombies in,
    and are none of its editions any more (2026-10-24)."""
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE versions (version_id INTEGER, game_id INTEGER);"
        "CREATE TABLE editions (edition_id INTEGER, scope TEXT);"
        "CREATE TABLE edition_items (edition_id INTEGER, version_id INTEGER, role TEXT);"
        "INSERT INTO versions VALUES (1, 837), (2, 2844);"
        "INSERT INTO editions VALUES (10, 'edition'), (11, 'edition');"
        # 10: FIFA's edition, PvZ a bonus in it; 11: PvZ's own.
        "INSERT INTO edition_items VALUES (10, 2, 'main'), (10, 1, 'bonus'), (11, 1, 'main');"
    )
    keys = ["e10.kind", "e10.holds", "e11.kind", "name"]
    assert trial_page.current_keys(conn, "E:837", keys) == ["e11.kind", "name"]
    assert trial_page.current_keys(conn, "R:1:2", keys) == keys
