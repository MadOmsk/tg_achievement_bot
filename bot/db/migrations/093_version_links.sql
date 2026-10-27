-- Owner's review of the first games (#147, 2026-10-09):
--
-- A version made from our own achievement list when no store described it
-- was filed under a store called "list"; it is the platform's own (an Xbox
-- 360 game is Xbox's), so it is named by its store and marked a stand-in.
--
-- A demo belongs to one version, not only to the game: the RE2 demo on One
-- to RE2 on One. `version_links` keeps that (`demo_of`), with who decided it.

ALTER TABLE versions ADD COLUMN stand_in INTEGER NOT NULL DEFAULT 0;

UPDATE versions SET stand_in = 1,
    store = CASE
        WHEN platform IN ('xbox_modern', 'xbox_360') THEN 'xbox'
        WHEN platform = 'psn' THEN 'psn'
        ELSE 'steam'
    END,
    product_id = title_id
WHERE store IN ('list', 'x360')
  AND NOT EXISTS (
      SELECT 1 FROM versions o
      WHERE o.store = CASE
              WHEN versions.platform IN ('xbox_modern', 'xbox_360') THEN 'xbox'
              WHEN versions.platform = 'psn' THEN 'psn' ELSE 'steam' END
        AND o.product_id = versions.title_id AND o.console = versions.console
  );

CREATE TABLE IF NOT EXISTS version_links (
    version_id    INTEGER NOT NULL REFERENCES versions(version_id) ON DELETE CASCADE,
    of_version_id INTEGER NOT NULL REFERENCES versions(version_id) ON DELETE CASCADE,
    kind          TEXT NOT NULL,   -- demo_of
    source        TEXT NOT NULL,   -- auto / manual
    decided_at    TEXT NOT NULL,
    PRIMARY KEY (version_id, kind),
    CHECK (version_id <> of_version_id)
);
