-- Games over versions (#147, stage 3): a game is the work (The Witcher 3);
-- its versions are store products on one console (091). A version belongs to
-- a game as a `version` (a port is just that, however late), an `edition`
-- (GOTY, Complete), a `remaster` (Gears of War → Ultimate → Reloaded), a part
-- of a `compilation` (one version, several games) or a `demo`. A remake is
-- another game, linked game → game (owner, 2026-10-09).
--
-- A link is `linked`, `review` (the matcher was not sure: the operator
-- decides) or `rejected` (decided: not this game), and says who decided it:
-- the matcher only ever rewrites its own (`auto`) rows, so a `manual`
-- decision — a rejection included — is never undone by a re-run.

CREATE TABLE IF NOT EXISTS games (
    game_id     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    name_ru     TEXT,
    year        INTEGER,
    name_source TEXT NOT NULL DEFAULT 'auto',   -- auto / manual
    merged_into INTEGER REFERENCES games(game_id),  -- an old id keeps resolving
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS version_games (
    version_id INTEGER NOT NULL REFERENCES versions(version_id) ON DELETE CASCADE,
    game_id    INTEGER NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,   -- version / edition / remaster / compilation / demo
    state      TEXT NOT NULL,   -- linked / review / rejected
    source     TEXT NOT NULL,   -- auto / manual
    score      REAL,
    reasons    TEXT,            -- JSON list: the signals that decided it
    decided_by TEXT,
    decided_at TEXT NOT NULL,
    PRIMARY KEY (version_id, game_id)
);
CREATE INDEX IF NOT EXISTS idx_version_games_game ON version_games(game_id, state);

CREATE TABLE IF NOT EXISTS game_relations (
    game_id    INTEGER NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    related_id INTEGER NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,   -- remake_of
    source     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (game_id, related_id, kind),
    CHECK (game_id <> related_id)
);
