-- `achievement_description_cache.source` gets a third value: 'fallback' —
-- the platform gave us one language only (or the same text twice, which is
-- how a platform says "no translation exists") and nothing has translated it
-- yet. User request, 2026-09-13: with no Anthropic key configured the text
-- must still be stored and shown untranslated, not silently dropped.
--
-- Why a value rather than a NULL `description_ru` alone: "we have no Russian
-- for this" and "nobody has tried yet" look identical otherwise, and the
-- difference is exactly what decides whether a later pass should pay an LLM
-- for it. A `fallback` row is re-offered to the translator the moment a key
-- exists; a `native` or `llm` row never is.
--
-- Rebuild-and-swap, because the old CHECK constraint only allowed two values.

PRAGMA foreign_keys = OFF;

CREATE TABLE achievement_description_cache_new (
    platform         TEXT NOT NULL,
    title_id         TEXT NOT NULL,
    achievement_id   TEXT NOT NULL,
    description_ru   TEXT,
    description_en   TEXT,
    source           TEXT NOT NULL CHECK (source IN ('native', 'llm', 'fallback')),
    cached_at        TEXT NOT NULL,
    PRIMARY KEY (platform, title_id, achievement_id)
);

INSERT INTO achievement_description_cache_new
    (platform, title_id, achievement_id, description_ru, description_en, source, cached_at)
SELECT platform, title_id, achievement_id, description_ru, description_en, source, cached_at
FROM achievement_description_cache;

DROP TABLE achievement_description_cache;
ALTER TABLE achievement_description_cache_new RENAME TO achievement_description_cache;

PRAGMA foreign_keys = ON;
