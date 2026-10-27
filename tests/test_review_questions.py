"""The relations the linker set by itself, for the advisers to recheck."""

import sqlite3

from scripts.review_questions import to_recheck


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE match_decisions (version_id INTEGER, other_id INTEGER, relation TEXT);
        CREATE TABLE game_relations (game_id INTEGER, related_id INTEGER, kind TEXT,
            source TEXT);
        CREATE TABLE versions (version_id INTEGER, game_id INTEGER, name TEXT, role TEXT,
            of_version_id INTEGER, release_date TEXT);
        INSERT INTO versions VALUES
            (1, 10, 'Gears of War', 'version', NULL, '2006'),
            (2, 20, 'Gears of War: Ultimate Edition', 'version', NULL, '2015'),
            (3, 30, 'Fallout 3', 'version', NULL, '2008'),
            (4, 30, 'Fallout 3 GOTY', 'enhanced', 3, '2009'),
            (5, 30, 'Fallout 3 Demo', 'demo', 3, '2008'),
            (6, 40, 'Halo', 'version', NULL, '2001'),
            (7, 50, 'Halo Anniversary', 'version', NULL, '2011');
        INSERT INTO game_relations VALUES
            (20, 10, 'remaster_of', 'auto'),
            (50, 40, 'remaster_of', 'manual');
        INSERT INTO match_decisions VALUES (5, 3, 'demo_of');
        """
    )
    return conn


def test_what_the_linker_set_alone_is_rechecked() -> None:
    """An automatic relation between games, and a role in a game, until a
    label settles it; the operator's own (manual) relation is not asked."""
    assert to_recheck(_db()) == [(2, 1, "remaster_of"), (4, 3, "enhanced_of")]
