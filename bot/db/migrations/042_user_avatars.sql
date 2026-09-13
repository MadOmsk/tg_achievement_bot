-- A person's Telegram profile photo, for the mini-app (owner request,
-- 2026-09-13): it shows people, and a list of names with no faces is not what
-- anyone means by a profile list.
--
-- What is stored is Telegram's own `file_id` — not an image and not a URL.
-- A file_id is only usable together with the bot token (getFile, then the
-- download URL that carries the token), so the token never has to leave the
-- server and nothing here is a secret on its own. `photo_unique_id` is stable
-- per photo and changes when the person changes their picture, which is how a
-- refresh can tell "still the same one" without downloading anything.
--
-- Deliberately numbered 042, above everything on the accounts-52 branch (up to
-- 041), so that when the two meet this file is one file, applied once, rather
-- than a second 037 racing the branch's own — and so it lands *after* that
-- branch's 038, which rebuilds `users` and would otherwise drop these columns.

ALTER TABLE users ADD COLUMN photo_file_id TEXT;
ALTER TABLE users ADD COLUMN photo_unique_id TEXT;
ALTER TABLE users ADD COLUMN photo_checked_at TEXT;
