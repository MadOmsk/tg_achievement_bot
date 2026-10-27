-- When an HLTB entry's own page was last read (#147; 2026-10-12). Another
-- page names it too — a game's DLC page lists the game, with average times
-- only — and that row used to overwrite the game's own times and make it the
-- DLC's child. Only an entry's own page sets its type, parent and times now;
-- another page's row fills an entry no page of its own was read for.
ALTER TABLE hltb_games ADD COLUMN page_read_at TEXT;

-- An entry whose page answer is kept was read from its own page.
UPDATE hltb_games SET page_read_at = checked_at
 WHERE page_read_at IS NULL
   AND EXISTS (SELECT 1 FROM source_payloads p
                WHERE p.subject = 'hltb:' || hltb_games.hltb_id AND p.source = 'hltb_page');
