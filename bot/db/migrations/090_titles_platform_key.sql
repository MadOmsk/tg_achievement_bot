-- A game's row is keyed by its platform as well as its id (#147, stage 1),
-- as `seen_achievements` and `title_achievements` already are. The id spaces
-- overlap: Steam appids run to ~3.5M and Xbox title ids start below 1M on
-- production, so a Steam game and an Xbox one could share a row. A version is
-- one achievement list on one platform; two versions of a game on one family
-- (a 360 and a One card, separate PS4 and PS5 lists) have ids of their own.
--
-- `title_guide_reads` hangs on a game's id and moves with it. `title_groups`
-- does not: it is PSN's alone, and an `NPWR…` id names nothing elsewhere.
--
-- Rebuilt with foreign keys off for the whole script, as 071 and 078 do.

PRAGMA foreign_keys = OFF;

BEGIN;

-- A row with no platform of its own takes it from what was earned in it, then
-- from PSN's own tables; what is left is Xbox (the rows
-- `titles_without_platform` once found were all Xbox).
UPDATE titles SET platform = (
    SELECT MIN(s.platform) FROM seen_achievements s WHERE s.title_id = titles.title_id
) WHERE platform IS NULL;
UPDATE titles SET platform = 'psn'
WHERE platform IS NULL AND (title_id LIKE 'NPWR%'
    OR EXISTS (SELECT 1 FROM psn_title_progress p WHERE p.np_communication_id = titles.title_id));
UPDATE titles SET platform = 'xbox_modern' WHERE platform IS NULL;

CREATE TABLE titles_new (
    platform   TEXT NOT NULL,
    title_id   TEXT NOT NULL,
    name       TEXT NOT NULL,
    name_ru    TEXT,
    name_en    TEXT,
    platforms  TEXT,
    platforms_attempts   INTEGER NOT NULL DEFAULT 0,
    platforms_checked_at TEXT,
    icon_url   TEXT,
    achievements_total INTEGER,
    cover_path TEXT,
    cover_hash TEXT,
    cover_checked_at TEXT,
    achievements_checked_at TEXT,
    hltb_id INTEGER,
    hltb_match_score REAL,
    hltb_attempts INTEGER NOT NULL DEFAULT 0,
    hltb_checked_at TEXT,
    steam_appid INTEGER,
    steam_appid_attempts INTEGER NOT NULL DEFAULT 0,
    steam_appid_checked_at TEXT,
    tips_checked_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (platform, title_id)
);
INSERT INTO titles_new (
    platform, title_id, name, name_ru, name_en, platforms,
    platforms_attempts, platforms_checked_at, icon_url, achievements_total,
    cover_path, cover_hash, cover_checked_at, achievements_checked_at,
    hltb_id, hltb_match_score, hltb_attempts, hltb_checked_at,
    steam_appid, steam_appid_attempts, steam_appid_checked_at, tips_checked_at,
    updated_at
)
SELECT
    platform, title_id, name, name_ru, name_en, platforms,
    platforms_attempts, platforms_checked_at, icon_url, achievements_total,
    cover_path, cover_hash, cover_checked_at, achievements_checked_at,
    hltb_id, hltb_match_score, hltb_attempts, hltb_checked_at,
    steam_appid, steam_appid_attempts, steam_appid_checked_at, tips_checked_at,
    updated_at
FROM titles;
DROP TABLE titles;
ALTER TABLE titles_new RENAME TO titles;

-- The catalog of an Xbox game a generation fix moved without its catalog
-- (two ids on production carry rows under both): the game's own platform
-- wins, and the stray copy goes.
DELETE FROM title_achievements
WHERE platform IN ('xbox_modern', 'xbox_360')
  AND EXISTS (SELECT 1 FROM titles t
              WHERE t.title_id = title_achievements.title_id
                AND t.platform IN ('xbox_modern', 'xbox_360')
                AND t.platform <> title_achievements.platform)
  AND EXISTS (SELECT 1 FROM title_achievements o
              WHERE o.title_id = title_achievements.title_id
                AND o.achievement_id = title_achievements.achievement_id
                AND o.platform <> title_achievements.platform);

-- A guide read belongs to the game it was read for (one row per id before
-- this migration, so the game's platform is its row's).
CREATE TABLE title_guide_reads_new (
    platform    TEXT    NOT NULL,
    title_id    TEXT    NOT NULL,
    guide_id    TEXT    NOT NULL,
    fingerprint TEXT    NOT NULL,
    answer      TEXT    NOT NULL,
    checked_at  TEXT    NOT NULL,
    PRIMARY KEY (platform, title_id, guide_id)
);
INSERT INTO title_guide_reads_new
    (platform, title_id, guide_id, fingerprint, answer, checked_at)
SELECT COALESCE(
           (SELECT t.platform FROM titles t WHERE t.title_id = r.title_id),
           'steam'
       ),
       r.title_id, r.guide_id, r.fingerprint, r.answer, r.checked_at
FROM title_guide_reads r;
DROP TABLE title_guide_reads;
ALTER TABLE title_guide_reads_new RENAME TO title_guide_reads;

COMMIT;

PRAGMA foreign_keys = ON;
