-- `users` keeps only the Telegram identity (#52, step 1b).
--
-- Step 1 moved Xbox into `accounts`/`account_links` but left `users.xuid`,
-- `gamertag`, `gamertag_modern` and `gamerscore` behind as a cache of the
-- active link, because some seventy call sites read them. They have a single
-- writer since then, and every query now reaches the same facts through the
-- link instead (db/repo/_sql.py::XBOX_ACCOUNT), so the cache has nothing left
-- to do — and a second copy of a fact is a second version of it waiting to
-- happen.
--
-- The UNIQUE on `users.xuid` goes with them. It said "one person per Xbox
-- account", which `idx_links_one_owner` now says for every platform at once.
--
-- Nothing is read from the dropped columns here: migration 037 already copied
-- them into `accounts`, and this file only runs after it.
--
-- Rebuild-and-swap with foreign keys off — `users` is the parent of most of
-- the schema, and a DROP would cascade every child row away before the rename
-- puts the table back. Same shape as 036 and 037.

PRAGMA foreign_keys = OFF;

CREATE TABLE users_new (
    tg_id           INTEGER PRIMARY KEY,
    username        TEXT,
    first_name      TEXT,
    last_name       TEXT,
    is_excluded     INTEGER NOT NULL DEFAULT 0,
    excluded_by     INTEGER,
    excluded_at     TEXT,
    last_online_at  TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

INSERT INTO users_new
    (tg_id, username, first_name, last_name, is_excluded, excluded_by, excluded_at,
     last_online_at, created_at, updated_at)
SELECT tg_id, username, first_name, last_name, is_excluded, excluded_by, excluded_at,
       last_online_at, created_at, updated_at
FROM users;

DROP TABLE users;
ALTER TABLE users_new RENAME TO users;

PRAGMA foreign_keys = ON;
