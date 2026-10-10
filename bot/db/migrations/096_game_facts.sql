-- Who made a game and who published it (#147; owner, 2026-10-10): the
-- earliest version's, as its year is the earliest of all of them — a
-- remaster's own studio and date do not rename the game's.
ALTER TABLE games ADD COLUMN developer TEXT;
ALTER TABLE games ADD COLUMN publisher TEXT;
