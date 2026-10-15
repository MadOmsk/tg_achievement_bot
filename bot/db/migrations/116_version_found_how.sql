-- How each version came into the database (#147; owner, 2026-10-15): the way
-- it was found, what found it (a list "platform:title_id", an HLTB entry
-- "hltb:id", a searched name "name:…"), and when. Set when the version is
-- made and never rewritten by a later look.
--   list     the list of achievements itself (a stand-in made from `titles`)
--   played   the store's product of a list somebody here has
--   sibling  another store's product found for a list (Steam's app, PSN's concept)
--   hltb     a Steam app that an HLTB entry names
--   search   a store searched by a game's name
--   earlier  made before this was recorded
ALTER TABLE versions ADD COLUMN found_how TEXT;
ALTER TABLE versions ADD COLUMN found_via TEXT;
ALTER TABLE versions ADD COLUMN found_at TEXT;

UPDATE versions SET found_how = 'list', found_via = platform || ':' || title_id,
    found_at = updated_at
WHERE stand_in = 1 AND title_id IS NOT NULL;

UPDATE versions SET found_how = 'played', found_via = platform || ':' || title_id,
    found_at = updated_at
WHERE found_how IS NULL AND stand_in = 0 AND title_id IS NOT NULL AND origin = 'played';

-- A Steam app that a list's `steam_twin` names was found for that list.
UPDATE versions SET found_how = 'sibling', found_at = updated_at,
    found_via = (SELECT w.platform || ':' || w.title_id FROM versions w, json_each(w.store_ids) j
                 WHERE w.title_id IS NOT NULL AND json_extract(j.value, '$[0]') = 'steam_twin'
                   AND json_extract(j.value, '$[1]') = versions.product_id LIMIT 1)
WHERE found_how IS NULL AND store = 'steam' AND EXISTS (
    SELECT 1 FROM versions w, json_each(w.store_ids) j
    WHERE w.title_id IS NOT NULL AND json_extract(j.value, '$[0]') = 'steam_twin'
      AND json_extract(j.value, '$[1]') = versions.product_id);

-- A Steam app that an HLTB entry's page names was found through that entry.
UPDATE versions SET found_how = 'hltb', found_at = updated_at,
    found_via = 'hltb:' || (SELECT MIN(h.hltb_id) FROM hltb_entries h
                            WHERE h.steam_appid = CAST(versions.product_id AS INTEGER)
                               OR h.steam_alt = CAST(versions.product_id AS INTEGER))
WHERE found_how IS NULL AND store = 'steam' AND EXISTS (
    SELECT 1 FROM hltb_entries h
    WHERE h.steam_appid = CAST(versions.product_id AS INTEGER)
       OR h.steam_alt = CAST(versions.product_id AS INTEGER));

UPDATE versions SET found_how = 'earlier', found_at = updated_at WHERE found_how IS NULL;
