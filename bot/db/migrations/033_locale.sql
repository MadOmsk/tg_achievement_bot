-- Multi-language support (#48): a locale per chat and a locale per person.
--
-- Two separate settings, not one, because Telegram has no way to show two
-- viewers of the same group message different text — a chat's own broadcasts
-- (achievement posts, /online, /recent, /summary, the group hub) need one
-- shared answer set by an admin, while DMs (/panel, /stats in a DM, personal
-- notifications) can be fully personal.
--
-- Both default to 'ru' and are deliberately NOT seeded from Telegram's own
-- language_code: plenty of this Russian-speaking community run Telegram
-- itself in English, and auto-switching them on deploy would be a silent
-- regression for every existing user. Explicit opt-in only.
--
-- Rebuild-and-swap for both tables, not ALTER TABLE ADD COLUMN — same
-- reasoning as every other add-a-column migration here (002/006/010/012/
-- 017/018/020/024/025/026/028/030): schema.sql already creates both tables
-- with the column for a brand-new database, and SQLite has no "add column
-- only if it doesn't already exist".

CREATE TABLE chat_settings_new (
    chat_id                INTEGER PRIMARY KEY REFERENCES chats(chat_id) ON DELETE CASCADE,
    min_gamerscore          INTEGER NOT NULL DEFAULT 0,
    daily_summary           INTEGER NOT NULL DEFAULT 1,
    muted_title_ids         TEXT    NOT NULL DEFAULT '[]',
    rare_threshold_percent  REAL    NOT NULL DEFAULT 10,
    daily_summary_time      TEXT    NOT NULL DEFAULT '20:00',
    tz_offset_min            INTEGER NOT NULL DEFAULT 180,
    flood_limit              INTEGER NOT NULL DEFAULT 3,
    flood_window_minutes     INTEGER NOT NULL DEFAULT 60,
    locale                   TEXT    NOT NULL DEFAULT 'ru'
);

INSERT INTO chat_settings_new
    (chat_id, min_gamerscore, daily_summary, muted_title_ids, rare_threshold_percent,
     daily_summary_time, tz_offset_min, flood_limit, flood_window_minutes)
SELECT chat_id, min_gamerscore, daily_summary, muted_title_ids, rare_threshold_percent,
       daily_summary_time, tz_offset_min, flood_limit, flood_window_minutes
FROM chat_settings;

DROP TABLE chat_settings;
ALTER TABLE chat_settings_new RENAME TO chat_settings;

CREATE TABLE user_settings_new (
    tg_id            INTEGER PRIMARY KEY REFERENCES users(tg_id) ON DELETE CASCADE,
    muted_title_ids  TEXT    NOT NULL DEFAULT '[]',
    tz_offset_min    INTEGER,
    show_profile_links INTEGER NOT NULL DEFAULT 0,
    locale           TEXT    NOT NULL DEFAULT 'ru'
);

INSERT INTO user_settings_new
    (tg_id, muted_title_ids, tz_offset_min, show_profile_links)
SELECT tg_id, muted_title_ids, tz_offset_min, show_profile_links
FROM user_settings;

DROP TABLE user_settings;
ALTER TABLE user_settings_new RENAME TO user_settings;
