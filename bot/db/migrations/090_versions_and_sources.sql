-- The store side of a game (#147, stage 2): what each store says about a
-- game, kept as versions, DLC and HLTB entries. Nothing reads these yet
-- beyond collecting them; games and their links come in stage 3.
--
-- A version is a store product on one console (owner, 2026-10-08): PS4 and
-- PS5, One and Series, are two versions even when they share one achievement
-- list; Xbox Play Anywhere's PC is a platform of the console version, not a
-- version of its own. Consoles are services/platform_format.py's canonical
-- names. A version points at its achievement list (`titles`) when it is
-- known; no foreign key to `titles`, whose key schema.sql may not have yet
-- on an older database (CLAUDE.md, bring-up).

CREATE TABLE IF NOT EXISTS versions (
    version_id   INTEGER PRIMARY KEY,
    store        TEXT NOT NULL,    -- steam / xbox / psn / x360 (no store: the 360 list itself)
    product_id   TEXT NOT NULL,    -- Steam appid, Xbox bigId, PSN concept id, 360 title id
    console      TEXT NOT NULL,    -- series / one / pc / 360 / ps5 / ps4 / ps3 / vita / steam
    platform     TEXT,             -- its achievement list: titles(platform, title_id)
    title_id     TEXT,
    name         TEXT,
    name_ru      TEXT,
    kind         TEXT,             -- the store's own: game / demo / dlc / bundle / app
    developer    TEXT,
    publisher    TEXT,
    release_date TEXT,             -- ISO day
    genres       TEXT,             -- JSON list
    also_on      TEXT,             -- JSON list: other platforms this product runs on (XPA's pc)
    store_group  TEXT,             -- how the store itself groups versions: Xbox ProductGroupId,
                                   -- PSN concept, Steam fullgame
    description_en TEXT,
    description_ru TEXT,
    media        TEXT,             -- JSON: cover, screenshots, videos (links)
    live_service INTEGER NOT NULL DEFAULT 0,
    origin       TEXT NOT NULL DEFAULT 'played',  -- played / store (found, nobody here owns it)
    updated_at   TEXT NOT NULL,
    UNIQUE (store, product_id, console)
);
CREATE INDEX IF NOT EXISTS idx_versions_title ON versions(platform, title_id);

-- Every store id that names a version: regional PSN products (several CUSA
-- for one PS4 version), an Xbox title id, a Steam appid.
CREATE TABLE IF NOT EXISTS version_store_ids (
    store      TEXT NOT NULL,      -- steam_app / xbox_product / xbox_title / psn_title / psn_concept
    store_id   TEXT NOT NULL,
    version_id INTEGER NOT NULL REFERENCES versions(version_id) ON DELETE CASCADE,
    source     TEXT NOT NULL,      -- catalog / presence / search / manual
    PRIMARY KEY (store, store_id, version_id)
);
CREATE INDEX IF NOT EXISTS idx_version_store_ids_version ON version_store_ids(version_id);

CREATE TABLE IF NOT EXISTS dlcs (
    dlc_id       INTEGER PRIMARY KEY,
    version_id   INTEGER NOT NULL REFERENCES versions(version_id) ON DELETE CASCADE,
    store_id     TEXT,             -- Steam DLC appid / Xbox add-on bigId / PSN add-on product id
    trophy_group_id TEXT,          -- PSN: title_groups(title_id, group_id)
    name         TEXT,
    name_ru      TEXT,
    kind         TEXT,             -- dlc / expansion / season_pass / soundtrack / other
    release_date TEXT,
    description_en TEXT,
    image_url    TEXT,
    updated_at   TEXT NOT NULL,
    CHECK (store_id IS NOT NULL OR trophy_group_id IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dlcs_store ON dlcs(version_id, store_id)
    WHERE store_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_dlcs_group ON dlcs(version_id, trophy_group_id)
    WHERE trophy_group_id IS NOT NULL;

-- The new HLTB store: one row per entry, the page's fields. `hltb_cache`
-- stays for /hltb's search until it is switched off.
CREATE TABLE IF NOT EXISTS hltb_games (
    hltb_id        INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    game_type      TEXT,           -- game / dlc / expansion / mod / …
    parent_hltb_id INTEGER,
    steam_appid    INTEGER,
    developer      TEXT,
    publisher      TEXT,
    release_year   INTEGER,
    platforms      TEXT,           -- JSON list, as HLTB names them
    times          TEXT,           -- JSON: bucket → average / median / fastest / slowest hours
    platform_times TEXT,           -- JSON: platform → main / extra / complete hours, count
    details        TEXT,           -- JSON: score, alias, releases, ratings, modes, speedruns
    summary_en     TEXT,
    summary_ru     TEXT,
    image_url      TEXT,
    checked_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS version_hltb (
    version_id INTEGER NOT NULL REFERENCES versions(version_id) ON DELETE CASCADE,
    hltb_id    INTEGER NOT NULL,
    source     TEXT NOT NULL,      -- auto / manual
    PRIMARY KEY (version_id, hltb_id)
);

CREATE TABLE IF NOT EXISTS dlc_hltb (
    dlc_id  INTEGER NOT NULL REFERENCES dlcs(dlc_id) ON DELETE CASCADE,
    hltb_id INTEGER NOT NULL,
    source  TEXT NOT NULL,
    PRIMARY KEY (dlc_id, hltb_id)
);

-- A source's last answer, compressed (zlib JSON), the latest only, rewritten
-- only when its hash changes. `subject` names what was asked:
-- `steam:292030`, `xbox:BR765873CQJD`, `psn:204794`, `hltb:10270`.
CREATE TABLE IF NOT EXISTS source_payloads (
    subject    TEXT NOT NULL,
    source     TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    sha256     TEXT NOT NULL,
    payload    BLOB NOT NULL,
    PRIMARY KEY (subject, source)
) WITHOUT ROWID;

-- When each subject was last asked of each source, and when to ask again:
-- the interval doubles while nothing changes (7 → 14 → 30 → 90 days) and
-- falls back to 7 when something did (live-service games stay frequent).
CREATE TABLE IF NOT EXISTS fetch_state (
    subject       TEXT NOT NULL,
    source        TEXT NOT NULL,
    status        TEXT NOT NULL,   -- ok / not_found / error / gave_up
    attempts      INTEGER NOT NULL DEFAULT 0,  -- failures in a row
    interval_days INTEGER NOT NULL DEFAULT 7,
    checked_at    TEXT NOT NULL,
    next_check_at TEXT NOT NULL,
    last_error    TEXT,
    PRIMARY KEY (subject, source)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_fetch_state_due ON fetch_state(next_check_at);
