"""The relations the linker set by itself, for the advisers to recheck."""

import pytest

from bot.db import tools
from bot.db.repo import Database, Repo
from bot.services.advice import DEFINITIONS
from scripts.review_questions import prompt, score, to_recheck, to_relabel
from tests.conftest import TEST_SCHEMA

NOW = "2026-10-27T00:00:00"


async def _label(repo: Repo, a: int, b: int, relation: str) -> None:
    await repo._conn.execute(
        "INSERT INTO match_decisions (version_id, other_id, relation, decided_by, decided_at)"
        " VALUES (?, ?, ?, 'viewer', ?)",
        (a, b, relation, NOW),
    )


@pytest.fixture
async def conn(database: Database, repo: Repo):
    for game in (10, 20, 30, 40, 50):
        await repo._conn.execute(
            "INSERT INTO games (game_id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (game, f"game {game}", NOW, NOW),
        )
    for version in (
        (1, 10, "Gears of War", "version", None, "2006"),
        (2, 20, "Gears of War: Ultimate Edition", "version", None, "2015"),
        (3, 30, "Fallout 3", "version", None, "2008"),
        (4, 30, "Fallout 3 GOTY", "enhanced", 3, "2009"),
        (5, 30, "Fallout 3 Demo", "demo", 3, "2008"),
        (6, 40, "Halo", "version", None, "2001"),
        (7, 50, "Halo Anniversary", "version", None, "2011"),
    ):
        await repo._conn.execute(
            "INSERT INTO versions (version_id, game_id, name, role, of_version_id, release_date,"
            " store, product_id, console, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 'steam', ?, 'steam', ?)",
            (*version, f"p{version[0]}", NOW),
        )
    await repo._conn.execute(
        "INSERT INTO game_relations (game_id, related_id, kind, source, created_at) VALUES"
        " (20, 10, 'remaster_of', 'auto', ?), (50, 40, 'remaster_of', 'manual', ?)",
        (NOW, NOW),
    )
    await _label(repo, 5, 3, "demo_of")
    with tools.connect(database._dsn, schema=TEST_SCHEMA, readonly=True) as connection:
        yield connection


def test_what_the_linker_set_alone_is_rechecked(conn) -> None:
    """An automatic relation between games, and a role in a game, until a
    label settles it; the operator's own (manual) relation is not asked."""
    assert to_recheck(conn) == [(2, 1, "remaster_of"), (4, 3, "enhanced_of")]


async def test_an_edition_labelled_same_is_asked_again(conn, repo: Repo) -> None:
    """Under the enhanced definition an edition's old "same" is in doubt;
    two plain names, or two editions, are not."""
    await _label(repo, 4, 3, "same")
    await _label(repo, 6, 3, "same")
    await _label(repo, 7, 4, "same")
    assert to_relabel(conn) == [(4, 3)]


def test_the_prompt_gives_the_definitions_as_they_stand() -> None:
    text = prompt(
        [{"type": "pair", "a": 1, "b": 2, "asked_for": "recheck: the model said", "known": "x"}],
        "2026-10-27-recheck",
    )
    assert DEFINITIONS in text
    assert "2026-10-27-recheck.<model>.json" in text
    assert "the model said" not in text and '"known"' not in text  # asked blind


def test_an_adviser_is_scored_on_the_pairs_of_known_answer() -> None:
    questions = [
        {"a": 1, "b": 2, "known": "enhanced_of"},
        {"a": 3, "b": 4, "known": "same"},
        {"a": 5, "b": 6},
    ]
    answers = [
        {"a": 1, "b": 2, "relation": "enhanced_of", "direction": "a", "confidence": "low"},
        {"a": 3, "b": 4, "relation": "series", "confidence": "high"},
        {"a": 5, "b": 6, "relation": "same", "confidence": "high"},
        {"a": 7, "b": 8, "relation": "same", "confidence": "high"},  # never asked
    ]
    report, kept = score(questions, answers)
    assert report[0] == "known pairs: 1/2 answered right (0 not answered)"
    assert kept == [answers[2]]
