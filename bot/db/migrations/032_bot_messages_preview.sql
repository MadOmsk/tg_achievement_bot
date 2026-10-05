-- Adds `preview` to bot_messages (2026-09-09 user request) — /delete_last's
-- own confirmation shows the first couple of lines of what it just deleted,
-- so repeated deletes in a row are each individually confirmable. See
-- schema.sql's own comment on the column.
--
-- Rebuild-and-swap, not ALTER TABLE ADD COLUMN — same reasoning as every
-- other add-a-column migration here: schema.sql already creates this table
-- with the column for a brand-new database, and SQLite has no "add column
-- only if it doesn't already exist". Existing rows get NULL — nothing to
-- backfill, they're either stats results the admin panel's own bulk wipes
-- still find fine without a preview, or already-cleaned-up system messages.

CREATE TABLE bot_messages_new (
    chat_id    INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    message_id INTEGER NOT NULL,
    sent_at    TEXT NOT NULL,
    is_system  INTEGER NOT NULL DEFAULT 1,
    preview    TEXT,
    PRIMARY KEY (chat_id, message_id)
);

INSERT INTO bot_messages_new (chat_id, message_id, sent_at, is_system)
SELECT chat_id, message_id, sent_at, is_system FROM bot_messages;

DROP TABLE bot_messages;
ALTER TABLE bot_messages_new RENAME TO bot_messages;
