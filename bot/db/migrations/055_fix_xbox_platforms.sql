-- Fix erroneous XboxOne platform seeding from migration 052 (#79 follow-up).
-- Migration 052 blindly updated all modern Xbox titles to '["XboxOne"]',
-- causing PC games (e.g. Microsoft Solitaire Collection), Series X|S games,
-- and cross-gen games to display as XOne.

-- 1. Reset blind '["XboxOne"]' entries to NULL for modern Xbox titles.
UPDATE titles
SET platforms = NULL
WHERE platform IN ('xbox_modern', 'modern') AND platforms = '["XboxOne"]';

-- 2. Populate platforms from seen_achievements.device where real devices were recorded.
UPDATE titles
SET platforms = (
    SELECT json_group_array(DISTINCT s.device)
    FROM seen_achievements s
    WHERE s.title_id = titles.title_id AND s.device IS NOT NULL
)
WHERE platform IN ('xbox_modern', 'modern')
  AND platforms IS NULL
  AND EXISTS (
      SELECT 1 FROM seen_achievements s
      WHERE s.title_id = titles.title_id AND s.device IS NOT NULL
  );
