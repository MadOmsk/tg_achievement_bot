-- Groups of achievements (#147; owner, 2026-10-15). Xbox and Steam have none:
-- every achievement is the main game's (`main_game`), ready for the Xbox
-- update that brings an analogue of the platinum. PSN keeps Sony's own
-- (`default`, `001`, ...), a NULL there still meaning "not fetched with its
-- groups yet". New rows get it from `constants.achievement_group`.
UPDATE seen_achievements SET trophy_group_id = 'main_game'
WHERE trophy_group_id IS NULL AND account_platform <> 'psn';

UPDATE title_achievements SET trophy_group_id = 'main_game'
WHERE trophy_group_id IS NULL AND platform <> 'psn';

-- A trophy group past the base game is a DLC of every version of its list,
-- stand-ins included (it was only made for lists a store proved).
INSERT INTO dlcs (version_id, trophy_group_id, name, name_ru, kind, updated_at)
SELECT v.version_id, g.group_id, g.name, g.name_ru, 'dlc', g.updated_at
FROM versions v JOIN title_groups g ON g.title_id = v.title_id
WHERE v.platform = 'psn' AND g.group_id <> 'default'
ON CONFLICT(version_id, trophy_group_id) WHERE trophy_group_id IS NOT NULL DO NOTHING;
