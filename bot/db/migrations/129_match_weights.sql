-- The games matcher's weights, fitted to the labels (#147): each fit is kept,
-- one is active, and the linker reads that one in place of the hand weights
-- in `game_match.WEIGHTS` (none active: the hand weights).
CREATE TABLE IF NOT EXISTS match_weights (
    weights_id   INTEGER PRIMARY KEY,
    weights      TEXT NOT NULL,     -- JSON: class -> sign -> weight
    gate_before  REAL,              -- the operator's labels, held out: right before the fit
    gate_after   REAL,              -- … and after it
    labels       INTEGER,           -- how many labels it was fitted on
    note         TEXT,
    created_at   TEXT NOT NULL,
    active       INTEGER NOT NULL DEFAULT 0
);
