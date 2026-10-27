-- The season pass (owner, 2026-10-27): the themes a person claimed. A claim
-- is checked against the month's points on the server and kept for good;
-- `month` is the season it was claimed in.
CREATE TABLE IF NOT EXISTS pass_claims (
    person_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    palette    TEXT NOT NULL,
    month      TEXT NOT NULL,
    claimed_at TEXT NOT NULL,
    PRIMARY KEY (person_id, palette)
);
