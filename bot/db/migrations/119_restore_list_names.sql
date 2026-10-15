-- A list whose name was never stored keeps its id (or "?") in `name` while
-- `name_en` holds the real one (#147; 2026-10-15): 187 of the 519 lists with no
-- name on the copy of production. The English name takes its place; the
-- trigger of 117 names the stand-in versions of those lists after it.
UPDATE achievement_list_connectors SET name = name_en
WHERE name_en IS NOT NULL AND name_en <> '' AND name_en <> name
  AND (name IS NULL OR name = '' OR name = '?' OR name = title_id);
