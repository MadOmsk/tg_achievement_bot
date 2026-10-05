-- What the model answered about one guide for one game: the fingerprint of what it
-- was asked (the guide's text and the game's achievements as the prompt shows them)
-- and the answer itself, the line ranges of each achievement's tip as JSON. A
-- re-read of a guide that has not changed costs nothing: its tips are cut again
-- from the stored answer, whether or not they were the ones kept.

CREATE TABLE IF NOT EXISTS title_guide_reads (
    title_id    TEXT    NOT NULL,
    guide_id    TEXT    NOT NULL,
    fingerprint TEXT    NOT NULL,
    answer      TEXT    NOT NULL,
    checked_at  TEXT    NOT NULL,
    PRIMARY KEY (title_id, guide_id)
);
