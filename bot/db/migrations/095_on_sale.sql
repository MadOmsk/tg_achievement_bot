-- Whether a store still sells a version or an edition (#147; owner,
-- 2026-10-10: a game taken off sale is still the game of everybody who has
-- it). NULL: not known (a stand-in, a version HLTB only says exists).
-- Steam's answer is the region the bot asks from: an app may be off sale in
-- one and on in another (Skyrim 2011).
ALTER TABLE versions ADD COLUMN on_sale INTEGER;
ALTER TABLE editions ADD COLUMN on_sale INTEGER;
