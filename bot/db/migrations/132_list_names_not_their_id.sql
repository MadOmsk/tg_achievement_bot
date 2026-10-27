-- A list named by its own id — a game whose name was never learned — has no
-- name (#147; owner, 2026-10-27: 389 stand-ins were named by a number, and an
-- adviser cannot look a number up). 119 took the English name in its place
-- once; the trigger of 117 still passed the id on as a name, and lists whose
-- English name came later kept it. From now on the id is no name anywhere.
DROP TRIGGER IF EXISTS list_name_reaches_its_stand_ins;
CREATE TRIGGER list_name_reaches_its_stand_ins
AFTER UPDATE OF name, name_ru, name_en ON achievement_list_connectors
BEGIN
    UPDATE versions SET
        name = CASE WHEN NEW.name IS NOT NULL AND NEW.name NOT IN ('', '?')
                         AND NEW.name <> NEW.title_id
                    THEN NEW.name ELSE COALESCE(NEW.name_en, name) END,
        name_ru = NEW.name_ru
    WHERE stand_in = 1 AND platform = NEW.platform AND title_id = NEW.title_id;
END;

UPDATE achievement_list_connectors SET name = name_en
WHERE name_en IS NOT NULL AND name_en <> '' AND name_en <> name
  AND (name IS NULL OR name = '' OR name = '?' OR name = title_id);
