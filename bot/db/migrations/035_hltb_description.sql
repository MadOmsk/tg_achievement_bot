-- Adds `description_en`/`description_ru` to hltb_cache (2026-09-12 user
-- request, #2): the game's own summary, shown as a collapsible blockquote at
-- the end of the /hltb card. Both languages, stored side by side, for the
-- same reason achievement_description_cache holds both — HLTB writes English
-- only, so the Russian side is an LLM translation that must be paid for once
-- and never again, whatever locale the next person to ask happens to use.
--
-- Rebuild-and-swap, not ALTER TABLE ADD COLUMN — same reasoning as migrations
-- 006 and 012 on this very table: schema.sql already creates hltb_cache with
-- these columns for a brand-new database, and SQLite has no "add column only
-- if it doesn't already exist". Existing rows get NULL and fill themselves in
-- lazily on the next lookup (services/hltb.py::resolve tops up a cached row
-- that predates the columns). No foreign keys in or out, so no PRAGMA
-- foreign_keys toggle needed around the swap.

CREATE TABLE hltb_cache_new (
    hltb_id             INTEGER PRIMARY KEY,
    name                TEXT NOT NULL,
    release_year        INTEGER,
    main_hours          REAL,
    extra_hours         REAL,
    completionist_hours REAL,
    platforms           TEXT NOT NULL DEFAULT '[]',
    game_url            TEXT,
    image_url           TEXT,
    genre               TEXT,
    description_en      TEXT,
    description_ru      TEXT,
    cached_at           TEXT NOT NULL
);

INSERT INTO hltb_cache_new
    (hltb_id, name, release_year, main_hours, extra_hours, completionist_hours,
     platforms, game_url, image_url, genre, cached_at)
SELECT hltb_id, name, release_year, main_hours, extra_hours, completionist_hours,
       platforms, game_url, image_url, genre, cached_at
FROM hltb_cache;

DROP TABLE hltb_cache;
ALTER TABLE hltb_cache_new RENAME TO hltb_cache;
