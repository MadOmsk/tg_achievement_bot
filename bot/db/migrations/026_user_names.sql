-- Adds first_name/last_name to users — /stats' header now shows the
-- Telegram identity (@username, or first+last name if no username is set),
-- not the Xbox gamertag (Follow-up 2026-09-06, user request: the card
-- already lists every connected platform's own name on its own line below,
-- the header should identify the *person*, not default to whichever
-- platform happened to be Xbox). NULL until MessageLogMiddleware-adjacent
-- tracking (handlers/chat.py's message middleware) has seen at least one
-- message from them; a brand-new /start with nothing yet falls through to
-- the gamertag/platform name as a last resort (handlers/chat.py's
-- _display_name), same defensive shape username itself already had.
--
-- Rebuilt via a new table and swap, not ALTER TABLE ADD COLUMN — same
-- reasoning as every other add-a-column migration in this project
-- (002/006/010/012/017/018/020/024/025): schema.sql already creates users
-- with these columns for a brand-new database, and SQLite has no "add
-- column only if it doesn't already exist".

PRAGMA foreign_keys = OFF;

CREATE TABLE users_new (
    tg_id           INTEGER PRIMARY KEY,
    username        TEXT,
    first_name      TEXT,
    last_name       TEXT,
    xuid            TEXT UNIQUE,
    gamertag        TEXT,
    gamerscore      INTEGER,
    is_excluded     INTEGER NOT NULL DEFAULT 0,
    excluded_by     INTEGER,
    excluded_at     TEXT,
    last_online_at  TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

INSERT INTO users_new
    (tg_id, username, xuid, gamertag, gamerscore, is_excluded, excluded_by,
     excluded_at, last_online_at, created_at, updated_at)
SELECT tg_id, username, xuid, gamertag, gamerscore, is_excluded, excluded_by,
       excluded_at, last_online_at, created_at, updated_at
FROM users;

DROP TABLE users;
ALTER TABLE users_new RENAME TO users;

PRAGMA foreign_keys = ON;
