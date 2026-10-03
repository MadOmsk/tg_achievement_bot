-- Follows, blocks and the one privacy setting (#157, stage 3). These tables point at
-- the person id (users.id, migration 071), not at tg_id: a person who signs in some
-- other way has no tg_id, and the older tables will move over to the id later (#156).
--
-- Friends are not stored: two follows facing each other are a friendship.
-- `activity_visible` is who sees a person's activity in the app: everyone, friends or
-- nobody.

CREATE TABLE IF NOT EXISTS follows (
    follower_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    followee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (follower_id, followee_id),
    CHECK (follower_id != followee_id)
);
CREATE INDEX IF NOT EXISTS idx_follows_followee ON follows (followee_id);

CREATE TABLE IF NOT EXISTS blocks (
    person_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    blocked_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (person_id, blocked_id),
    CHECK (person_id != blocked_id)
);
CREATE INDEX IF NOT EXISTS idx_blocks_blocked ON blocks (blocked_id);

ALTER TABLE users ADD COLUMN activity_visible TEXT NOT NULL DEFAULT 'all'
    CHECK (activity_visible IN ('all', 'friends', 'nobody'));
