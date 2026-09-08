-- PSN presence (issue #1's "/online" piece, 2026-09-08). Separate table,
-- not a reuse of presence_state (Xbox, keyed by xuid) or steam_presence_state
-- (Steam, its own persona_state/gameid shape) — PSN gets its own poller with
-- no achievement-poll debounce at all: unlike Xbox/Steam, trophy sync here
-- has never been driven by presence (CLAUDE.md's PSN section explains why —
-- trophies may only sync to Sony's servers when a player opens trophy data
-- on the console, not at the moment of unlock), and that design doesn't
-- change just because presence is now tracked too. This table exists purely
-- so /online has something real to show instead of "нет данных" for every
-- PSN-only person.
CREATE TABLE IF NOT EXISTS psn_presence_state (
    account_id TEXT PRIMARY KEY,
    state      TEXT,     -- Online / Offline, same vocabulary as presence_state
    title_id   TEXT,     -- npTitleId
    title_name TEXT,
    changed_at TEXT,     -- when title_id or state last changed
    updated_at TEXT
);
