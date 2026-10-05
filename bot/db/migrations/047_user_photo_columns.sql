-- Put the Telegram-photo columns back on `users` (found rehearsing the
-- accounts-52 merge against a copy of production, 2026-09-16).
--
-- The two branches added things to `users` in the opposite order, and the
-- merge makes production walk that order backwards:
--
--   * main added the photo columns in 042, and production has them today;
--   * this branch rebuilt `users` in 038 — written when no photo column
--     existed — so the rebuild copies the columns it knew about and drops
--     the rest.
--
-- Run 038 on a database that already has 042 and the photos are gone: the
-- table comes back without them, `get_user` then asks for `photo_file_id`
-- and raises `IndexError: No item with that key` on the first screen anybody
-- opens. That is what this migration prevents.
--
-- 046 already adds `photo_path`, so only the three from 042 are here. On a
-- database that has them (this branch's own test bot, where 042 landed
-- *after* the rebuild) every statement below is a duplicate column and is
-- skipped — see `_apply_one` in db/repo/_database.py for why that is not an
-- error.
--
-- The file_ids themselves are lost in that rebuild and are not recoverable
-- from here: `poller/avatars.py` collects them again within the hour, which
-- is what it is for.

ALTER TABLE users ADD COLUMN photo_file_id TEXT;
ALTER TABLE users ADD COLUMN photo_unique_id TEXT;
ALTER TABLE users ADD COLUMN photo_checked_at TEXT;
