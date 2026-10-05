-- How rare an achievement is, as a fact about the achievement rather than
-- about the person who unlocked it (owner, 2026-09-17).
--
-- `seen_achievements.rarity_percent` is written once per person per
-- achievement and never updated (every insert is INSERT OR IGNORE, and
-- nothing in the project UPDATEs that table), so it is really "the
-- percentage the platform happened to report the first time somebody here
-- earned this". On Xbox most rows do not carry one at all: rarity arrives
-- only on contract 4, the per-title call a live poll makes, while backfill
-- uses contract 2 for the whole library — 51 rows against 14866 on the test
-- bot, split exactly along that line.
--
-- Shared, like achievement_name_cache and achievement_description_cache
-- beside it, and keyed the same way. `checked_at` is when it was last
-- fetched, not an expiry: a percentage drifts as more people play, but a
-- year-old figure is worth more than none at all (owner), so nothing here is
-- ever hidden for being stale — it is only a queue order for refreshing.
CREATE TABLE IF NOT EXISTS achievement_rarity_cache (
    platform        TEXT NOT NULL,   -- xbox_modern / xbox_360 / steam / psn
    title_id        TEXT NOT NULL,
    achievement_id  TEXT NOT NULL,
    rarity_percent  REAL NOT NULL,   -- share of players who earned it
    checked_at      TEXT NOT NULL,
    PRIMARY KEY (platform, title_id, achievement_id)
);

-- The backfill walker's own question: "which title have I not looked at,
-- longest ago" (scripts/backfill_rarity.py, poller/rarity_backfill.py).
CREATE INDEX IF NOT EXISTS idx_rarity_cache_title
    ON achievement_rarity_cache(platform, title_id, checked_at);
