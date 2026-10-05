-- Adds achievements_visible (+ the timestamp of the check that produced it)
-- to platform_links (#5, /panel login-row rework, user request 2026-09-08).
-- NULL = never checked yet, 1 = the shared service credential could see
-- this account's achievements/trophies as of the last check, 0 = it could
-- not (the "My Profile" toggle can be public while a separate, narrower
-- privacy setting — Steam's own "Game details", PSN's own trophy
-- visibility — still blocks it). Set at connect time and refreshed by every
-- backfill and every admin/on-demand resync, so /panel's login row and the
-- admin card can show what the *last actual check* found, and when, rather
-- than nothing at all — the same "when was this last confirmed" role
-- Xbox's own login row already fills via token.last_refresh_at.
--
-- Rebuild-and-swap, not ALTER TABLE ADD COLUMN — same reasoning as every
-- other add-a-column migration here (002/006/010/012/017/018/020/024/025/
-- 026): schema.sql already creates platform_links with this column for a
-- brand-new database, and SQLite has no "add column only if it doesn't
-- already exist".

CREATE TABLE platform_links_new (
    tg_id        INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    platform     TEXT    NOT NULL CHECK (platform IN ('steam', 'psn')),
    external_id  TEXT    NOT NULL,
    display_name TEXT,
    linked_at    TEXT    NOT NULL,
    psn_trophy_level INTEGER,
    achievements_visible INTEGER,
    achievements_visible_checked_at TEXT,
    PRIMARY KEY (tg_id, platform)
);

-- Existing links start at NULL (unknown/never) — the next backfill or
-- resync (already scheduled/available for every one of them) fills both
-- columns in for real, rather than guessing from data that predates them.
INSERT INTO platform_links_new
    (tg_id, platform, external_id, display_name, linked_at, psn_trophy_level)
SELECT tg_id, platform, external_id, display_name, linked_at, psn_trophy_level
FROM platform_links;

DROP TABLE platform_links;
ALTER TABLE platform_links_new RENAME TO platform_links;
