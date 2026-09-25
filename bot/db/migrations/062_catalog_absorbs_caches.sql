-- One store for an achievement's names, descriptions and rarity: the catalog
-- (#119). The three caches predate it and were written and read by different
-- paths, so a fact one side learned was invisible to the other. Whatever they
-- hold moves into title_achievements, and they go.
--
-- Where both sides have a value the cache's wins: it is what every card,
-- digest and list read until now, the one every live poll refreshed, and the
-- one that went through the translator.

ALTER TABLE title_achievements ADD COLUMN description_source TEXT
    CHECK (description_source IN ('native', 'llm', 'fallback'));

-- Every row the catalog holds today was written by its own refresh; the rows
-- the caches bring in below are only facts about an achievement, not the
-- game's list, and stay 0.
ALTER TABLE title_achievements ADD COLUMN listed INTEGER NOT NULL DEFAULT 0;
UPDATE title_achievements SET listed = 1;

-- The WHERE also keeps SQLite from reading ON CONFLICT as a join clause.
INSERT INTO title_achievements
    (platform, title_id, achievement_id, description_ru, description_en,
     description_source, updated_at)
SELECT platform, title_id, achievement_id, description_ru, description_en, source, cached_at
FROM achievement_description_cache
WHERE platform IN ('xbox_modern', 'xbox_360', 'steam', 'psn')
ON CONFLICT(platform, title_id, achievement_id) DO UPDATE SET
    description_ru = excluded.description_ru,
    description_en = COALESCE(excluded.description_en, title_achievements.description_en),
    description_source = excluded.description_source;

INSERT INTO title_achievements
    (platform, title_id, achievement_id, name_ru, name_en, updated_at)
SELECT platform, title_id, achievement_id, name_ru, name_en, cached_at
FROM achievement_name_cache
WHERE platform IN ('xbox_modern', 'xbox_360', 'steam', 'psn')
ON CONFLICT(platform, title_id, achievement_id) DO UPDATE SET
    name_ru = COALESCE(excluded.name_ru, title_achievements.name_ru),
    name_en = COALESCE(excluded.name_en, title_achievements.name_en);

INSERT INTO title_achievements
    (platform, title_id, achievement_id, rarity_percent, updated_at)
SELECT platform, title_id, achievement_id, rarity_percent, checked_at
FROM achievement_rarity_cache
WHERE platform IN ('xbox_modern', 'xbox_360', 'steam', 'psn')
ON CONFLICT(platform, title_id, achievement_id) DO UPDATE SET
    rarity_percent = excluded.rarity_percent;

DROP TABLE achievement_description_cache;
DROP TABLE achievement_name_cache;
DROP INDEX IF EXISTS idx_rarity_cache_title;
DROP TABLE achievement_rarity_cache;
