-- The Steam app an achievement list is (#147; owner, 2026-10-15) was three
-- columns of `titles`. A Steam list is its own app; any other is known by the
-- app found for it — HLTB's page, or Steam's store search — now kept as a
-- `steam_twin` id on the versions of the list (`versions.store_ids`), as the
-- ids that name a version already are, and read by `_sql.STEAM_APP_OF_TITLE`.
-- When it was last looked for goes to `fetch_state` ('steam_app', subject
-- "platform:title_id"). Every list has a version since 110.

UPDATE versions SET store_ids = json_insert(COALESCE(store_ids, '[]'), '$[#]',
    json_array('steam_twin', (SELECT CAST(t.steam_appid AS TEXT) FROM titles t
                              WHERE t.platform = versions.platform
                                AND t.title_id = versions.title_id)))
WHERE EXISTS (SELECT 1 FROM titles t WHERE t.platform = versions.platform
                AND t.title_id = versions.title_id AND t.platform <> 'steam'
                AND t.steam_appid IS NOT NULL);

INSERT OR REPLACE INTO fetch_state
    (subject, source, status, attempts, interval_days, checked_at, next_check_at, last_error)
SELECT
    t.platform || ':' || t.title_id, 'steam_app',
    CASE WHEN t.steam_appid IS NOT NULL THEN 'ok'
         WHEN t.steam_appid_attempts >= 3 THEN 'gave_up' ELSE 'error' END,
    CASE WHEN t.steam_appid IS NOT NULL THEN 0 ELSE t.steam_appid_attempts END,
    7,
    COALESCE(t.steam_appid_checked_at, t.updated_at),
    strftime('%Y-%m-%dT%H:%M:%S', COALESCE(t.steam_appid_checked_at, t.updated_at),
             CASE WHEN t.steam_appid IS NOT NULL THEN '+7 days'
                  WHEN t.steam_appid_attempts >= 3 THEN '+30 days' ELSE '+1 hour' END) || '+00:00',
    CASE WHEN t.steam_appid IS NULL THEN 'no app' END
FROM titles t
WHERE t.platform <> 'steam'
  AND (t.steam_appid IS NOT NULL OR t.steam_appid_attempts > 0 OR t.steam_appid_checked_at IS NOT NULL);

ALTER TABLE titles DROP COLUMN steam_appid;
ALTER TABLE titles DROP COLUMN steam_appid_attempts;
ALTER TABLE titles DROP COLUMN steam_appid_checked_at;
