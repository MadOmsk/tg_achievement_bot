-- `title_groups` — the base game plus one row per DLC, for the second line of
-- a PSN notification (#46, owner decision: name the group a trophy came from
-- and how far through it that person is).
--
-- A trophy already carries its own `trophy_group_id`, so the group is free;
-- what costs a request is the group's name and size, fetched once per game
-- and kept here forever, the same shape as steam_schema_cache.

CREATE TABLE IF NOT EXISTS title_groups (
    title_id   TEXT NOT NULL,
    group_id   TEXT NOT NULL,
    name       TEXT,
    total      INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (title_id, group_id)
);

-- And where a row's own group goes. Rebuild-and-swap like every other
-- add-a-column migration here; the GENERATED column and both indexes are
-- recreated with it. Only existing databases reach this file — a new one is
-- baselined from schema.sql, which already has the column.

PRAGMA foreign_keys = OFF;

CREATE TABLE seen_achievements_new (
    xuid            TEXT NOT NULL,
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
    trophy_group_id TEXT,
    trophy_type     TEXT,
    created_at      TEXT NOT NULL,
    account_platform TEXT GENERATED ALWAYS AS (
        CASE WHEN platform IN ('xbox_modern', 'xbox_360') THEN 'xbox' ELSE platform END
    ) STORED,
    PRIMARY KEY (platform, xuid, title_id, achievement_id),
    FOREIGN KEY (account_platform, xuid) REFERENCES accounts(platform, external_id)
);

INSERT INTO seen_achievements_new
    (xuid, title_id, achievement_id, name, description, icon_url, unlocked_at,
     gamerscore, rarity_percent, platform, is_backfill, is_secret, trophy_type, created_at)
SELECT xuid, title_id, achievement_id, name, description, icon_url, unlocked_at,
       gamerscore, rarity_percent, platform, is_backfill, is_secret, trophy_type, created_at
FROM seen_achievements;

DROP TABLE seen_achievements;
ALTER TABLE seen_achievements_new RENAME TO seen_achievements;

CREATE INDEX IF NOT EXISTS idx_seen_unlocked ON seen_achievements(xuid, unlocked_at DESC);
CREATE INDEX IF NOT EXISTS idx_seen_account ON seen_achievements(account_platform, xuid);

PRAGMA foreign_keys = ON;
