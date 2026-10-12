-- A mode of a game is a role in it (#147; owner, 2026-10-12): Steam files a
-- launcher of one mode of another app as an app of type "advertising" (Call
-- of Duty: Black Ops II - Zombies holds the Zombies part of Black Ops II's
-- one list on 360), so it belongs to that game as a demo or a tool does, and
-- names the version it is a mode of. SQLite cannot change a CHECK in place:
-- the table is rebuilt, foreign keys off for the script as 071 and 078 do
-- (nothing points at game_versions; its own keys are copied as they were).

PRAGMA foreign_keys = OFF;

BEGIN;

CREATE TABLE game_versions_new (
    version_id    INTEGER PRIMARY KEY REFERENCES versions(version_id) ON DELETE CASCADE,
    game_id       INTEGER NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    role          TEXT NOT NULL,   -- version / demo / tool / mode
    of_version_id INTEGER REFERENCES versions(version_id) ON DELETE SET NULL,
    p             REAL,
    linked_at     TEXT NOT NULL,
    CHECK (of_version_id IS NULL OR role IN ('demo', 'tool', 'mode'))
);
INSERT INTO game_versions_new (version_id, game_id, role, of_version_id, p, linked_at)
SELECT version_id, game_id, role, of_version_id, p, linked_at FROM game_versions;
DROP TABLE game_versions;
ALTER TABLE game_versions_new RENAME TO game_versions;
CREATE INDEX IF NOT EXISTS idx_game_versions_game ON game_versions(game_id, role);

COMMIT;

PRAGMA foreign_keys = ON;
