-- Whether this person sees secret achievements unspoilered in the Mini App.
-- Off by default: secrets stay behind the reveal tap. Group teasers are
-- unchanged — Telegram cannot hide a published name from one viewer only.

ALTER TABLE user_settings ADD COLUMN show_secrets INTEGER NOT NULL DEFAULT 0;
