-- Every answer given about the games, kept (#147; the training audit,
-- 2026-10-24): `match_decisions` and `game_series` hold the answer that
-- counts now, and a later one replaced an earlier there — an operator's
-- answer an adviser's, an undo the answer. The log keeps each event, so
-- sources can be compared and the models fitted on the history.
CREATE TABLE IF NOT EXISTS label_log (
    log_id     INTEGER PRIMARY KEY,
    subject    TEXT NOT NULL,      -- pair (two versions) / series (a game in a series)
    event      TEXT NOT NULL,      -- label / undo / skip / refused (kept under the operator's)
    version_id INTEGER,
    other_id   INTEGER,
    relation   TEXT,               -- a pair's relation
    game_id    INTEGER,
    series_id  INTEGER,
    member     INTEGER,            -- a series answer: 1 in it, 0 not
    decided_by TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    note       TEXT
);
CREATE INDEX IF NOT EXISTS idx_label_log_pair ON label_log(version_id, other_id);
CREATE INDEX IF NOT EXISTS idx_label_log_series ON label_log(game_id, series_id);

-- What was answered before the log, as it stands now.
INSERT INTO label_log (subject, event, version_id, other_id, relation, decided_by,
                       decided_at, note)
SELECT 'pair', 'label', version_id, other_id, relation, decided_by, decided_at,
       'before the log'
FROM match_decisions;
INSERT INTO label_log (subject, event, game_id, series_id, member, decided_by, decided_at,
                       note)
SELECT 'series', 'label', game_id, series_id, member, COALESCE(decided_by, source),
       COALESCE(updated_at, created_at), 'before the log'
FROM game_series WHERE source <> 'auto';
