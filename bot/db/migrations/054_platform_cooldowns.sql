-- Platform cooldowns for anti-abuse protection on account resets/re-links.
-- Issue: prevent repeated delete and recreate cycles that cause excessive backfill load.

CREATE TABLE IF NOT EXISTS platform_cooldowns (
    tg_id          INTEGER NOT NULL,
    platform       TEXT NOT NULL,
    external_id    TEXT,
    reset_count    INTEGER NOT NULL DEFAULT 1,
    last_reset_at  TEXT NOT NULL,
    PRIMARY KEY (tg_id, platform)
);

CREATE INDEX IF NOT EXISTS idx_platform_cooldowns_ext
    ON platform_cooldowns(platform, external_id);
