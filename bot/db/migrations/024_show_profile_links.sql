-- Adds show_profile_links to user_settings — whether other people's /stats
-- and /who cards get a clickable profile link in this person's own
-- nickname line (Follow-up 2026-09-06). Default off: a person's platform
-- account is visible only to whoever the bot already tells, opting in is
-- explicit. The admin can flip what a brand-new person starts with via
-- app_settings['default_show_profile_links'] (repo.py's ensure_user, same
-- pattern as app_settings['default_rarity_mode'] in subscribe()) — this
-- column's own DEFAULT 0 only matters as a fallback for a row inserted
-- some other way.
--
-- Deliberately does NOT apply to /panel: that screen is only ever shown to
-- its own owner (panel.py refuses to render in a group at all), so it's not
-- "other people seeing your link" in the first place — always shows them
-- there regardless of this setting.
--
-- Rebuilt via a new table and swap, not ALTER TABLE ADD COLUMN — same
-- reasoning as migrations 002/006/010/012/017/018/020: schema.sql already
-- creates user_settings with this column for a brand-new database, and
-- SQLite has no "add column only if it doesn't already exist".

PRAGMA foreign_keys = OFF;

CREATE TABLE user_settings_new (
    tg_id               INTEGER PRIMARY KEY REFERENCES users(tg_id) ON DELETE CASCADE,
    muted_title_ids     TEXT    NOT NULL DEFAULT '[]',
    tz_offset_min       INTEGER,
    show_profile_links  INTEGER NOT NULL DEFAULT 0
);

INSERT INTO user_settings_new (tg_id, muted_title_ids, tz_offset_min)
SELECT tg_id, muted_title_ids, tz_offset_min FROM user_settings;

DROP TABLE user_settings;
ALTER TABLE user_settings_new RENAME TO user_settings;

PRAGMA foreign_keys = ON;
