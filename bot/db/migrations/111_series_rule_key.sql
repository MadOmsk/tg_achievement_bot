-- Series a rule names (#147; owner, 2026-10-14): every LEGO game is in the
-- series "LEGO" beside its licence's, a franchise has its local series
-- ("Modern Warfare" in "Call of Duty", "Star Wars Jedi" in "Star Wars"). Such
-- a series has no anchor game; the rule's key says which it is. The unique
-- index on it is made by INDEXES_AFTER_MIGRATIONS (it names a column added here).

ALTER TABLE series ADD COLUMN rule_key TEXT;
