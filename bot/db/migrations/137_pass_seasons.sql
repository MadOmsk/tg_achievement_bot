-- A month's pass has a name of its own, its theme ("Хэллоуин"; owner,
-- 2026-10-28). Edited as a draft like the levels: `draft` 1 holds
-- `draft_title` (NULL to clear it) until the month's publish.
CREATE TABLE IF NOT EXISTS pass_seasons (
    month       TEXT PRIMARY KEY,
    title       TEXT,
    draft       INTEGER NOT NULL DEFAULT 0,
    draft_title TEXT
);
