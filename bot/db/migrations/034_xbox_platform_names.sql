-- Rename the two Xbox platform values (2026-09-11, user request):
--   'modern' -> 'xbox_modern'
--   'x360'   -> 'xbox_360'
--
-- 'modern' was named when Xbox was the only platform here and the word had
-- an obvious subject. Next to 'steam' and 'psn' it stopped having one — it
-- actually means Xbox One, Series and the PC Microsoft Store, which share
-- one achievement service and one contract (4). 'x360' was already
-- unambiguous but is renamed alongside it so both Xbox values look alike.
--
-- Three tables store these strings. Only `seen_achievements` needs a
-- rebuild-and-swap (its CHECK constraint names the old values, and SQLite
-- cannot alter a constraint in place — same shape as every other
-- constraint-touching migration here); the other two are plain UPDATEs, as
-- neither constrains the column.
--
-- Order matters: the UPDATEs below run against the *new* table, so they are
-- written after the swap.

CREATE TABLE seen_achievements_new (
    tg_id           INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    xuid            TEXT NOT NULL,
    title_id        TEXT NOT NULL,
    achievement_id  TEXT NOT NULL,
    name            TEXT,
    description     TEXT,
    icon_url        TEXT,
    unlocked_at     TEXT,
    gamerscore      INTEGER,
    rarity_percent  REAL,
    platform        TEXT NOT NULL DEFAULT 'xbox_modern'
                    CHECK (platform IN ('xbox_modern', 'xbox_360', 'steam', 'psn')),
    is_backfill     INTEGER NOT NULL DEFAULT 0,
    is_secret       INTEGER NOT NULL DEFAULT 0,
    trophy_type     TEXT,
    created_at      TEXT NOT NULL,
    PRIMARY KEY (tg_id, platform, title_id, achievement_id)
);

INSERT INTO seen_achievements_new
    (tg_id, xuid, title_id, achievement_id, name, description, icon_url,
     unlocked_at, gamerscore, rarity_percent, platform, is_backfill, is_secret,
     trophy_type, created_at)
SELECT tg_id, xuid, title_id, achievement_id, name, description, icon_url,
       unlocked_at, gamerscore, rarity_percent,
       CASE platform
           WHEN 'modern' THEN 'xbox_modern'
           WHEN 'x360'   THEN 'xbox_360'
           ELSE platform
       END,
       is_backfill, is_secret, trophy_type, created_at
FROM seen_achievements;

DROP TABLE seen_achievements;
ALTER TABLE seen_achievements_new RENAME TO seen_achievements;

-- The description cache is keyed by (platform, title_id, achievement_id), so
-- leaving the old spelling here would orphan every Xbox row the #48 backfill
-- just filled in — the lookup would miss and the bot would silently re-fetch
-- and re-translate all of it.
UPDATE achievement_description_cache SET platform = 'xbox_modern' WHERE platform = 'modern';
UPDATE achievement_description_cache SET platform = 'xbox_360'   WHERE platform = 'x360';

-- Xbox's own title cache: drives the x360 box-art fallback and /stats' games
-- list, so a stale value here would quietly lose both for those titles.
-- (`titles`, not `title_history` — the latter has no platform column at all;
-- checked rather than assumed, having written the wrong name first.)
UPDATE titles SET platform = 'xbox_modern' WHERE platform = 'modern';
UPDATE titles SET platform = 'xbox_360'   WHERE platform = 'x360';

-- Deliberately untouched: `platform_links` only ever holds 'steam'/'psn'
-- (its own CHECK says so), and `hltb_cache.platforms` is a JSON list of
-- HowLongToBeat's own platform names, not this enum.
