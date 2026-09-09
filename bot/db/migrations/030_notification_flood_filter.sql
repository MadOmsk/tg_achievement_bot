-- Anti-flood filter for achievement notifications (2026-09-09 user
-- request): chat_settings gets two new per-chat, admin-configurable knobs
-- (flood_limit, flood_window_minutes — see schema.sql's own comment on
-- them), and a new notification_throttle table tracks each (person, chat)
-- currently inside a counting or throttled window. See poller/flood_flush.py
-- and services/achievements.py::passes_filters' caller in
-- poller/publisher.py for the actual mechanism.
--
-- Rebuild-and-swap for chat_settings, not ALTER TABLE ADD COLUMN — same
-- reasoning as every other add-a-column migration here (002/006/010/012/
-- 017/018/020/024/025/026/028): schema.sql already creates chat_settings
-- with these columns for a brand-new database, and SQLite has no "add
-- column only if it doesn't already exist". Every existing chat starts at
-- the same defaults as a fresh one (3 achievements / 60 minutes) — the
-- filter is on everywhere from the moment this ships, not opt-in per chat.

CREATE TABLE chat_settings_new (
    chat_id                INTEGER PRIMARY KEY REFERENCES chats(chat_id) ON DELETE CASCADE,
    min_gamerscore          INTEGER NOT NULL DEFAULT 0,
    daily_summary           INTEGER NOT NULL DEFAULT 1,
    muted_title_ids         TEXT    NOT NULL DEFAULT '[]',
    rare_threshold_percent  REAL    NOT NULL DEFAULT 10,
    daily_summary_time      TEXT    NOT NULL DEFAULT '20:00',
    tz_offset_min            INTEGER NOT NULL DEFAULT 180,
    flood_limit              INTEGER NOT NULL DEFAULT 3,
    flood_window_minutes     INTEGER NOT NULL DEFAULT 60
);

INSERT INTO chat_settings_new
    (chat_id, min_gamerscore, daily_summary, muted_title_ids, rare_threshold_percent,
     daily_summary_time, tz_offset_min)
SELECT chat_id, min_gamerscore, daily_summary, muted_title_ids, rare_threshold_percent,
       daily_summary_time, tz_offset_min
FROM chat_settings;

DROP TABLE chat_settings;
ALTER TABLE chat_settings_new RENAME TO chat_settings;

CREATE TABLE IF NOT EXISTS notification_throttle (
    tg_id             INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    chat_id           INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    window_started_at TEXT    NOT NULL,
    count_in_window   INTEGER NOT NULL DEFAULT 0,
    throttled         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tg_id, chat_id)
);
