-- Which HowLongToBeat entry an achievement list is has one home (#147; owner,
-- 2026-10-14): the links of its versions (`version_hltb`). `titles.hltb_id`
-- copied them, and the copy won where it mattered — the Mini App ignored the
-- operator's links, and a link the evidence removed was made again from it.
--
-- * every list gets a version when it has none (a stand-in made from the
--   list, as `stores.stand_in_for` does: its store and console are the SQL
--   twin of `store_of` / `console_of`, checked against them in tests), so the
--   link has somewhere to be;
-- * `titles.hltb_id` becomes an automatic link of each of the list's versions,
--   with its score; an entry the operator or the advisers refuse is the new
--   source `rejected`;
-- * the attempts and the time of the last one go to `fetch_state`
--   ('hltb_match', subject "platform:title_id");
-- * the four columns go.

ALTER TABLE version_hltb ADD COLUMN score REAL;

INSERT OR IGNORE INTO versions
    (store, product_id, console, platform, title_id, name, name_ru, kind, live_service,
     origin, updated_at, stand_in, store_ids)
SELECT
    CASE
        WHEN t.platform = 'xbox_modern' AND json_valid(t.platforms)
             AND json_type(t.platforms) = 'array' AND json_array_length(t.platforms) = 1
             AND json_extract(t.platforms, '$[0]') = 'Win32' THEN 'unknown'
        WHEN t.platform IN ('xbox_modern', 'xbox_360') THEN 'xbox'
        ELSE t.platform
    END,
    t.title_id,
    CASE
        WHEN t.platform = 'xbox_360' THEN '360'
        WHEN t.platform = 'steam' THEN 'steam'
        WHEN t.platform = 'psn' THEN
            CASE WHEN COALESCE(f.has_ps5, 0) AND NOT COALESCE(f.has_ps4, 0) THEN 'ps5' ELSE 'ps4' END
        WHEN COALESCE(f.has_series, 0) AND NOT COALESCE(f.has_one, 0) THEN 'series'
        WHEN COALESCE(f.has_pc, 0) AND NOT COALESCE(f.has_other, 0) THEN 'pc'
        ELSE 'one'
    END,
    t.platform,
    t.title_id,
    CASE WHEN t.name IS NOT NULL AND trim(t.name) NOT IN ('', '?') THEN t.name ELSE t.name_en END,
    t.name_ru,
    'game', 0, 'played', t.updated_at, 1,
    json_array(json_array('list', t.platform || ':' || t.title_id))
FROM titles t
LEFT JOIN (
    SELECT platform, title_id,
           MAX(canon = 'series') AS has_series, MAX(canon = 'one') AS has_one,
           MAX(canon = 'ps5') AS has_ps5, MAX(canon = 'ps4') AS has_ps4,
           MAX(canon = 'pc') AS has_pc, MAX(canon IS NOT NULL AND canon <> 'pc') AS has_other
    FROM (
        SELECT t2.platform AS platform, t2.title_id AS title_id,
               CASE lower(trim(j.value))
                   WHEN 'xboxseries' THEN 'series' WHEN 'xboxseriesx' THEN 'series'
                   WHEN 'xboxseriess' THEN 'series' WHEN 'xboxscarlett' THEN 'series'
                   WHEN 'scarlett' THEN 'series' WHEN 'anaconda' THEN 'series'
                   WHEN 'lockhart' THEN 'series'
                   WHEN 'xboxone' THEN 'one' WHEN 'xboxones' THEN 'one' WHEN 'xboxonex' THEN 'one'
                   WHEN 'durango' THEN 'one' WHEN 'xboxdurango' THEN 'one' WHEN 'scorpio' THEN 'one'
                   WHEN 'pc' THEN 'pc' WHEN 'win32' THEN 'pc' WHEN 'windows' THEN 'pc'
                   WHEN 'windowsonecore' THEN 'pc'
                   WHEN 'xbox360' THEN '360' WHEN 'xbox 360' THEN '360' WHEN 'x360' THEN '360'
                   WHEN 'mobile' THEN 'mobile' WHEN 'ios' THEN 'mobile' WHEN 'android' THEN 'mobile'
                   WHEN 'windowsphone' THEN 'mobile'
                   WHEN 'web' THEN 'cloud' WHEN 'cloud' THEN 'cloud'
                   WHEN 'ps5' THEN 'ps5' WHEN 'ps4' THEN 'ps4' WHEN 'ps3' THEN 'ps3'
                   WHEN 'psvita' THEN 'vita' WHEN 'ps vita' THEN 'vita' WHEN 'vita' THEN 'vita'
                   WHEN 'pspc' THEN 'pspc' WHEN 'ps pc' THEN 'pspc'
               END AS canon
        FROM titles t2, json_each(t2.platforms) j
        WHERE json_valid(t2.platforms) AND json_type(t2.platforms) = 'array'
              AND j.value IS NOT NULL AND j.value <> ''
    )
    GROUP BY platform, title_id
) f ON f.platform = t.platform AND f.title_id = t.title_id
WHERE NOT EXISTS (
    SELECT 1 FROM versions v WHERE v.platform = t.platform AND v.title_id = t.title_id
);

INSERT OR IGNORE INTO version_hltb (version_id, hltb_id, source, score)
SELECT v.version_id, t.hltb_id, 'auto', t.hltb_match_score
FROM titles t JOIN versions v ON v.platform = t.platform AND v.title_id = t.title_id
WHERE t.hltb_id IS NOT NULL;

UPDATE version_hltb SET score = (
    SELECT t.hltb_match_score FROM titles t JOIN versions v
        ON v.platform = t.platform AND v.title_id = t.title_id
    WHERE v.version_id = version_hltb.version_id AND t.hltb_id = version_hltb.hltb_id
)
WHERE source = 'auto' AND score IS NULL;

INSERT OR REPLACE INTO fetch_state
    (subject, source, status, attempts, interval_days, checked_at, next_check_at, last_error)
SELECT
    t.platform || ':' || t.title_id, 'hltb_match',
    CASE WHEN t.hltb_id IS NOT NULL THEN 'ok'
         WHEN t.hltb_attempts >= 3 THEN 'gave_up' ELSE 'error' END,
    CASE WHEN t.hltb_id IS NOT NULL THEN 0 ELSE t.hltb_attempts END,
    7,
    COALESCE(t.hltb_checked_at, t.updated_at),
    strftime('%Y-%m-%dT%H:%M:%S', COALESCE(t.hltb_checked_at, t.updated_at),
             CASE WHEN t.hltb_id IS NOT NULL THEN '+7 days'
                  WHEN t.hltb_attempts >= 3 THEN '+30 days' ELSE '+1 hour' END) || '+00:00',
    CASE WHEN t.hltb_id IS NULL THEN 'no match' END
FROM titles t
WHERE t.hltb_id IS NOT NULL OR t.hltb_attempts > 0 OR t.hltb_checked_at IS NOT NULL;

ALTER TABLE titles DROP COLUMN hltb_id;
ALTER TABLE titles DROP COLUMN hltb_match_score;
ALTER TABLE titles DROP COLUMN hltb_attempts;
ALTER TABLE titles DROP COLUMN hltb_checked_at;
