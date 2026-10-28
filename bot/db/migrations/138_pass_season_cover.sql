-- A month's pass has a cover of its own (owner, 2026-10-28): a picture at
-- the head of its page, the page's colours read from it as a game's are.
-- A draft like the name: `draft_image_path` waits for the month's publish.
ALTER TABLE pass_seasons ADD COLUMN image_path TEXT;
ALTER TABLE pass_seasons ADD COLUMN draft_image_path TEXT;
