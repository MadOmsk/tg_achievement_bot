-- Bilingual achievement/trophy description cache (2026-09-09 user request) —
-- see schema.sql's own comment on the table for the full picture. Plain
-- CREATE, not a rebuild-and-swap: this is a brand-new table, nothing to
-- migrate data out of.

CREATE TABLE IF NOT EXISTS achievement_description_cache (
    platform         TEXT NOT NULL,
    title_id         TEXT NOT NULL,
    achievement_id   TEXT NOT NULL,
    description_ru   TEXT,
    description_en   TEXT,
    source           TEXT NOT NULL CHECK (source IN ('native', 'llm')),
    cached_at        TEXT NOT NULL,
    PRIMARY KEY (platform, title_id, achievement_id)
);
