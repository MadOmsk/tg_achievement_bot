-- A picture the person chose in the Mini App (#157), shown instead of their Telegram
-- photo. Relative to data/avatars/, like users.photo_path; NULL = the Telegram one.
ALTER TABLE users ADD COLUMN custom_avatar_path TEXT;
