-- A season pass a month (owner, 2026-10-28): every level belongs to the
-- month whose pass it is, `YYYY-MM`. A new month's pass is empty until the
-- super-admin publishes one; the next month's may be built ahead. The levels
-- already there are the month they were published (or made) in.
ALTER TABLE pass_items ADD COLUMN month TEXT;
UPDATE pass_items SET month = substr(COALESCE(published_at, created_at), 1, 7)
    WHERE month IS NULL;
