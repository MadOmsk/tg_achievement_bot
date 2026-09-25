-- A catalog refresh stored whatever the platform answered to a Russian request
-- under description_ru — its English when it has no Russian, sometimes a
-- placeholder ("<Translated text>", "TRP012D") — and readers took it for a
-- translation: Well Dweller's achievements published in English on
-- 2026-09-25 (#127). A Russian side has to read as Russian (owner): Cyrillic,
-- or no letters at all. What does not is dropped, and the translator fills it
-- in later; until then every reader falls back to the English, which is what
-- it showed anyway. A 'native' row that fails the test is re-queued; an 'llm'
-- one is the translator's own answer and stays.
UPDATE title_achievements
SET description_ru = NULL,
    description_source = CASE WHEN description_source = 'native' THEN NULL
                              ELSE description_source END
WHERE description_ru IS NOT NULL
  AND (description_source IS NULL OR description_source = 'native')
  AND description_ru NOT GLOB '*[А-яЁё]*'
  -- has a letter of any script: something besides digits, spaces, punctuation
  AND description_ru GLOB '*[^0-9 .,!?%:;()+/-]*';
