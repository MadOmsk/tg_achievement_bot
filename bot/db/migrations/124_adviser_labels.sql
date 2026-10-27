-- The advisers' answers to a run, kept as labels (#147; owner, 2026-10-17):
-- a decision two or three of them gave alike (`source`: advisers:3/3 or
-- advisers:2/3, weighed 0.8 / 0.4 by `match_fit`), with what each said, per
-- run of question files. What the database has a place for is also written
-- there (`services/advice_import.apply`); the rest waits here for its step.
CREATE TABLE IF NOT EXISTS adviser_labels (
    run        TEXT NOT NULL,
    question   TEXT NOT NULL,   -- G:12, R:12:34, S:7, …
    decision   TEXT NOT NULL,   -- v101.belongs, relation, g12, …
    value      TEXT NOT NULL,
    source     TEXT NOT NULL,
    said       TEXT NOT NULL,   -- JSON {adviser: value}
    created_at TEXT NOT NULL,
    PRIMARY KEY (run, question, decision)
);
