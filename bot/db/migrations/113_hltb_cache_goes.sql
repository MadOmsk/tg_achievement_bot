-- The old HowLongToBeat cache (`hltb_cache`: what /hltb and the Mini App read,
-- with the Russian summary Haiku wrote) is read from the mirror now
-- (`hltb_entries`, 112; owner, 2026-10-15). What it holds that the mirror
-- does not comes over: an entry nobody's page was read for (the average
-- hours, the genre, the summaries; its page is read when it is looked up),
-- and every summary and translation already paid for.

INSERT OR IGNORE INTO hltb_entries
    (hltb_id, name, comp_main, comp_plus, comp_100, genres, summary_en, summary_ru, checked_at)
SELECT hltb_id, name,
       CAST(ROUND(main_hours * 3600) AS INTEGER),
       CAST(ROUND(extra_hours * 3600) AS INTEGER),
       CAST(ROUND(completionist_hours * 3600) AS INTEGER),
       genre, description_en, description_ru, cached_at
FROM hltb_cache;

UPDATE hltb_entries SET
    summary_en = COALESCE(summary_en,
        (SELECT c.description_en FROM hltb_cache c WHERE c.hltb_id = hltb_entries.hltb_id)),
    summary_ru = COALESCE(summary_ru,
        (SELECT c.description_ru FROM hltb_cache c WHERE c.hltb_id = hltb_entries.hltb_id))
WHERE hltb_id IN (SELECT hltb_id FROM hltb_cache);

DROP TABLE hltb_cache;
