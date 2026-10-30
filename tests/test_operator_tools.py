"""The operator's scripts run their queries on PostgreSQL (#234): every question
they make, on a catalog with a row of every kind."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest

from bot.db import tools
from bot.db.repo import Database, Repo
from scripts import (
    advise_pairs,
    argon_export,
    catalog_files,
    label_queue_answers,
    label_queue_prompt,
    review_questions,
    trial_page,
    web_labels,
)
from tests.catalog_seed import seed_catalog
from tests.conftest import TEST_SCHEMA


@pytest.fixture
async def seeded(database: Database, repo: Repo, tmp_path: Path, monkeypatch) -> Repo:
    await seed_catalog(repo._conn)
    settings = SimpleNamespace(
        database_url=database._dsn, database_schema=TEST_SCHEMA, db_path=tmp_path / "bot.db"
    )
    for module in (tools, advise_pairs, label_queue_answers):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    return repo


@pytest.fixture
def conn(seeded: Repo):
    with tools.connect(schema=TEST_SCHEMA, readonly=True) as connection:
        yield connection


def test_the_export_makes_every_kind_of_question(conn) -> None:
    cards = argon_export.game_cards(conn)
    assert {c["game_id"] for c in cards} == {1, 2, 3}
    relations = argon_export.relation_questions(conn)
    assert any(q["id"] == "R:2:1" for q in relations)
    duplicates = argon_export.duplicate_questions(conn, {frozenset(q["games"]) for q in relations})
    assert isinstance(duplicates, list)
    assert any(q["id"] == "S:40" for q in argon_export.series_questions(conn))
    groups = argon_export.psn_group_questions(conn)
    assert "(7 trophies)" in groups[0]["text"] and "EP1-CUSA" in groups[0]["text"]
    editions = argon_export.edition_questions(conn)
    assert any(q["id"] == "E:1" and "Control Ultimate" in q["text"] for q in editions)
    assert any(q["id"] == "H:1" for q in argon_export.dlc_hltb_questions(conn))
    assert any(q["id"] == "X:12:102" for q in argon_export.refused_questions(conn))


def test_the_review_questions_are_built(conn, seeded: Repo) -> None:
    questions = review_questions.build(TEST_SCHEMA, 40)
    kinds = {q["type"] for q in questions}
    assert kinds == {"pair", "hltb", "series"}
    hltb = next(q for q in questions if q["type"] == "hltb")
    assert hltb["hltb"]["platforms"] == "PC, Xbox"
    # A membership of no known probability sorts first, as in SQLite.
    series = [q for q in questions if q["type"] == "series"]
    assert series[0]["game_id"] == 2 and "Control" in series[0]["other_games_in_series"]
    assert review_questions.recheck_questions(TEST_SCHEMA, 2)


async def test_the_advisers_questions_are_built(seeded: Repo, tmp_path: Path) -> None:
    database = await advise_pairs.open_read_only(TEST_SCHEMA)
    try:
        # The script's own read-only promise is the server's.
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            await database.conn.execute("DELETE FROM games")
        facts = await advise_pairs.load_facts(database.conn)
        assert facts.hltb[100]["platforms"] == "PC, Xbox"
        assert facts.achievements[("xbox_modern", "77")] == 2
        types = {"games", "versions", "hltb", "dlc"}
        advised = await advise_pairs.advised_pairs(database.conn, facts, types)
        assert {q["type"] for q in advised.values()} >= {"games", "hltb"}
        assert any(q["type"] == "dlc" for q in advised.values())
        audit = await advise_pairs.audit_pairs(
            Repo(database), database.conn, facts, types, 1.0, 1, set()
        )
        assert isinstance(audit, dict)
    finally:
        await database.close()


async def test_the_commands_of_advise_pairs_open_the_schema(seeded: Repo, tmp_path: Path) -> None:
    args = argparse.Namespace(
        schema=TEST_SCHEMA,
        advice_dir=str(tmp_path / "advice"),
        types="games,versions,hltb,dlc",
        audit=0.0,
        seed=1,
        out=None,
    )
    await advise_pairs.export(args)
    assert (tmp_path / "advice" / "batches").is_dir()
    await advise_pairs.status(args)
    await advise_pairs.apply(argparse.Namespace(**vars(args), dry_run=True))
    await advise_pairs.apply(argparse.Namespace(**vars(args), dry_run=False))
    await advise_pairs.conflicts(
        argparse.Namespace(
            schema=TEST_SCHEMA,
            advice_dir=str(tmp_path / "advice"),
            out=str(tmp_path / "conflicts.json"),
            into_proposals=None,
            into_gemini=None,
            review=True,
        )
    )


async def test_the_labelling_queue_goes_out_and_is_scored(seeded: Repo, tmp_path: Path) -> None:
    questions = await label_queue_prompt.build(TEST_SCHEMA, 10)
    assert {q["version_id"] for q in questions} >= {12}
    held = tmp_path / "x.audit.json"
    held.write_text(
        json.dumps(
            {"p": {"version_id": 11, "other_id": 13, "relation": "not_related", "direction": None}}
        ),
        "utf-8",
    )
    label_queue_answers.score(TEST_SCHEMA, tmp_path / "x")


async def test_web_answers_are_written(seeded: Repo) -> None:
    await web_labels.write(
        TEST_SCHEMA,
        [(10, 12, "series", "A New Series")],
        [
            {"type": "hltb", "verdict": "wrong", "version_id": 10, "hltb_id": 100},
            {"type": "series", "verdict": "no", "game_id": 2, "series_id": 40},
        ],
    )
    cursor = await seeded._conn.execute(
        "SELECT relation FROM match_decisions WHERE version_id = 10 AND other_id = 12"
    )
    assert (await cursor.fetchone())[0] == "series"


async def test_the_catalog_files_command_opens_the_schema(
    seeded: Repo, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(catalog_files, "ROOT", tmp_path)
    monkeypatch.setattr(catalog_files, "LABELS", tmp_path / "labels.jsonl")
    monkeypatch.setattr(catalog_files, "WEIGHTS", tmp_path / "weights.json")
    await catalog_files.run("export", TEST_SCHEMA, False)
    assert (tmp_path / "labels.jsonl").exists()
    await catalog_files.run("import", TEST_SCHEMA, True)


def test_the_trial_cards_look_things_up(conn) -> None:
    look = trial_page._Look(conn, lambda url, size: str(url or ""), lambda row: "")
    assert "Control" in look.version(10)
    assert "/covers/c/a.png" in look.version(11)
    assert "cover.png" in look.game(1)
    assert "Control" in look.hltb(100)
    assert "The Foundation" in look.dlc(20)
    assert look.shared_series(1, 2) == [(40, "Control")]
    assert look.series_names() == ["Control", "Remedy Verse"]
    assert "v12" in look.releases(2)
    assert "Ultimate" in look.edition(30)
    assert look.edition_word(30) == "ultimate"
    assert 30 in trial_page.own_editions(conn, 1)
    assert trial_page.current_keys(conn, "E:1", ["e30.kind", "e31.kind"]) == ["e30.kind"]
