-- Which HowLongToBeat entry each game is (#131): a game page shows HLTB's
-- hours and description without anybody having to search and pick one first.
-- Same shape as migration 060's platform lookup — a finite backlog, given up
-- on after a few failed attempts rather than retried forever.
ALTER TABLE titles ADD COLUMN hltb_id INTEGER;
ALTER TABLE titles ADD COLUMN hltb_match_score REAL;
ALTER TABLE titles ADD COLUMN hltb_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE titles ADD COLUMN hltb_checked_at TEXT;
