-- Game covers, kept as a URL *and* as a file (owner decision, 2026-09-18:
-- "храним ссылки на обложку игры, также скачиваем все обложки и сохраняем,
-- а в бд отдельный столбик для сопоставления"). The Mini App shows a game's
-- art beside every achievement, and on 2544 stored titles exactly two had
-- any art at all.
--
-- `titles.icon_url` already existed and already meant this — the game's own
-- box art, filled only for the handful of Xbox 360 titles whose achievement
-- messages borrow it. What is new is the rest of the platforms filling it
-- too, and the downloaded copy beside it:
--
-- * `cover_path` — the file actually on disk, relative to data/covers/,
--   never absolute: the same database is copied between machines whose
--   paths differ, and an absolute path in a row is a path that is wrong
--   somewhere else. This is the column that maps a row to its file.
-- * `cover_hash` — sha256 of the bytes, so "same picture, new URL" is one
--   comparison and no write.
-- * `cover_checked_at` — when this title was last looked at, so a game
--   whose platform offers no art is not asked about again on every tick
--   forever. Stamped whether or not anything was found.
--
-- Same three-column shape migration 046 gave `accounts` for avatars, and
-- for the same reasons; see poller/covers.py for what fills them.

ALTER TABLE titles ADD COLUMN cover_path TEXT;

ALTER TABLE titles ADD COLUMN cover_hash TEXT;

ALTER TABLE titles ADD COLUMN cover_checked_at TEXT;
