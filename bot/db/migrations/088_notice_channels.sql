-- Where each kind of notice goes (owner, 2026-10-06): every notice is kept in
-- the app's list; push and Telegram each carry only the kinds switched on there
-- (comma-separated keys of services/notifier.py::KINDS, a choice after a colon
-- where the kind has one: `new_post:friends`, `game_news:patch`) — none by
-- default. `notify_posts` (081) and 087's per-kind switches are no longer read.
-- A migration of its own, not an edit of 087: 087 had already run on the test
-- and dev servers, and an applied migration never runs again.
ALTER TABLE user_settings ADD COLUMN notify_push_on TEXT NOT NULL DEFAULT '';
ALTER TABLE user_settings ADD COLUMN notify_telegram_on TEXT NOT NULL DEFAULT '';
-- Who was told of new followers by a Telegram message before (075) keeps them
-- there; the old switch is no longer read.
UPDATE user_settings SET notify_telegram_on = 'new_follower,new_friend' WHERE notify_followers = 1;
