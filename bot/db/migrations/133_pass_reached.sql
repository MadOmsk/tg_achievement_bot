-- The season pass's levels a person reached, per month (owner, 2026-10-28):
-- a level is told once a month, when the points first reach it.
CREATE TABLE IF NOT EXISTS pass_reached (
    person_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id    INTEGER NOT NULL REFERENCES pass_items(item_id) ON DELETE CASCADE,
    month      TEXT NOT NULL,
    reached_at TEXT NOT NULL,
    PRIMARY KEY (person_id, item_id, month)
);
