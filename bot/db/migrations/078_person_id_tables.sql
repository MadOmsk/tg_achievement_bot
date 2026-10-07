-- The tables about a person point at the person's own id (#156, step 2), not at
-- their Telegram id: somebody who signs in by email (#162) has none. Five tables
-- move — `account_links`, `tokens`, `user_settings`, `subscriptions`,
-- `notification_throttle`. What is Telegram by nature keeps its Telegram id:
-- `chat_seen` (who wrote in a group), the admins' ids, and the reset cooldowns
-- (`platform_cooldowns*`), which must outlive a deleted person to do their job.
--
-- Each table is rebuilt (SQLite cannot change a key in place) with foreign keys
-- off for the whole script, as 071 does: the pragma is a no-op inside a
-- transaction, and dropping a parent with them on would cascade. A row is copied
-- only when its Telegram id names a person; every one of these tables already had
-- a foreign key to users, so none is lost.

PRAGMA foreign_keys = OFF;

BEGIN;

-- ---------------------------------------------------------------- account_links
CREATE TABLE account_links_new (
    person_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform    TEXT NOT NULL,
    external_id TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    linked_at   TEXT NOT NULL,
    unlinked_at TEXT,
    publishes   INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (person_id, platform, external_id),
    FOREIGN KEY (platform, external_id) REFERENCES accounts(platform, external_id)
);
-- rowid order kept: `active_account` breaks ties between a person's PSN accounts
-- by it, and the first one linked names the person.
INSERT INTO account_links_new (
    rowid, person_id, platform, external_id, is_active, linked_at, unlinked_at, publishes
)
SELECT al.rowid, u.id, al.platform, al.external_id, al.is_active, al.linked_at,
       al.unlinked_at, al.publishes
FROM account_links al JOIN users u ON u.tg_id = al.tg_id;
DROP TABLE account_links;
ALTER TABLE account_links_new RENAME TO account_links;
CREATE UNIQUE INDEX IF NOT EXISTS idx_links_one_active_per_platform
    ON account_links(person_id, platform) WHERE is_active = 1 AND platform <> 'psn';
CREATE UNIQUE INDEX IF NOT EXISTS idx_links_one_owner
    ON account_links(platform, external_id) WHERE is_active = 1;

-- ----------------------------------------------------------------------- tokens
CREATE TABLE tokens_new (
    person_id         INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_enc BLOB NOT NULL,
    status            TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active', 'invalid', 'revoked')),
    fail_count        INTEGER NOT NULL DEFAULT 0,
    last_refresh_at   TEXT,
    invalid_at        TEXT,
    notify_count      INTEGER NOT NULL DEFAULT 0,
    last_notified_at  TEXT,
    created_at        TEXT NOT NULL
);
INSERT INTO tokens_new (
    person_id, refresh_token_enc, status, fail_count, last_refresh_at, invalid_at,
    notify_count, last_notified_at, created_at
)
SELECT u.id, t.refresh_token_enc, t.status, t.fail_count, t.last_refresh_at, t.invalid_at,
       t.notify_count, t.last_notified_at, t.created_at
FROM tokens t JOIN users u ON u.tg_id = t.tg_id;
DROP TABLE tokens;
ALTER TABLE tokens_new RENAME TO tokens;

-- ---------------------------------------------------------------- user_settings
CREATE TABLE user_settings_new (
    person_id          INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    rarity_mode        TEXT    NOT NULL DEFAULT 'all'
                       CHECK (rarity_mode IN ('all', 'rare', 'hidden')),
    muted_title_ids    TEXT    NOT NULL DEFAULT '[]',
    tz_offset_min      INTEGER,
    show_profile_links INTEGER NOT NULL DEFAULT 0,
    show_secrets       INTEGER NOT NULL DEFAULT 0,
    locale             TEXT    NOT NULL DEFAULT 'ru',
    notify_followers   INTEGER NOT NULL DEFAULT 1
);
INSERT INTO user_settings_new (
    person_id, rarity_mode, muted_title_ids, tz_offset_min, show_profile_links,
    show_secrets, locale, notify_followers
)
SELECT u.id, s.rarity_mode, s.muted_title_ids, s.tz_offset_min, s.show_profile_links,
       s.show_secrets, s.locale, s.notify_followers
FROM user_settings s JOIN users u ON u.tg_id = s.tg_id;
DROP TABLE user_settings;
ALTER TABLE user_settings_new RENAME TO user_settings;

-- ---------------------------------------------------------------- subscriptions
CREATE TABLE subscriptions_new (
    chat_id     INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    person_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (chat_id, person_id)
);
INSERT INTO subscriptions_new (chat_id, person_id, created_at)
SELECT s.chat_id, u.id, s.created_at
FROM subscriptions s JOIN users u ON u.tg_id = s.tg_id;
DROP TABLE subscriptions;
ALTER TABLE subscriptions_new RENAME TO subscriptions;

-- -------------------------------------------------------- notification_throttle
CREATE TABLE notification_throttle_new (
    person_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chat_id           INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    window_started_at TEXT    NOT NULL,
    count_in_window   INTEGER NOT NULL DEFAULT 0,
    throttled         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (person_id, chat_id)
);
INSERT INTO notification_throttle_new (
    person_id, chat_id, window_started_at, count_in_window, throttled
)
SELECT u.id, n.chat_id, n.window_started_at, n.count_in_window, n.throttled
FROM notification_throttle n JOIN users u ON u.tg_id = n.tg_id;
DROP TABLE notification_throttle;
ALTER TABLE notification_throttle_new RENAME TO notification_throttle;

COMMIT;

PRAGMA foreign_keys = ON;
