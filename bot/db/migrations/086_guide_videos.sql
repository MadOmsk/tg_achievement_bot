-- Video guides from YouTube channels (owner, 2026-10-06): every video of a
-- guide channel, and the moments its description marks — a timeline line,
-- or the whole video when its title names one achievement. Matched to our
-- achievements when a page asks, by exact name within the game, so nothing
-- here points at a game or an achievement of ours.
CREATE TABLE IF NOT EXISTS guide_channels (
    channel_id      TEXT PRIMARY KEY,
    uploads_id      TEXT,
    -- Where the first pass through the channel's history stopped.
    backfill_token  TEXT,
    backfill_done   INTEGER NOT NULL DEFAULT 0,
    checked_at      TEXT
);

CREATE TABLE IF NOT EXISTS guide_videos (
    video_id      TEXT PRIMARY KEY,
    channel_id    TEXT NOT NULL,
    title         TEXT NOT NULL,
    -- The title's parts between " - ", each normalized, joined by " | ":
    -- a game is found by its name being the first part(s).
    title_key     TEXT NOT NULL,
    published_at  TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_guide_videos_key ON guide_videos (title_key);

CREATE TABLE IF NOT EXISTS guide_marks (
    video_id       TEXT NOT NULL REFERENCES guide_videos (video_id) ON DELETE CASCADE,
    -- What the moment is about, normalized as an achievement's name is.
    label          TEXT NOT NULL,
    start_seconds  INTEGER NOT NULL,
    -- "– PART 2" in a timeline; 0 when the line names no part.
    part           INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (video_id, label, start_seconds)
);
CREATE INDEX IF NOT EXISTS idx_guide_marks_label ON guide_marks (label);
