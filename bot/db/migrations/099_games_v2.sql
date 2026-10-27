-- The games model after the review (#147; owner, 2026-10-11).
-- The operator's decisions are input — labels on pairs of versions, with the
-- pair's signs and the model that saw them — and a game's versions are output,
-- recomputed from the labels and the model, so a decision is never lost when
-- games are rebuilt. A version is in exactly one game; a remaster, a remake, a
-- compilation, a VR version is a game of its own, related to the original.

CREATE TABLE IF NOT EXISTS match_decisions (
    version_id INTEGER NOT NULL REFERENCES versions(version_id) ON DELETE CASCADE,
    other_id   INTEGER NOT NULL REFERENCES versions(version_id) ON DELETE CASCADE,
    relation   TEXT NOT NULL,   -- same / edition / demo_of / tool_of / remaster_of /
                                -- remake_of / contains / vr_of / other
    features   TEXT,            -- JSON: the pair's signs when it was decided
    model      TEXT,            -- which weights saw them
    decided_by TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    PRIMARY KEY (version_id, other_id),
    CHECK (version_id <> other_id)
);
CREATE INDEX IF NOT EXISTS idx_match_decisions_other ON match_decisions(other_id);

CREATE TABLE IF NOT EXISTS game_versions (
    version_id    INTEGER PRIMARY KEY REFERENCES versions(version_id) ON DELETE CASCADE,
    game_id       INTEGER NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    role          TEXT NOT NULL,   -- version / edition / demo / tool
    of_version_id INTEGER REFERENCES versions(version_id) ON DELETE SET NULL,
    p             REAL,
    linked_at     TEXT NOT NULL,
    CHECK (of_version_id IS NULL OR role IN ('demo', 'tool'))
);
CREATE INDEX IF NOT EXISTS idx_game_versions_game ON game_versions(game_id, role);

CREATE TABLE IF NOT EXISTS match_pairs (
    version_id INTEGER NOT NULL REFERENCES versions(version_id) ON DELETE CASCADE,
    other_id   INTEGER NOT NULL REFERENCES versions(version_id) ON DELETE CASCADE,
    relation   TEXT NOT NULL,
    p          REAL NOT NULL,
    probs      TEXT NOT NULL,   -- JSON: every class's probability
    features   TEXT NOT NULL,
    model      TEXT NOT NULL,
    scored_at  TEXT NOT NULL,
    PRIMARY KEY (version_id, other_id)
);

ALTER TABLE games ADD COLUMN anchor_version_id INTEGER REFERENCES versions(version_id)
    ON DELETE SET NULL;
ALTER TABLE game_relations ADD COLUMN p REAL;

-- The operator's rows become labels, against another version of the game they
-- were about (its first linked one).
INSERT OR IGNORE INTO match_decisions
    (version_id, other_id, relation, features, model, decided_by, decided_at)
SELECT vg.version_id,
       (SELECT MIN(o.version_id) FROM version_games o
         WHERE o.game_id = vg.game_id AND o.state = 'linked' AND o.version_id <> vg.version_id),
       CASE
         WHEN vg.state = 'rejected' THEN 'other'
         WHEN vg.kind = 'edition' THEN 'edition'
         WHEN vg.kind = 'remaster' THEN 'remaster_of'
         WHEN vg.kind = 'compilation' THEN 'contains'
         WHEN vg.kind = 'demo' THEN 'demo_of'
         WHEN vg.kind = 'tool' THEN 'tool_of'
         ELSE 'same'
       END,
       NULL, NULL, COALESCE(vg.decided_by, 'viewer'), vg.decided_at
  FROM version_games vg
 WHERE vg.source = 'manual'
   AND (SELECT MIN(o.version_id) FROM version_games o
         WHERE o.game_id = vg.game_id AND o.state = 'linked'
           AND o.version_id <> vg.version_id) IS NOT NULL;

INSERT OR REPLACE INTO match_decisions
    (version_id, other_id, relation, features, model, decided_by, decided_at)
SELECT version_id, of_version_id, kind, NULL, NULL, 'viewer', decided_at
  FROM version_links WHERE source = 'manual';

-- Each game keeps an anchor (its first linked version that is no demo), so it
-- keeps its id when the matcher rebuilds it; an anchor anchors one game.
UPDATE games SET anchor_version_id = (
    SELECT a.anchor FROM (
        SELECT game_id, anchor,
               ROW_NUMBER() OVER (PARTITION BY anchor ORDER BY game_id) AS n
          FROM (SELECT vg.game_id, MIN(vg.version_id) AS anchor FROM version_games vg
                 WHERE vg.state = 'linked' AND vg.kind NOT IN ('demo', 'tool')
                 GROUP BY vg.game_id)
    ) a WHERE a.game_id = games.game_id AND a.n = 1
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_games_anchor ON games(anchor_version_id);

DROP TABLE version_games;
DROP TABLE version_links;
