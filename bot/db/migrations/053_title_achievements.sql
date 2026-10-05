-- Full game achievements catalog (`title_achievements`) and titles check timestamp
-- Issue #99, #80.

CREATE TABLE IF NOT EXISTS title_achievements (
    platform        TEXT NOT NULL CHECK (platform IN ('xbox_modern', 'xbox_360', 'steam', 'psn')),
    title_id        TEXT NOT NULL,
    achievement_id  TEXT NOT NULL,
    name_ru         TEXT,
    name_en         TEXT,
    description_ru  TEXT,
    description_en  TEXT,
    icon_url        TEXT,
    is_secret       INTEGER NOT NULL DEFAULT 0,
    gamerscore      INTEGER,
    trophy_type     TEXT,
    trophy_group_id TEXT,
    rarity_percent  REAL,
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (platform, title_id, achievement_id)
);

CREATE INDEX IF NOT EXISTS idx_title_achievements_title
    ON title_achievements(platform, title_id);

ALTER TABLE titles ADD COLUMN achievements_checked_at TEXT;

-- Backfill title_achievements from already seen achievements and existing bilingual/rarity caches
INSERT OR IGNORE INTO title_achievements (
    platform,
    title_id,
    achievement_id,
    name_ru,
    name_en,
    description_ru,
    description_en,
    icon_url,
    is_secret,
    gamerscore,
    trophy_type,
    trophy_group_id,
    rarity_percent,
    updated_at
)
SELECT
    s.platform,
    s.title_id,
    s.achievement_id,
    COALESCE(MAX(nc.name_ru), MAX(s.name)),
    MAX(nc.name_en),
    MAX(dc.description_ru),
    COALESCE(MAX(dc.description_en), MAX(s.description)),
    MAX(s.icon_url),
    MAX(s.is_secret),
    MAX(s.gamerscore),
    MAX(s.trophy_type),
    MAX(s.trophy_group_id),
    COALESCE(MAX(rc.rarity_percent), MAX(s.rarity_percent)),
    MAX(s.created_at)
FROM seen_achievements s
LEFT JOIN achievement_name_cache nc
    ON nc.platform = s.platform AND nc.title_id = s.title_id AND nc.achievement_id = s.achievement_id
LEFT JOIN achievement_description_cache dc
    ON dc.platform = s.platform AND dc.title_id = s.title_id AND dc.achievement_id = s.achievement_id
LEFT JOIN achievement_rarity_cache rc
    ON rc.platform = s.platform AND rc.title_id = s.title_id AND rc.achievement_id = s.achievement_id
GROUP BY s.platform, s.title_id, s.achievement_id;
