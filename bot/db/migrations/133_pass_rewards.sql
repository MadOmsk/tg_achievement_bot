-- The season pass's levels (owner, 2026-10-27): each a theme of the app or a
-- prize of the super-admin's (a game of ours, or a code for something else),
-- all edited by the super-admin in the Mini App. An edit is a draft until one
-- "publish": a new level is `draft`, a change to one already shown waits in
-- `pending` (JSON; `{"remove": true}` to take it down). Nothing anybody has
-- claimed is changed. A prize's codes: one to a person, taken once
-- `claimed_at` is set (`person_id` goes NULL with a deleted person, the code
-- staying taken).
CREATE TABLE IF NOT EXISTS pass_items (
    item_id      INTEGER PRIMARY KEY,
    kind         TEXT NOT NULL,             -- theme / game / code
    palette      TEXT,                      -- a theme's
    tier         TEXT,                      -- a theme's look: common / rare / legendary / mythic
    title        TEXT,
    description  TEXT,
    points       INTEGER NOT NULL DEFAULT 0,
    image_path   TEXT,
    game_id      INTEGER,
    state        TEXT NOT NULL DEFAULT 'draft',  -- draft / live / removed
    pending      TEXT,
    created_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at   TEXT NOT NULL,
    published_at TEXT,
    removed_at   TEXT
);
CREATE TABLE IF NOT EXISTS pass_item_codes (
    code_id    INTEGER PRIMARY KEY,
    item_id    INTEGER NOT NULL REFERENCES pass_items(item_id) ON DELETE CASCADE,
    code       TEXT NOT NULL,
    person_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    claimed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_pass_item_codes_item ON pass_item_codes (item_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pass_item_codes_one_each
    ON pass_item_codes (item_id, person_id) WHERE person_id IS NOT NULL;
