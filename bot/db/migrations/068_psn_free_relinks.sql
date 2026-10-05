-- The person's PSN cooldown counts re-links, not deletions (owner,
-- 2026-09-30): after a deletion somebody who held N PSN accounts may link N
-- accounts again for free; one more inside the window is blocked. Xbox and
-- Steam keep counting deletions (one account each, one free re-link).
ALTER TABLE platform_cooldowns ADD COLUMN free_relinks INTEGER NOT NULL DEFAULT 1;
ALTER TABLE platform_cooldowns ADD COLUMN relinks INTEGER NOT NULL DEFAULT 0;
