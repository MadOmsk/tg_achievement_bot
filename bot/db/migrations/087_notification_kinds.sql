-- Each kind of notice has its own switch (owner, 2026-10-06); `notify_posts`
-- stays whose activity one hears of (friends, everybody followed, nobody).
ALTER TABLE user_settings ADD COLUMN notify_new_posts INTEGER NOT NULL DEFAULT 1;
ALTER TABLE user_settings ADD COLUMN notify_friends INTEGER NOT NULL DEFAULT 1;
ALTER TABLE user_settings ADD COLUMN notify_account INTEGER NOT NULL DEFAULT 1;
-- A new post of a game's developer, for the people who play it: every post,
-- patches only, news only, or none.
ALTER TABLE user_settings ADD COLUMN notify_game_news TEXT NOT NULL DEFAULT 'all'
    CHECK (notify_game_news IN ('all', 'patch', 'news', 'none'));
