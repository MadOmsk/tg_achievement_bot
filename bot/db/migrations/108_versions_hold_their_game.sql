-- A version is in exactly one game, so the table that said so (game_versions,
-- 099) is columns of the version itself (#147; owner, 2026-10-14: two tables
-- with one row per version were one table). `game_id` is empty until the
-- matcher links the version; `p` is `link_p` (`match_pairs` has a `p` of its
-- own). The role CHECK is not kept: the list of roles changed twice (100, 107)
-- and a CHECK means rebuilding `versions`, which nine tables point at; the
-- roles are checked in game_link.py. The index on (game_id, role) is made by
-- INDEXES_AFTER_MIGRATIONS (it names a column added here).

ALTER TABLE versions ADD COLUMN game_id INTEGER REFERENCES games(game_id) ON DELETE SET NULL;
ALTER TABLE versions ADD COLUMN role TEXT;
ALTER TABLE versions ADD COLUMN of_version_id INTEGER REFERENCES versions(version_id) ON DELETE SET NULL;
ALTER TABLE versions ADD COLUMN link_p REAL;
ALTER TABLE versions ADD COLUMN linked_at TEXT;

UPDATE versions SET
    game_id       = (SELECT gv.game_id FROM game_versions gv WHERE gv.version_id = versions.version_id),
    role          = (SELECT gv.role FROM game_versions gv WHERE gv.version_id = versions.version_id),
    of_version_id = (SELECT gv.of_version_id FROM game_versions gv WHERE gv.version_id = versions.version_id),
    link_p        = (SELECT gv.p FROM game_versions gv WHERE gv.version_id = versions.version_id),
    linked_at     = (SELECT gv.linked_at FROM game_versions gv WHERE gv.version_id = versions.version_id)
WHERE EXISTS (SELECT 1 FROM game_versions gv WHERE gv.version_id = versions.version_id);

DROP INDEX IF EXISTS idx_game_versions_game;
DROP TABLE game_versions;
