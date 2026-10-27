-- The ids that name a version are a column of the version (#147; owner,
-- 2026-10-14): a JSON list of [kind, id], as a parsed product lists them
-- (`StoreVersion.store_ids`). Nothing ever looked a version up by one of
-- them, only the ids of one version were read, and `source` was always
-- "catalog", so the table (091) goes.

ALTER TABLE versions ADD COLUMN store_ids TEXT;

UPDATE versions SET store_ids = (
    SELECT json_group_array(json_array(i.store, i.store_id))
    FROM (SELECT store, store_id FROM version_store_ids
          WHERE version_id = versions.version_id ORDER BY rowid) i
)
WHERE EXISTS (SELECT 1 FROM version_store_ids i WHERE i.version_id = versions.version_id);

DROP INDEX IF EXISTS idx_version_store_ids_version;
DROP TABLE version_store_ids;
