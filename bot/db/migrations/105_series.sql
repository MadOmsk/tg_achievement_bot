-- Game series (#147; owner, 2026-10-12): a series is an entity of its own,
-- and a game may be in several (a crossover: Street Fighter X Tekken is in
-- both). The linker proposes memberships (`auto`, with a probability and
-- how the game got there); the operator's (`manual`) and the advisers'
-- (`advisers`) answers are never overwritten, and `member = 0` says a game
-- is not in that series, so it is never proposed again. A series keeps its
-- id through rebuilds by its anchor game, as a game does by its anchor
-- version; a merged one keeps resolving to the series it went into.
CREATE TABLE IF NOT EXISTS series (
    series_id      INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    name_ru        TEXT,
    name_source    TEXT NOT NULL DEFAULT 'auto',
    anchor_game_id INTEGER UNIQUE REFERENCES games(game_id) ON DELETE SET NULL,
    merged_into    INTEGER REFERENCES series(series_id),
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS game_series (
    game_id    INTEGER NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    series_id  INTEGER NOT NULL REFERENCES series(series_id) ON DELETE CASCADE,
    source     TEXT NOT NULL,
    member     INTEGER NOT NULL DEFAULT 1,
    p          REAL,
    reason     TEXT,
    decided_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (game_id, series_id)
);
CREATE INDEX IF NOT EXISTS idx_game_series_series ON game_series(series_id);
