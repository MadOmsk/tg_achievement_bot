-- A catalog refresh stored the platform's English under description_ru when
-- the platform had no Russian, and readers took it for a translation: Well
-- Dweller's achievements published in English on 2026-09-25 (#127). Such a
-- copy is no Russian side; the translator fills it in later, and until then
-- every reader falls back to the English, which is what they showed anyway.
UPDATE title_achievements
SET description_ru = NULL
WHERE description_source IS NULL
  AND description_ru IS NOT NULL
  AND description_ru = description_en;
