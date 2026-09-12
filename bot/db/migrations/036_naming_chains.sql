-- The two fields the naming chains needed and nobody was storing (#51,
-- 2026-09-12 user request). See CLAUDE.md, "Naming people and accounts".
--
-- `users.gamertag_modern`: Xbox's own ModernGamertag, the first step of the
-- Xbox chain. It has always been in the profile response the bot already
-- reads for gamerscore — alongside Gamertag, ModernGamertagSuffix and
-- UniqueModernGamertag — and was parsed out and thrown away every time.
-- `gamertag` keeps meaning the classic one: it is the lookup-ish display
-- cache every existing path uses, and the only form account.xbox.com's own
-- profile search accepts.
--
-- `platform_links.secondary_name`: the middle step of whichever platform the
-- row belongs to — Steam's vanity name (the `xxx` in /id/xxx, absent when
-- the person never set a custom URL) and PSN's previous online ID (what an
-- account was called before a rename). One column rather than two because
-- both answer the same question in their own chain, and a row is never both
-- platforms at once.
--
-- Rebuild-and-swap, not ALTER TABLE ADD COLUMN — same reasoning as every
-- other add-a-column migration here: schema.sql already creates these tables
-- with the columns for a brand-new database, and SQLite has no "add column
-- only if it doesn't already exist". Existing rows get NULL and fill
-- themselves in on the next refresh, which now keeps them current instead of
-- writing them once at connect and never again.
--
-- users is referenced by ON DELETE CASCADE from most of the schema, so the
-- swap runs with foreign keys off (they are re-enabled per connection by
-- Database.connect anyway) — otherwise dropping it would cascade every child
-- row away before the rename puts it back.

PRAGMA foreign_keys = OFF;

CREATE TABLE users_new (
    tg_id           INTEGER PRIMARY KEY,
    username        TEXT,
    first_name      TEXT,
    last_name       TEXT,
    xuid            TEXT UNIQUE,
    gamertag        TEXT,
    gamertag_modern TEXT,
    gamerscore      INTEGER,
    is_excluded     INTEGER NOT NULL DEFAULT 0,
    excluded_by     INTEGER,
    excluded_at     TEXT,
    last_online_at  TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

INSERT INTO users_new
    (tg_id, username, first_name, last_name, xuid, gamertag, gamerscore,
     is_excluded, excluded_by, excluded_at, last_online_at, created_at, updated_at)
SELECT tg_id, username, first_name, last_name, xuid, gamertag, gamerscore,
       is_excluded, excluded_by, excluded_at, last_online_at, created_at, updated_at
FROM users;

DROP TABLE users;
ALTER TABLE users_new RENAME TO users;

CREATE TABLE platform_links_new (
    tg_id        INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    platform     TEXT    NOT NULL CHECK (platform IN ('steam', 'psn')),
    external_id  TEXT    NOT NULL,
    display_name TEXT,
    secondary_name TEXT,
    linked_at    TEXT    NOT NULL,
    psn_trophy_level INTEGER,
    achievements_visible INTEGER,
    achievements_visible_checked_at TEXT,
    PRIMARY KEY (tg_id, platform)
);

INSERT INTO platform_links_new
    (tg_id, platform, external_id, display_name, linked_at, psn_trophy_level,
     achievements_visible, achievements_visible_checked_at)
SELECT tg_id, platform, external_id, display_name, linked_at, psn_trophy_level,
       achievements_visible, achievements_visible_checked_at
FROM platform_links;

DROP TABLE platform_links;
ALTER TABLE platform_links_new RENAME TO platform_links;

PRAGMA foreign_keys = ON;
