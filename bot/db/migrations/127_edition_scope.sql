-- What a store's bundle is, read from what it holds (#147; owner, 2026-10-24):
-- `edition` (one game, maybe with its own DLC — Monster Hunter Rise +
-- Sunbreak), `bundle` (several games, none of them the bundle's own — the
-- PopCap Bundle, games of different series), `addon_pack` (add-ons or
-- currency, no game). A game an item stands for keeps its version link; its
-- `role` says what it is to the bundle: `main` (the edition's game), `bonus`
-- (thrown in — Plants vs. Zombies Garden Warfare in FIFA 16 Super Deluxe),
-- `part` (one of a bundle's games). Set by the collection and by the re-parse.
ALTER TABLE editions ADD COLUMN scope TEXT NOT NULL DEFAULT 'edition';
ALTER TABLE edition_items ADD COLUMN role TEXT;
