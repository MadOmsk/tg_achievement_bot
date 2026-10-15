-- Where an achievement's group came from (#147; owner, 2026-10-15):
-- `platform` — the platform said so (PSN's groups, Xbox's `groupIds`) —, or
-- `derived` — worked out by us where the platform says nothing (an Xbox 360
-- list: its ids and gamerscore, `xbox.models.x360_groups`), provisional: a
-- group the platform gives later replaces it. NULL with no group.
ALTER TABLE title_achievements ADD COLUMN group_source TEXT;
ALTER TABLE seen_achievements ADD COLUMN group_source TEXT;

UPDATE title_achievements SET group_source =
    CASE WHEN platform = 'xbox_360' THEN 'derived' ELSE 'platform' END
WHERE trophy_group_id IS NOT NULL AND trophy_group_id <> 'main_game';

UPDATE seen_achievements SET group_source =
    CASE WHEN platform = 'xbox_360' THEN 'derived' ELSE 'platform' END
WHERE trophy_group_id IS NOT NULL AND trophy_group_id <> 'main_game';
