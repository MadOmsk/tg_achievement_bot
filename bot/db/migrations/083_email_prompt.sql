-- Somebody with no email is asked for one once, on opening the app (owner,
-- 2026-10-05): email is the main way in. When they answered «Позже».
ALTER TABLE users ADD COLUMN email_prompted_at TEXT;
