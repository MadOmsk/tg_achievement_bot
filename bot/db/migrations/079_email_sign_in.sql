-- Signing in by email (#162). `users.email` is the address a person proved with
-- a code, lower-cased; one person per address. NULL = no email login.
ALTER TABLE users ADD COLUMN email TEXT;
ALTER TABLE users ADD COLUMN email_linked_at TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users (email) WHERE email IS NOT NULL;

-- The one-time codes sent to an address. Only an HMAC of the code is kept.
-- `person_id` is set when a signed-in person adds the address to themselves
-- (purpose 'link'), NULL for a sign-in.
CREATE TABLE IF NOT EXISTS email_codes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT NOT NULL,
    purpose     TEXT NOT NULL CHECK (purpose IN ('sign_in', 'link')),
    person_id   INTEGER REFERENCES users(id) ON DELETE CASCADE,
    code_hash   TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    used_at     TEXT,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_email_codes_email ON email_codes (email, created_at);
