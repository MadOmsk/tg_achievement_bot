-- Xbox achievements are grouped as Xbox groups them (#147; owner, 2026-10-15):
-- `base`, the list a game shipped with, or `non_base`, added later (a DLC, an
-- update) — contract 6's `groupIds`, and what a Mythic achievement counts.
-- The `main_game` 118 put on every Xbox row goes: it said nothing. The groups
-- come with the next read of each list (`TitleCatalogService`), and the rows
-- people earned take theirs from it.
UPDATE seen_achievements SET trophy_group_id = NULL
WHERE trophy_group_id = 'main_game' AND account_platform = 'xbox';

UPDATE title_achievements SET trophy_group_id = NULL
WHERE trophy_group_id = 'main_game' AND platform IN ('xbox_modern', 'xbox_360');
