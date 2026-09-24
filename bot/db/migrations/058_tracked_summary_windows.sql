-- /summary_day and /summary_month each replace their own previous copy under
-- kind 'summary_day' / 'summary_month', which the CHECK never allowed: the
-- report reached the chat and then set_tracked_message raised, so the next
-- call could not replace it. SQLite cannot alter a CHECK, so the table is
-- rebuilt. 'summary' stays for rows left by the removed /summary.

CREATE TABLE tracked_messages_new (
    chat_id    INTEGER NOT NULL,
    kind       TEXT    NOT NULL CHECK (
        kind IN ('panel', 'summary', 'summary_day', 'summary_month', 'recent', 'stats')
    ),
    subject_id INTEGER NOT NULL DEFAULT 0,
    message_id INTEGER NOT NULL,
    updated_at TEXT    NOT NULL,
    PRIMARY KEY (chat_id, kind, subject_id)
);

INSERT INTO tracked_messages_new (chat_id, kind, subject_id, message_id, updated_at)
SELECT chat_id, kind, subject_id, message_id, updated_at FROM tracked_messages;

DROP TABLE tracked_messages;

ALTER TABLE tracked_messages_new RENAME TO tracked_messages;
