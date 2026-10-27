-- What a game is (#147; owner, 2026-10-12): a game, a compilation (a game
-- that holds more than one game) or an extra — a soundtrack, an artbook, an
-- app, an Insider build: not a game, kept as an entry of its own and joined
-- to nothing. The linker sets it on every rebuild; the operator's choice
-- (`kind_source = 'manual'`) is never overwritten.
ALTER TABLE games ADD COLUMN kind TEXT NOT NULL DEFAULT 'game';
ALTER TABLE games ADD COLUMN kind_source TEXT NOT NULL DEFAULT 'auto';
