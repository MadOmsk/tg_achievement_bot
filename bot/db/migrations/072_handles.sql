-- A person is named by a nickname only (#157). `handle` is as typed, Latin letters
-- and digits; `handle_norm` is the lower-case form uniqueness is judged on;
-- `handle_number` is the four digits the system adds when the nickname is taken,
-- 0 when there are none (a NULL would make every row distinct to SQLite). Nobody
-- has a nickname yet: bot/services/handles.py gives every person a first one at
-- start-up (SQL cannot strip and de-duplicate names) and the Mini App asks them to
-- keep or change it (`handle_confirmed_at`). `handle_changed_at` is the last real
-- change, for the once-per-30-days limit.
ALTER TABLE users ADD COLUMN handle TEXT;
ALTER TABLE users ADD COLUMN handle_norm TEXT;
ALTER TABLE users ADD COLUMN handle_number INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN handle_confirmed_at TEXT;
ALTER TABLE users ADD COLUMN handle_changed_at TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_handle ON users (handle_norm, handle_number);
