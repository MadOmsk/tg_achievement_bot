-- A player's own PSN token (owner, 2026-10-29; #233): an NPSSO a person adds
-- to one of their PSN accounts, opt-in. Kept by account: the token is that
-- account's, and goes when the account leaves its person. Fernet, never logged.
CREATE TABLE IF NOT EXISTS psn_tokens (
    account_id       TEXT PRIMARY KEY,
    person_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    npsso_enc        BLOB NOT NULL,
    status           TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'dead')),
    verified_at      TEXT NOT NULL,
    checked_at       TEXT,
    dead_at          TEXT,
    last_error       TEXT,
    notify_count     INTEGER NOT NULL DEFAULT 0,
    last_notified_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_psn_tokens_person ON psn_tokens (person_id);
