-- What was asked of the model about one guide for one game (the fingerprint of
-- the guide's text and the game's achievements) and how many tips came of it, so a
-- re-read of a guide that has not changed — or one that gave nothing — costs
-- nothing: the model is asked again only when the guide or the list changed.

CREATE TABLE IF NOT EXISTS title_guide_reads (
    title_id    TEXT    NOT NULL,
    guide_id    TEXT    NOT NULL,
    fingerprint TEXT    NOT NULL,
    found       INTEGER NOT NULL,
    checked_at  TEXT    NOT NULL,
    PRIMARY KEY (title_id, guide_id)
);
