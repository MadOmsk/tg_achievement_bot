-- A post keeps its time, not only its day (owner, 2026-10-06): the posts are
-- read again so `published_at` becomes `2026-10-05T14:32:00Z`. The older
-- day-only values still sort and compare right beside them.
UPDATE steam_apps SET patches_checked_at = NULL;
