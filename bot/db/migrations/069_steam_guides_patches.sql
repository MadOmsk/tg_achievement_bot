-- What Steam knows about a game beyond its achievements: the Steam app it is
-- (for an Xbox or PlayStation game, looked up once, like its HLTB entry), the
-- community guides' tip for each achievement, and the developer's patch notes.
-- Filled when a game's first new achievement is published, and on a visit to
-- its page when it still is not; patches are refreshed in the background.

ALTER TABLE titles ADD COLUMN steam_appid INTEGER;
ALTER TABLE titles ADD COLUMN steam_appid_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE titles ADD COLUMN steam_appid_checked_at TEXT;
ALTER TABLE titles ADD COLUMN tips_checked_at TEXT;

ALTER TABLE title_achievements ADD COLUMN tip_en TEXT;
ALTER TABLE title_achievements ADD COLUMN tip_ru TEXT;
ALTER TABLE title_achievements ADD COLUMN tip_source TEXT;
ALTER TABLE title_achievements ADD COLUMN tip_translation TEXT
    CHECK (tip_translation IN ('llm'));

CREATE TABLE IF NOT EXISTS steam_apps (
    appid              INTEGER PRIMARY KEY,
    guides_checked_at  TEXT,
    patches_checked_at TEXT
);

CREATE TABLE IF NOT EXISTS game_patches (
    steam_appid  INTEGER NOT NULL,
    gid          TEXT    NOT NULL,
    title        TEXT    NOT NULL,
    published_at TEXT    NOT NULL,
    text_en      TEXT,
    title_ru     TEXT,
    text_ru      TEXT,
    created_at   TEXT    NOT NULL,
    PRIMARY KEY (steam_appid, gid)
);

CREATE INDEX IF NOT EXISTS idx_game_patches_published
    ON game_patches(steam_appid, published_at);
