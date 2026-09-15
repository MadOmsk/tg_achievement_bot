-- An achievement's *name* in both languages (#61, owner request 2026-09-15:
-- a Russian chat was showing English names).
--
-- A separate table rather than two more columns on
-- `achievement_description_cache`, for two reasons. That table's `source`
-- describes where a *description* came from (native / llm / fallback), and a
-- name has no such story — it is only ever the platform's own, never
-- translated by anything (CLAUDE.md's rule, unchanged). And plenty of
-- achievements have a name and no description at all, which would otherwise
-- need a description row invented for them just to hold the name.
--
-- Both sides are the platform's own strings, fetched in the same two
-- locale requests the descriptions already ride on — no new requests.

CREATE TABLE IF NOT EXISTS achievement_name_cache (
    platform        TEXT NOT NULL,
    title_id        TEXT NOT NULL,
    achievement_id  TEXT NOT NULL,
    name_ru         TEXT,
    name_en         TEXT,
    cached_at       TEXT NOT NULL,
    PRIMARY KEY (platform, title_id, achievement_id)
);
