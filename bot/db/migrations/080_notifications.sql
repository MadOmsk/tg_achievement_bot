-- The app's own notifications (#164): what a person is told is kept in a list
-- of their own, pushed to the devices that allowed it, and — only if they keep
-- it on and have Telegram — sent as a DM as well.
ALTER TABLE user_settings ADD COLUMN notify_push INTEGER NOT NULL DEFAULT 1;
ALTER TABLE user_settings ADD COLUMN notify_telegram INTEGER NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    -- What the text is made from (who, which game…), JSON; worded on reading,
    -- in the reader's language at that moment.
    data        TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    read_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_notifications_person ON notifications (person_id, id);

-- One row per browser that allowed push (#164). `endpoint` is the push
-- service's address for that browser; `p256dh`/`auth` are its keys.
CREATE TABLE IF NOT EXISTS push_subscriptions (
    endpoint    TEXT PRIMARY KEY,
    person_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    p256dh      TEXT NOT NULL,
    auth        TEXT NOT NULL,
    user_agent  TEXT,
    created_at  TEXT NOT NULL,
    last_ok_at  TEXT,
    failures    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_push_subscriptions_person ON push_subscriptions (person_id);
