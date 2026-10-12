-- The operator's labels outlive their versions (#147; 2026-10-12). A label
-- pointed at `versions` with ON DELETE CASCADE, so a store re-parse that
-- deletes a version (a bundle taken for a game, a product the store no longer
-- makes for that console) took every answer about it along — the operator's
-- work lost without a trace, and a training example with it. Now a label has
-- no foreign key: it stays when its version goes, and keeps which store
-- product each side was (`subject_key`, `other_key`: store:product_id:console)
-- so it can be found again. The linker only reads labels between versions
-- that exist; the fit reads a gone pair from its feature snapshot.
--
-- Rebuilt with foreign keys off for the whole script, as 071 and 078 do: the
-- pragma is a no-op inside a transaction.

PRAGMA foreign_keys = OFF;

BEGIN;

CREATE TABLE match_decisions_new (
    version_id  INTEGER NOT NULL,
    other_id    INTEGER NOT NULL,
    relation    TEXT NOT NULL,
    features    TEXT,
    model       TEXT,
    decided_by  TEXT NOT NULL,
    decided_at  TEXT NOT NULL,
    subject_key TEXT,
    other_key   TEXT,
    PRIMARY KEY (version_id, other_id),
    CHECK (version_id <> other_id)
);

INSERT INTO match_decisions_new
    (version_id, other_id, relation, features, model, decided_by, decided_at,
     subject_key, other_key)
SELECT d.version_id, d.other_id, d.relation, d.features, d.model, d.decided_by, d.decided_at,
       (SELECT v.store || ':' || v.product_id || ':' || v.console
          FROM versions v WHERE v.version_id = d.version_id),
       (SELECT v.store || ':' || v.product_id || ':' || v.console
          FROM versions v WHERE v.version_id = d.other_id)
  FROM match_decisions d;

DROP TABLE match_decisions;
ALTER TABLE match_decisions_new RENAME TO match_decisions;
CREATE INDEX IF NOT EXISTS idx_match_decisions_other ON match_decisions(other_id);

COMMIT;

PRAGMA foreign_keys = ON;
