-- The pictures HLTB gives its entries are kept on disk (#147; owner,
-- 2026-10-15), under data/covers/hltb/, as the bot keeps game covers: the
-- address can break, the file does not. Path, hash and the day it was asked.
ALTER TABLE hltb_entries ADD COLUMN image_path TEXT;
ALTER TABLE hltb_entries ADD COLUMN image_hash TEXT;
ALTER TABLE hltb_entries ADD COLUMN image_checked_at TEXT;
