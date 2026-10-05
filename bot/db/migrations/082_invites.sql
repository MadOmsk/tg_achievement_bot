-- Invites (owner, 2026-10-05): for now somebody new signs up in a browser (by
-- email, or by Telegram's Login Widget) only with a code a member made. A code
-- lets one person in; who made it and who came by it are both kept.
CREATE TABLE IF NOT EXISTS invites (
    code        TEXT PRIMARY KEY,
    created_by  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    used_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    used_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_invites_created_by ON invites (created_by, created_at);
