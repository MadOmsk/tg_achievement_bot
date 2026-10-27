-- How far a game's versions spread past its earliest (#147; owner,
-- 2026-10-10): the latest version's year, and whether other versions were
-- made or published by somebody else — shown as "2006–2025", "Epic Games
-- and others".
ALTER TABLE games ADD COLUMN last_year INTEGER;
ALTER TABLE games ADD COLUMN more_developers INTEGER NOT NULL DEFAULT 0;
ALTER TABLE games ADD COLUMN more_publishers INTEGER NOT NULL DEFAULT 0;
