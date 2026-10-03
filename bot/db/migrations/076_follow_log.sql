-- One row per (follower, followee) pair (#157), kept apart from `follows`, whose row
-- an unfollow deletes:
--   notified_at   — when the bot last told the followee about a follow: one DM a day
--                   at most, so following and unfollowing in a loop spams nobody;
--   unfollowed_at — the last unfollow: following the same person again waits ten
--                   minutes (owner, 2026-10-03).
CREATE TABLE IF NOT EXISTS follow_log (
    follower_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    followee_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    notified_at   TEXT,
    unfollowed_at TEXT,
    PRIMARY KEY (follower_id, followee_id)
);
