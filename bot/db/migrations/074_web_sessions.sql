-- Browser sign-in (#157, stage 6): a person who signed in through Telegram Login
-- in a plain browser holds a server session. Only a hash of the random token is
-- stored, so a copy of the database cannot be replayed as a login. Sessions point
-- at the person id (users.id).

CREATE TABLE IF NOT EXISTS web_sessions (
    token_hash   TEXT PRIMARY KEY,
    person_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at   TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    user_agent   TEXT
);
CREATE INDEX IF NOT EXISTS idx_web_sessions_person ON web_sessions (person_id);
