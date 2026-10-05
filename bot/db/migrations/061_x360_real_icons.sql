-- Xbox 360 achievements stored before contract 1's imageId became an icon URL
-- carry the game's box art, or nothing (#118). The catalog (title_achievements)
-- holds the real icon for most of them; copy it onto the row. A row whose
-- catalog entry has no real icon keeps what it has.
UPDATE seen_achievements
SET icon_url = (
    SELECT ta.icon_url FROM title_achievements ta
    WHERE ta.platform = seen_achievements.platform
      AND ta.title_id = seen_achievements.title_id
      AND ta.achievement_id = seen_achievements.achievement_id
)
WHERE platform = 'xbox_360'
  AND (icon_url IS NULL OR icon_url NOT LIKE '%/ach/0/%')
  AND EXISTS (
      SELECT 1 FROM title_achievements ta
      WHERE ta.platform = seen_achievements.platform
        AND ta.title_id = seen_achievements.title_id
        AND ta.achievement_id = seen_achievements.achievement_id
        AND ta.icon_url LIKE '%/ach/0/%'
  );
