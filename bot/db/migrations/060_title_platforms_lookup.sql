-- A game's platforms decide which version of it an achievement names (#114), so
-- an Xbox game without them is looked up in titlehub — before publishing, and by
-- poller/title_platforms.py for the rest. Three failed lookups end the search:
-- `platforms` becomes '[]' and the card falls back to the device played on.
ALTER TABLE titles ADD COLUMN platforms_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE titles ADD COLUMN platforms_checked_at TEXT;
