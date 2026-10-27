-- A person's favorite games (owner, 2026-10-25): shown on their profile, and
-- their news read every hour. `game_id` names the game; `anchor_key` is its
-- anchor version as `store:product_id:console`, which survives a catalog
-- carried over from another database (`scripts/catalog_transfer.py`), where
-- game ids may differ — a favorite whose id is gone is found again by it.
CREATE TABLE IF NOT EXISTS favorite_games (
    person_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    game_id    INTEGER NOT NULL,
    anchor_key TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (person_id, game_id)
);
CREATE INDEX IF NOT EXISTS idx_favorite_games_game ON favorite_games (game_id);
