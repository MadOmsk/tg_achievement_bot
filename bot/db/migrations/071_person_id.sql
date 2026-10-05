-- A person gets an id of their own (#156, step 1). `users.tg_id` stops being the
-- primary key and becomes a plain unique column that may be empty — a person who
-- will sign in some other way has no Telegram id. Every other table still points
-- at users(tg_id), which SQLite allows for a UNIQUE column, so no code changes here.
--
-- SQLite cannot change a primary key in place: the table is rebuilt. Foreign keys
-- must be off while it is, or dropping the old table would cascade-delete every row
-- that points at it; they are switched off before the transaction (the pragma is a
-- no-op inside one) and back on after it. The ids are given in the order people
-- joined. Old rows are copied as they are: the tg_id > 0 check schema.sql puts on
-- new databases is not imposed on data written before it existed.

PRAGMA foreign_keys = OFF;

BEGIN;

CREATE TABLE users_new (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id            INTEGER UNIQUE,
    username         TEXT,
    first_name       TEXT,
    last_name        TEXT,
    is_excluded      INTEGER NOT NULL DEFAULT 0,
    excluded_by      INTEGER,
    excluded_at      TEXT,
    last_online_at   TEXT,
    photo_file_id    TEXT,
    photo_unique_id  TEXT,
    photo_checked_at TEXT,
    photo_path       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

INSERT INTO users_new (
    tg_id, username, first_name, last_name, is_excluded, excluded_by, excluded_at,
    last_online_at, photo_file_id, photo_unique_id, photo_checked_at, photo_path,
    created_at, updated_at
)
SELECT
    tg_id, username, first_name, last_name, is_excluded, excluded_by, excluded_at,
    last_online_at, photo_file_id, photo_unique_id, photo_checked_at, photo_path,
    created_at, updated_at
FROM users
ORDER BY created_at, tg_id;

DROP TABLE users;
ALTER TABLE users_new RENAME TO users;

COMMIT;

PRAGMA foreign_keys = ON;
