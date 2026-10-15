-- `titles` was read as a list of games; it is the link between a game's
-- versions and an achievement list on one platform, plus that list's own facts
-- (#147; owner, 2026-10-15). Renamed so nobody takes a row of it for a game.
-- schema.sql ran before this and made the new table empty: it goes (with its
-- trigger), the old one takes its name (nothing points at `titles` with a
-- foreign key). A stand-in version's name follows its list's from now on.
DROP TABLE achievement_list_connectors;
ALTER TABLE titles RENAME TO achievement_list_connectors;

CREATE TRIGGER IF NOT EXISTS list_name_reaches_its_stand_ins
AFTER UPDATE OF name, name_ru, name_en ON achievement_list_connectors
BEGIN
    UPDATE versions SET
        name = CASE WHEN NEW.name IS NOT NULL AND NEW.name NOT IN ('', '?')
                    THEN NEW.name ELSE COALESCE(NEW.name_en, name) END,
        name_ru = NEW.name_ru
    WHERE stand_in = 1 AND platform = NEW.platform AND title_id = NEW.title_id;
END;
