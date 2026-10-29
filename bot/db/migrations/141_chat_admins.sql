-- Roles (owner, 2026-10-29; #232). A chat's admin, by Telegram id, one per
-- chat: whoever added the bot, for the chats it is in now. And the chat's
-- own publishing switch, in place of the admin's "bot on" (is_active stays
-- the bot's own flag).
CREATE TABLE IF NOT EXISTS chat_admins (
    chat_id    INTEGER PRIMARY KEY REFERENCES chats(chat_id) ON DELETE CASCADE,
    tg_id      INTEGER NOT NULL,
    granted_by INTEGER,
    granted_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_admins_tg ON chat_admins(tg_id);

INSERT OR IGNORE INTO chat_admins (chat_id, tg_id, granted_by, granted_at)
SELECT chat_id, added_by, NULL, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
FROM chats
WHERE is_active = 1 AND added_by IS NOT NULL AND chat_id < 0;

ALTER TABLE chat_settings ADD COLUMN publishing INTEGER NOT NULL DEFAULT 1;
