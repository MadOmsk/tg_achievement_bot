-- A version's facts, the games-model review (#147, 2026-10-11).
-- * Xbox's cross-gen set is its own column: one set is one game, a strong
--   sign; store_group keeps only the product group, which can hold a series.
-- * Versions "known from HLTB" go: HLTB is matched by name, and a version
--   nobody sells is no version (the page shows HLTB's platforms instead).
-- * version_hltb is looked up by its entry.
ALTER TABLE versions ADD COLUMN cross_gen_set TEXT;
DELETE FROM version_hltb WHERE version_id IN (SELECT version_id FROM versions WHERE store = 'hltb');
DELETE FROM version_games WHERE version_id IN (SELECT version_id FROM versions WHERE store = 'hltb');
DELETE FROM version_links WHERE version_id IN (SELECT version_id FROM versions WHERE store = 'hltb')
   OR of_version_id IN (SELECT version_id FROM versions WHERE store = 'hltb');
DELETE FROM version_store_ids WHERE version_id IN (SELECT version_id FROM versions WHERE store = 'hltb');
DELETE FROM dlcs WHERE version_id IN (SELECT version_id FROM versions WHERE store = 'hltb');
DELETE FROM edition_items WHERE version_id IN (SELECT version_id FROM versions WHERE store = 'hltb');
DELETE FROM versions WHERE store = 'hltb';
CREATE INDEX IF NOT EXISTS idx_version_hltb_hltb ON version_hltb(hltb_id);
