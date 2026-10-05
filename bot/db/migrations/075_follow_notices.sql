-- Whether the bot tells a person in a DM that someone followed them (#157). On by
-- default; the person turns it off in the Mini App's settings.
ALTER TABLE user_settings ADD COLUMN notify_followers INTEGER NOT NULL DEFAULT 1;
