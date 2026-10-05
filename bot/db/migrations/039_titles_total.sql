-- `titles.achievements_total` — the denominator of the "47/50" beside a
-- notification's game line (#46), for the one platform that had no other
-- source for it.
--
-- Xbox states a per-account total in `title_history`, and Steam's total is
-- the length of its cached schema. PSN reports progress as a percentage and
-- never a count — but the trophy-title list it already fetches carries
-- `defined_trophies`, which services/psn/client.py already sums into
-- `defined_total` and then discarded. Storing it makes the counter work the
-- same way on all three platforms instead of being absent on one.
--
-- Rebuild-and-swap rather than ALTER TABLE ADD COLUMN, for the same reason
-- as every other add-a-column migration here: schema.sql already creates
-- this table with the column for a database that does not need this file.
-- `titles` is referenced by nothing, so no foreign-key dance.

CREATE TABLE titles_new (
    title_id   TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    platform   TEXT,
    icon_url   TEXT,
    achievements_total INTEGER,
    updated_at TEXT NOT NULL
);

INSERT INTO titles_new (title_id, name, platform, icon_url, updated_at)
SELECT title_id, name, platform, icon_url, updated_at FROM titles;

DROP TABLE titles;
ALTER TABLE titles_new RENAME TO titles;
