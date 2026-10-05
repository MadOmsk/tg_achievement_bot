-- Adds psn_trophy_level to platform_links — the account-wide PSN level
-- (Follow-up 2026-09-06, user request: show it in /stats next to the
-- achievement count). NULL until the poller caches it (poller/psn_fetcher.py:
-- once right after backfill, then again each time it finds new trophies —
-- level can only change when a trophy is earned, so there is no reason to
-- refresh it on every tick). Meaningless for Steam rows (no such concept
-- there), left NULL for them same as trophy_type on seen_achievements is
-- NULL for every non-PSN row.
--
-- Rebuilt via a new table and swap, not ALTER TABLE ADD COLUMN — same
-- reasoning as every other add-a-column migration in this project
-- (002/006/010/012/017/018/020/024): schema.sql already creates
-- platform_links with this column for a brand-new database, and SQLite has
-- no "add column only if it doesn't already exist".

PRAGMA foreign_keys = OFF;

CREATE TABLE platform_links_new (
    tg_id             INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    platform          TEXT    NOT NULL CHECK (platform IN ('steam', 'psn')),
    external_id       TEXT    NOT NULL,
    display_name      TEXT,
    linked_at         TEXT    NOT NULL,
    psn_trophy_level  INTEGER,
    PRIMARY KEY (tg_id, platform)
);

INSERT INTO platform_links_new (tg_id, platform, external_id, display_name, linked_at)
SELECT tg_id, platform, external_id, display_name, linked_at FROM platform_links;

DROP TABLE platform_links;
ALTER TABLE platform_links_new RENAME TO platform_links;

PRAGMA foreign_keys = ON;
