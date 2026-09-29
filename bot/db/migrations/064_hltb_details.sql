-- The rest of a game's HLTB page beyond genre and description: rating,
-- developer/publisher, other names, regional release dates, play modes,
-- co-op/multiplayer hours, each category's spread and speedrun records.
-- One JSON object rather than a column per field — it is read and written
-- whole, never queried into. NULL means the page has not been read for it
-- yet; a row cached before this column is filled in on its next lookup.
ALTER TABLE hltb_cache ADD COLUMN details TEXT;
