-- Separate the bot's users from the platform accounts they link (#52,
-- 2026-09-12 design, agreed with the project owner). The bug underneath is
-- #29: achievement history was keyed by the *person*, so swapping one
-- account for another on the same platform silently merged the two — and,
-- worse, kept dropping the new account's genuinely new unlocks forever,
-- because title_id/achievement_id are not account-specific and
-- INSERT OR IGNORE saw them as already seen.
--
-- Three moves, in order:
--   1. `accounts`      — one row per platform account, owner-independent.
--   2. `account_links` — who has it now, who had it before; nothing deleted.
--   3. `seen_achievements` re-keyed to the account that earned the row.
--
-- Xbox is one account and one platform here: both generations bind as a pair
-- and display as one everywhere (owner decision). seen_achievements.platform
-- keeps the finer xbox_modern/xbox_360 distinction that the achievement
-- contract, the missing rarity data and the box-art substitution all still
-- need; `account_platform` is GENERATED from it, so the two cannot drift and
-- none of the ~60 places branching on the generation had to change.
--
-- Foreign keys are off for the swap: seen_achievements is dropped and
-- rebuilt, and every child of `users` would otherwise be at the mercy of a
-- cascade. Database.connect turns them back on per connection.
--
-- Every statement here has to work on a **brand-new** database as well as on
-- an upgraded one: _apply_schema() runs schema.sql in full on every startup,
-- before migrations, and migrations then run unconditionally. So schema.sql
-- has already created `accounts`/`account_links` and the new-shape
-- `seen_achievements` by the time this file executes on a fresh database.
-- Hence IF NOT EXISTS throughout, hence `platform_links` being recreated
-- empty below before being read, and hence `xuid` keeping its name: renaming
-- it would leave this file selecting a column that a fresh database does not
-- have. (It has been the generic per-platform external id since M-Steam-2 —
-- a SteamID64 or a PSN account_id on non-Xbox rows — the name is just older
-- than the meaning.)

PRAGMA foreign_keys = OFF;

-- 1 ------------------------------------------------------------- accounts

CREATE TABLE IF NOT EXISTS accounts (
    platform     TEXT NOT NULL CHECK (platform IN ('xbox', 'steam', 'psn')),
    external_id  TEXT NOT NULL,
    display_name TEXT,
    secondary_name TEXT,
    gamerscore   INTEGER,
    psn_trophy_level INTEGER,
    achievements_visible INTEGER,
    achievements_visible_checked_at TEXT,
    first_seen_at TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (platform, external_id)
);

