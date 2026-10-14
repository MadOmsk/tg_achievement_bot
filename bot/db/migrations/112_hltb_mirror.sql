-- The HowLongToBeat mirror (#147; owner, 2026-10-15): `hltb_games`, whose page
-- was kept as three JSON columns, becomes `hltb_entries` with a column for
-- every field of the page and tables for its platform rows, platform groups,
-- platforms and users' scores (schema.sql makes them). The rows come over with
-- what they hold: identity, the Steam ids, the studio, the description, its
-- translation, the picture, when it was read, and the average hours (hours as
-- the seconds HLTB gives). The rest is read again from the raw pages kept in
-- `source_payloads`, no request: `scripts/reparse_store_payloads.py`.

INSERT OR IGNORE INTO hltb_entries
    (hltb_id, name, game_type, parent_hltb_id, steam_appid, developer, publisher,
     summary_en, summary_ru, image, checked_at, page_read_at,
     comp_main, comp_plus, comp_100, comp_all)
SELECT hltb_id, name, game_type, parent_hltb_id, steam_appid, developer, publisher,
       summary_en, summary_ru,
       CASE WHEN image_url LIKE 'https://howlongtobeat.com/games/%' THEN substr(image_url, 33) END,
       checked_at, page_read_at,
       CAST(ROUND(json_extract(times, '$.main.average') * 3600) AS INTEGER),
       CAST(ROUND(json_extract(times, '$.extra.average') * 3600) AS INTEGER),
       CAST(ROUND(COALESCE(json_extract(times, '$.completionist.average'),
                           json_extract(times, '$.complete.average')) * 3600) AS INTEGER),
       CAST(ROUND(json_extract(times, '$.all.average') * 3600) AS INTEGER)
FROM hltb_games;

DROP TABLE hltb_games;
