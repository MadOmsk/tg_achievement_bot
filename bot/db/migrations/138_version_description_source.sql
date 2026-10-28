-- A version's Russian description says where it came from (owner,
-- 2026-10-28; #230), as an achievement's does: `native` is the store's own
-- Russian, `llm` our translation of the English text `description_ru_of`
-- names (a hash), so a changed English text is translated again. Rows from
-- before stay NULL and are judged by their text (Cyrillic, not the English).
ALTER TABLE versions ADD COLUMN description_source TEXT;
ALTER TABLE versions ADD COLUMN description_ru_of TEXT;
