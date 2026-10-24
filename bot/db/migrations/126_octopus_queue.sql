-- The octopus's queue and the linker's dirty set (#215; owner, 2026-10-24).
-- The queue holds what to look for, by a stable key — `list:psn:NPWR…`,
-- `steam:123`, `hltb:45`, `name:…`, `game:12` — never only a game id, which a
-- relink may change; `hops` is how far from what was asked for, so the
-- search does not crawl a whole store. The dirty set is the versions the
-- octopus touched, for the linker to rebuild once per batch.
CREATE TABLE IF NOT EXISTS octopus_queue (
    key        TEXT PRIMARY KEY,
    hops       INTEGER NOT NULL DEFAULT 0,
    reason     TEXT,
    due_at     TEXT NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_octopus_queue_due ON octopus_queue(due_at, hops);
CREATE TABLE IF NOT EXISTS octopus_dirty (
    version_id INTEGER PRIMARY KEY,
    marked_at  TEXT NOT NULL
);