-- Xbox comes from `users` itself, the only platform that ever lived there.
-- `gamertag_modern` is the modern gamertag (#51's first chain step) and
-- `gamertag` the classic one, which is what the profile link is built from —
-- so they map to display_name/secondary_name in that order.
INSERT INTO accounts
    (platform, external_id, display_name, secondary_name, gamerscore,
     first_seen_at, updated_at)
SELECT 'xbox', u.xuid, COALESCE(u.gamertag_modern, u.gamertag), u.gamertag,
       u.gamerscore, u.created_at, u.updated_at
FROM users u
WHERE u.xuid IS NOT NULL;

-- Recreated empty when it is already gone (a fresh database, where
-- schema.sql never had it) purely so the SELECT below has a table to read.
CREATE TABLE IF NOT EXISTS platform_links (
    tg_id        INTEGER NOT NULL,
    platform     TEXT    NOT NULL,
    external_id  TEXT    NOT NULL,
    display_name TEXT,
    secondary_name TEXT,
    linked_at    TEXT    NOT NULL,
    psn_trophy_level INTEGER,
    achievements_visible INTEGER,
    achievements_visible_checked_at TEXT,
    PRIMARY KEY (tg_id, platform)
);

INSERT INTO accounts
    (platform, external_id, display_name, secondary_name, psn_trophy_level,
     achievements_visible, achievements_visible_checked_at, first_seen_at, updated_at)
SELECT pl.platform, pl.external_id, pl.display_name, pl.secondary_name,
       pl.psn_trophy_level, pl.achievements_visible,
       pl.achievements_visible_checked_at, pl.linked_at, pl.linked_at
FROM platform_links pl;

-- 2 -------------------------------------------------------- account_links

CREATE TABLE IF NOT EXISTS account_links (
    tg_id       INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    platform    TEXT NOT NULL,
    external_id TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    linked_at   TEXT NOT NULL,
    unlinked_at TEXT,
    PRIMARY KEY (tg_id, platform, external_id),
    FOREIGN KEY (platform, external_id) REFERENCES accounts(platform, external_id)
);

INSERT INTO account_links (tg_id, platform, external_id, is_active, linked_at)
SELECT u.tg_id, 'xbox', u.xuid, 1, u.created_at FROM users u WHERE u.xuid IS NOT NULL;

INSERT INTO account_links (tg_id, platform, external_id, is_active, linked_at)
SELECT pl.tg_id, pl.platform, pl.external_id, 1, pl.linked_at FROM platform_links pl;

CREATE UNIQUE INDEX IF NOT EXISTS idx_links_one_active_per_platform
    ON account_links(tg_id, platform) WHERE is_active = 1;
CREATE UNIQUE INDEX IF NOT EXISTS idx_links_one_owner
    ON account_links(platform, external_id) WHERE is_active = 1;

DROP TABLE platform_links;

-- 3 ---------------------------------------------------- seen_achievements

CREATE TABLE seen_achievements_new (
    xuid            TEXT NOT NULL,   -- the generic external id; see the header
    title_id        TEXT NOT NULL,
    achievement_id  TEXT NOT NULL,
    name            TEXT,
    description     TEXT,
    icon_url        TEXT,
    unlocked_at     TEXT,
    gamerscore      INTEGER,
    rarity_percent  REAL,
    platform        TEXT NOT NULL DEFAULT 'xbox_modern'
                    CHECK (platform IN ('xbox_modern', 'xbox_360', 'steam', 'psn')),
    is_backfill     INTEGER NOT NULL DEFAULT 0,
    is_secret       INTEGER NOT NULL DEFAULT 0,
    trophy_type     TEXT,
    created_at      TEXT NOT NULL,
    account_platform TEXT GENERATED ALWAYS AS (
        CASE WHEN platform IN ('xbox_modern', 'xbox_360') THEN 'xbox' ELSE platform END
    ) STORED,
    PRIMARY KEY (platform, xuid, title_id, achievement_id),
    FOREIGN KEY (account_platform, xuid) REFERENCES accounts(platform, external_id)
);

-- Rows land on their own account, unchanged. The old `tg_id` is dropped with
-- the table: who is *currently* linked is account_links' answer now, and a
-- copy on every row could only go stale. A plain INSERT on purpose — if two
-- different people somehow held rows for the same account, the new key would
-- collide and this fails loudly rather than merging them silently, which is
-- the very failure this migration exists to end.
INSERT INTO seen_achievements_new
    (xuid, title_id, achievement_id, name, description, icon_url, unlocked_at,
     gamerscore, rarity_percent, platform, is_backfill, is_secret, trophy_type, created_at)
SELECT xuid, title_id, achievement_id, name, description, icon_url, unlocked_at,
       gamerscore, rarity_percent, platform, is_backfill, is_secret, trophy_type, created_at
FROM seen_achievements;

DROP TABLE seen_achievements;
ALTER TABLE seen_achievements_new RENAME TO seen_achievements;

-- Both live here rather than in schema.sql: that file runs before any
-- migration, so an index naming `account_platform` would crash startup on a
-- database that has not reached this migration yet. Same reasoning the old
-- idx_seen_tg_unlocked carried, and the same fix migration 011 used.
CREATE INDEX IF NOT EXISTS idx_seen_unlocked ON seen_achievements(xuid, unlocked_at DESC);
CREATE INDEX IF NOT EXISTS idx_seen_account ON seen_achievements(account_platform, xuid);

PRAGMA foreign_keys = ON;
