-- The season's start told at noon on the 1st: who has opened a month's pass, and
-- who has been told of its start, so nobody hears of it twice.
CREATE TABLE IF NOT EXISTS pass_seen (
    person_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    month     TEXT NOT NULL,
    seen_at   TEXT NOT NULL,
    PRIMARY KEY (person_id, month)
);

CREATE TABLE IF NOT EXISTS season_notified (
    person_id   BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    month       TEXT NOT NULL,
    notified_at TEXT NOT NULL,
    PRIMARY KEY (person_id, month)
);
