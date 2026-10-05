-- Profile pictures, kept as files (#55, owner decision 2026-09-16: "качай
-- реальные аватарки" — the mini-app is meant to grow past this community,
-- and a face that only exists as somebody else's URL is a face that
-- disappears when they reorganize their CDN).
--
-- Two halves, and they are stored differently for a reason:
--
-- * Telegram's photo is already addressed by `users.photo_file_id`
--   (migration 042) — a file_id, usable only with the bot token. What is
--   new here is `photo_path`: the copy actually downloaded, so the mini-app
--   serves an image instead of round-tripping getFile with the token.
-- * A platform account's picture is a plain public URL (Xbox's
--   GameDisplayPicRaw, Steam's avatarfull, PSN's own avatars list). The URL
--   is worth keeping as the thing that changed, and the file beside it is
--   what gets served.
--
-- Paths are relative to data/avatars/, never absolute: the same database is
-- copied between machines whose paths differ, and an absolute path in a row
-- is a path that is wrong somewhere else. The hash is of the bytes, so
-- "same picture, new URL" is one comparison and no write.

ALTER TABLE users ADD COLUMN photo_path TEXT;

ALTER TABLE accounts ADD COLUMN avatar_url TEXT;
ALTER TABLE accounts ADD COLUMN avatar_path TEXT;
ALTER TABLE accounts ADD COLUMN avatar_hash TEXT;
ALTER TABLE accounts ADD COLUMN avatar_checked_at TEXT;
