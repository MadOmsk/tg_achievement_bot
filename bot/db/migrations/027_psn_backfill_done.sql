-- Adds backfill_done to psn_poll_state (#21). The regular trophy poller
-- (poller/psn_fetcher.py's tick) must not touch a freshly-linked account
-- until its initial backfill has finished: /connect_psn fires backfill as a
-- background task and returns immediately, so a scheduler tick landing
-- mid-backfill would call fetch/publish on trophies backfill hasn't stored
-- yet and flood the chat with the account's entire history. A brand-new
-- psn_poll_state row now starts at backfill_done = 0; backfill() flips it to
-- 1 as its final step; tick() skips anything still at 0. A stuck account
-- (linked, first backfill crashed) stays at 0 and is recovered through the
-- admin panel's PSN resync, not by the regular poller.
--
-- Rebuild-and-swap, not ALTER TABLE ADD COLUMN — same reasoning as every
-- other add-a-column migration here (002/006/010/012/017/018/020/024/025):
-- schema.sql already creates psn_poll_state with this column for a brand-new
-- database, and SQLite has no "add column only if it doesn't already exist".

CREATE TABLE psn_poll_state_new (
    account_id     TEXT PRIMARY KEY,
    last_polled_at TEXT NOT NULL,
    backfill_done  INTEGER NOT NULL DEFAULT 0
);

-- Every account already in this table has been polling fine for weeks — its
-- backfill is long done. Only genuinely new links (no row yet) start gated.
INSERT INTO psn_poll_state_new (account_id, last_polled_at, backfill_done)
SELECT account_id, last_polled_at, 1 FROM psn_poll_state;

DROP TABLE psn_poll_state;
ALTER TABLE psn_poll_state_new RENAME TO psn_poll_state;
