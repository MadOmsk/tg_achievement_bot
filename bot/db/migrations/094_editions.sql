-- Editions as a store sells them (#147; owner, 2026-10-10): a pack of a game
-- and its add-ons — E-Day's Premium Edition, Skyrim's Anniversary Edition —
-- not a re-release (Gears of War: Ultimate Edition is a version, a remaster).
-- On Xbox an edition is a bundle product, on Steam a package of the game's
-- app. Editions come and go on the stores (pre-orders vanish at release), so
-- when one was first and last seen is kept.

CREATE TABLE IF NOT EXISTS editions (
    edition_id    INTEGER PRIMARY KEY,
    store         TEXT NOT NULL,    -- xbox / steam / psn
    store_id      TEXT NOT NULL,    -- Xbox bundle bigId, Steam package id, PSN product id
    name          TEXT,
    kind          TEXT,             -- standard / deluxe / premium / ultimate / gold / goty /
                                    -- complete / anniversary / preorder / bundle
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    UNIQUE (store, store_id)
);

-- What an edition holds: its game (a version of ours, when we have it) and
-- add-ons (our DLC rows, when we have them), currency kept as such.
CREATE TABLE IF NOT EXISTS edition_items (
    edition_id INTEGER NOT NULL REFERENCES editions(edition_id) ON DELETE CASCADE,
    store_id   TEXT NOT NULL,       -- the item's own id on that store
    name       TEXT,
    item_kind  TEXT NOT NULL,       -- game / dlc / consumable / other
    is_primary INTEGER NOT NULL DEFAULT 0,
    version_id INTEGER REFERENCES versions(version_id) ON DELETE SET NULL,
    PRIMARY KEY (edition_id, store_id)
);
CREATE INDEX IF NOT EXISTS idx_edition_items_version ON edition_items(version_id);
