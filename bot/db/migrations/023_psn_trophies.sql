-- Adds 'psn' to seen_achievements.platform's CHECK and a new trophy_type
-- column (bronze/silver/gold/platinum — no analogue on Xbox/Steam, M-PSN-1's
-- design notes), plus psn_title_progress for the trophy poller (M-PSN-2).
-- Same rebuild-and-swap as migration 011: SQLite can't ALTER a CHECK
-- constraint, so the table is recreated and the data copied across as-is
-- (every existing row already satisfies the new, wider CHECK — 'psn' is
-- additive, not a replacement for any existing value).

PRAGMA foreign_keys = OFF;

CREATE TABLE seen_achievements_new (
    tg_id           INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    xuid            TEXT NOT NULL,
    title_id        TEXT NOT NULL,
    achievement_id  TEXT NOT NULL,
    name            TEXT,
    description     TEXT,
    icon_url        TEXT,
    unlocked_at     TEXT,
    gamerscore      INTEGER,
    rarity_percent  REAL,
    platform        TEXT NOT NULL DEFAULT 'modern'
                    CHECK (platform IN ('modern', 'x360', 'steam', 'psn')),
    is_backfill     INTEGER NOT NULL DEFAULT 0,
    is_secret       INTEGER NOT NULL DEFAULT 0,
    trophy_type     TEXT,
    created_at      TEXT NOT NULL,
    PRIMARY KEY (tg_id, platform, title_id, achievement_id)
);

INSERT INTO seen_achievements_new
    (tg_id, xuid, title_id, achievement_id, name, description, icon_url, unlocked_at,
     gamerscore, rarity_percent, platform, is_backfill, is_secret, created_at)
SELECT
    tg_id, xuid, title_id, achievement_id, name, description, icon_url, unlocked_at,
    gamerscore, rarity_percent, platform, is_backfill, is_secret, created_at
FROM seen_achievements;

DROP TABLE seen_achievements;
ALTER TABLE seen_achievements_new RENAME TO seen_achievements;

CREATE INDEX IF NOT EXISTS idx_seen_unlocked ON seen_achievements(xuid, unlocked_at DESC);
CREATE INDEX IF NOT EXISTS idx_seen_tg_unlocked ON seen_achievements(tg_id, unlocked_at DESC);

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS psn_title_progress (
    account_id           TEXT NOT NULL,
    np_communication_id  TEXT NOT NULL,
    progress             INTEGER NOT NULL,
    updated_at           TEXT NOT NULL,
    PRIMARY KEY (account_id, np_communication_id)
);

CREATE TABLE IF NOT EXISTS psn_poll_state (
    account_id     TEXT PRIMARY KEY,
    last_polled_at TEXT NOT NULL
);
