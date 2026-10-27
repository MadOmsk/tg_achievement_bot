-- The octopus's queue (#215; owner, 2026-10-24): the games to assemble, each
-- by an entry that leads to it — `list:psn:NPWR…`, `product:steam:620`,
-- `achievement:…`, `dlc:…`, `hltb:…`, `name:…`, `game:12` — never only a
-- game id, which a relink may change.
CREATE TABLE IF NOT EXISTS octopus_queue (
    key        TEXT PRIMARY KEY,
    reason     TEXT,
    due_at     TEXT NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_octopus_queue_due ON octopus_queue(due_at);
