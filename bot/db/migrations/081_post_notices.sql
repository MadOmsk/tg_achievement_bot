-- Notices about new posts (#164; owner, 2026-10-05): whose new achievements a
-- person is told about — friends only (the default), everybody they follow,
-- or nobody.
ALTER TABLE user_settings ADD COLUMN notify_posts TEXT NOT NULL DEFAULT 'friends'
    CHECK (notify_posts IN ('friends', 'following', 'none'));
