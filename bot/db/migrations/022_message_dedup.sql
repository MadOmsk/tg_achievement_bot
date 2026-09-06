-- Self-deduplicating message kinds (Follow-up 2026-09-06): /panel, /summary,
-- /recent, a specific person's /stats card (plain dedup, tracked_messages),
-- plus /admin's own auto-refreshing screen (admin_panel_refresh, same shape
-- as online_auto_refresh). Brand-new tables, not columns added to an
-- existing one, so plain CREATE TABLE IF NOT EXISTS is safe here (same
-- reasoning as migrations 013/014/021).

CREATE TABLE IF NOT EXISTS tracked_messages (
    chat_id    INTEGER NOT NULL,
    kind       TEXT    NOT NULL CHECK (kind IN ('panel', 'summary', 'recent', 'stats')),
    subject_id INTEGER NOT NULL DEFAULT 0,
    message_id INTEGER NOT NULL,
    updated_at TEXT    NOT NULL,
    PRIMARY KEY (chat_id, kind, subject_id)
);

CREATE TABLE IF NOT EXISTS admin_panel_refresh (
    admin_id        INTEGER PRIMARY KEY,
    message_id      INTEGER NOT NULL,
    created_at      TEXT NOT NULL,
    last_updated_at TEXT NOT NULL
);
