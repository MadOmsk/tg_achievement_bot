-- A Mythic and a completion, as a person earns them (#147; owner,
-- 2026-10-16). Not achievements of their own yet: a mark on the earned row
-- that brought them — `mythic`, the last of the game's base list (Xbox's
-- `base` group), and `completes`, the last of its whole list. Each is set once
-- per account and game, when it happens (`repo.mark_xbox_completions`), and
-- stays: a list that grows later does not take back what was earned.
ALTER TABLE seen_achievements ADD COLUMN mythic INTEGER NOT NULL DEFAULT 0;
ALTER TABLE seen_achievements ADD COLUMN completes INTEGER NOT NULL DEFAULT 0;
