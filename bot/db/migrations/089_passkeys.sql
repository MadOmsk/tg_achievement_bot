-- Passkeys (owner, 2026-10-08): a key kept on a phone or a computer that signs
-- its person in, in place of an email's code. Only the public half is here;
-- the id is the authenticator's own (base64url), the count guards against a
-- copied key.
CREATE TABLE IF NOT EXISTS passkeys (
    id            TEXT PRIMARY KEY,
    person_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    public_key    BLOB NOT NULL,
    sign_count    INTEGER NOT NULL DEFAULT 0,
    transports    TEXT,
    name          TEXT,
    created_at    TEXT NOT NULL,
    last_used_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_passkeys_person ON passkeys (person_id);
