-- Full schema, SPEC section 3. Applied once to an empty database; later changes
-- go to db/migrations/ so an existing bot.db is never recreated from scratch.

-- Telegram users. Only the Telegram identity lives here (#52): an Xbox
-- account is an `accounts` row like any other, reached through the active
-- link in `account_links`, and used to be cached in xuid/gamertag/gamerscore
-- columns beside these. A second copy of a fact is a second version of it
-- waiting to happen.
CREATE TABLE IF NOT EXISTS users (
    tg_id           INTEGER PRIMARY KEY,
    username        TEXT,                 -- for /stats @user, refreshed on every message
    -- /stats' header identity (Follow-up 2026-09-06) — refreshed the same
    -- way username is, on every message (handlers/chat.py's message
    -- middleware). first_name always exists for a real Telegram account;
    -- last_name doesn't.
    first_name      TEXT,
    last_name       TEXT,
    is_excluded     INTEGER NOT NULL DEFAULT 0,
    excluded_by     INTEGER,
    excluded_at     TEXT,
    last_online_at  TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- One user, one token. Refresh only; everything else lives in memory.
CREATE TABLE IF NOT EXISTS tokens (
    tg_id             INTEGER PRIMARY KEY REFERENCES users(tg_id) ON DELETE CASCADE,
    refresh_token_enc BLOB NOT NULL,      -- Fernet, NEVER logged
    status            TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active', 'invalid', 'revoked')),
    -- active:  usable token
    -- invalid: Microsoft refused to refresh (SPEC 5.1.2), polling stopped
    -- revoked: the user opted out himself, no more reminders
    fail_count        INTEGER NOT NULL DEFAULT 0,
    last_refresh_at   TEXT,
    invalid_at        TEXT,
    notify_count      INTEGER NOT NULL DEFAULT 0,
    last_notified_at  TEXT,
    created_at        TEXT NOT NULL
);

-- Chats we post to
CREATE TABLE IF NOT EXISTS chats (
    chat_id    INTEGER PRIMARY KEY,
    title      TEXT,
    is_active  INTEGER NOT NULL DEFAULT 1,  -- cleared when Telegram answers 403
    added_by   INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subscriptions (
    chat_id     INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    tg_id       INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    -- Per (person, chat), not one global value on the person (moved off
    -- user_settings — same reasoning as 'all'/'rare'/'hidden' documented
    -- there originally, now scoped down: what counts as worth publishing
    -- can differ between a close-friends chat and a big public one).
    -- New subscriptions default to 'all', same as user_settings used to.
    rarity_mode TEXT NOT NULL DEFAULT 'all'
                CHECK (rarity_mode IN ('all', 'rare', 'hidden')),
    -- Per (person, chat), same move as rarity_mode above and for the same
    -- reason (Follow-up, 2026-09-05) — how many achievements at once
    -- deserve one summary message instead of separate ones can reasonably
    -- differ between a quiet chat and a busy one.
    digest_threshold INTEGER NOT NULL DEFAULT 3,
    PRIMARY KEY (chat_id, tg_id)
);

-- Who's been seen writing in a chat, separately from `subscriptions` (who
-- chose to publish there) — /online lists this, not just publishers (SPEC 6.3).
CREATE TABLE IF NOT EXISTS chat_seen (
    chat_id      INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    tg_id        INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (chat_id, tg_id)
);

CREATE TABLE IF NOT EXISTS user_settings (
    tg_id            INTEGER PRIMARY KEY REFERENCES users(tg_id) ON DELETE CASCADE,
    -- rarity_mode and digest_threshold used to live here, one value for
    -- every chat a person publishes to. Both moved to subscriptions (one
    -- per chat, not one for all of them — Follow-ups, SPEC 9 M-Steam-2e
    -- and 2026-09-05) — a chat with close friends and a big public one can
    -- reasonably want different answers to both "what's worth showing" and
    -- "how many at once is a lot". rarity_mode is still one mode for every
    -- platform though (Xbox modern, Xbox 360, Steam — M-Steam-2e, SPEC
    -- 1.4): a platform with no rarity_percent at all (currently only Xbox
    -- 360) is exempt from the rarity check under 'rare' rather than
    -- getting a switch of its own.
    muted_title_ids  TEXT    NOT NULL DEFAULT '[]',
    tz_offset_min    INTEGER,                      -- minutes from UTC, NULL = global timezone
    -- Whether other people's /stats and /who cards get a clickable link in
    -- this person's nickname (Follow-up 2026-09-06). Default off; the admin
    -- picks what new users start with via app_settings, same pattern as
    -- default_rarity_mode (repo.py's ensure_user). /panel is exempt — it's
    -- only ever shown to its own owner, always shows links there.
    show_profile_links INTEGER NOT NULL DEFAULT 0,
    -- This person's own language, for DMs only (/panel, /stats in a DM,
    -- personal notifications) — a group always follows chat_settings.locale
    -- instead, see there (#48). Deliberately not seeded from Telegram's own
    -- language_code: plenty of this Russian-speaking community run Telegram
    -- itself in English, and auto-switching them would be a silent
    -- regression rather than a feature. Explicit opt-in, default 'ru'.
    locale           TEXT    NOT NULL DEFAULT 'ru'
);

-- Rare-achievement threshold, daily-summary time and its timezone are always
-- explicit per chat (SPEC 5.5, 5.7) — briefly shared via app_settings with a
-- NULL-means-"follow the global value" fallback, reverted once real multi-
-- chat use showed chats want genuinely different values, not one shared
-- knob that moves every chat at once on every edit. No *admin-controlled*
-- rarity mode column here — that used to gate publication alongside the
-- person's own choice (an AND of the two), dropped as redundant. The
-- person's own choice does live per chat, just not here: `subscriptions.
-- rarity_mode` (SPEC 9, M-Steam-2e's follow-up) — this table only supplies
-- the threshold number for what "rare" means once someone picks it.
CREATE TABLE IF NOT EXISTS chat_settings (
    chat_id                INTEGER PRIMARY KEY REFERENCES chats(chat_id) ON DELETE CASCADE,
    min_gamerscore          INTEGER NOT NULL DEFAULT 0,
    daily_summary           INTEGER NOT NULL DEFAULT 1,
    muted_title_ids         TEXT    NOT NULL DEFAULT '[]',
    rare_threshold_percent  REAL    NOT NULL DEFAULT 10,
    daily_summary_time      TEXT    NOT NULL DEFAULT '20:00',
    -- Offset, not a zone name — same reasoning as user_settings.tz_offset_min:
    -- unambiguous, and Russia has had no DST since 2014 so a fixed offset
    -- never drifts for this audience.
    tz_offset_min            INTEGER NOT NULL DEFAULT 180,
    -- Anti-flood (2026-09-09 user request): once `flood_limit` achievements
    -- have been individually notified for the same person in this chat
    -- within `flood_window_minutes`, further ones stop posting on their own
    -- and accumulate instead, to be flushed as one combined digest once the
    -- window closes (poller/flood_flush.py, notification_throttle below).
    -- `flood_limit = 0` disables the filter for this chat entirely — same
    -- "0 = off" convention as min_gamerscore/summary_top_limit.
    flood_limit              INTEGER NOT NULL DEFAULT 3,
    flood_window_minutes     INTEGER NOT NULL DEFAULT 60,
    -- Multi-language (#48). One locale per *chat*, not per viewer: Telegram
    -- cannot show two people reading the same group message different text,
    -- so everything this bot broadcasts into a group needs one shared
    -- answer, set by an admin. A person's DMs follow user_settings.locale
    -- instead.
    locale                   TEXT    NOT NULL DEFAULT 'ru'
);

-- Global settings the admin turns
CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_by INTEGER,
    updated_at TEXT NOT NULL
);

-- Deduplication: what we have already seen. Keyed by the **account** that
-- earned it (#52, 2026-09-12), not by the person who happened to have that
-- account linked at the time. Keying by tg_id was the older answer to "one
-- person, several platforms" (M-Steam-2, SPEC 9) and it broke the moment a
-- person swapped one account for another on the same platform: title_id and
-- achievement_id are not account-specific, so a second account's genuinely
-- new unlock collided with the first account's row and was silently dropped
-- by INSERT OR IGNORE — never published, never counted (#29).
--
-- A person's achievements are now "every row belonging to an account they
-- currently have linked", resolved through account_links. An account nobody
-- has linked is invisible everywhere; the moment someone links it, its whole
-- history is theirs.
CREATE TABLE IF NOT EXISTS seen_achievements (
    -- The platform-specific account id: XUID / SteamID64 / PSN account_id.
    -- The name is older than the meaning (it has been generic since
    -- M-Steam-2) and is kept deliberately: renaming it would leave migration
    -- 037 selecting a column a brand-new database does not have, since this
    -- file runs in full before any migration.
    xuid            TEXT NOT NULL,
    title_id        TEXT NOT NULL,
    achievement_id  TEXT NOT NULL,
    name            TEXT,
    description     TEXT,
    icon_url        TEXT,
    unlocked_at     TEXT,               -- UTC
    gamerscore      INTEGER,
    rarity_percent  REAL,               -- NULL on Xbox 360 and Steam
    platform        TEXT NOT NULL DEFAULT 'xbox_modern'
                    CHECK (platform IN ('xbox_modern', 'xbox_360', 'steam', 'psn')),
    is_backfill     INTEGER NOT NULL DEFAULT 0,  -- arrived via backfill, never published
    is_secret       INTEGER NOT NULL DEFAULT 0,  -- Xbox's own isSecret; name/description are
                                                  -- real either way, we're the ones who spoiler it
    -- Which trophy group this came from — 'default' for the base game, then
    -- '001'... per DLC (#46). PSN only; NULL everywhere else, the same way
    -- trophy_type below is. The trophy itself reports it, so it costs
    -- nothing to keep and is what makes "3/7 in this DLC" answerable.
    trophy_group_id TEXT,
    trophy_type     TEXT,                -- PSN's tier (bronze/silver/gold/platinum), NULL
                                          -- elsewhere — new dimension, no analogue on any other
                                          -- platform (M-PSN-1's design notes), M-PSN-2
    created_at      TEXT NOT NULL,
    -- Which `accounts` row this belongs to. Both Xbox generations are one
    -- account and one platform as far as a person is concerned (#52, owner
    -- decision: they bind as a pair and display as one everywhere), while
    -- `platform` above keeps the distinction the achievement contract, the
    -- missing rarity data and the box-art substitution all still need.
    -- GENERATED so the two can never drift apart, and so none of the ~60
    -- places that branch on xbox_modern/xbox_360 had to change.
    account_platform TEXT GENERATED ALWAYS AS (
        CASE WHEN platform IN ('xbox_modern', 'xbox_360') THEN 'xbox' ELSE platform END
    ) STORED,
    PRIMARY KEY (platform, xuid, title_id, achievement_id),
    FOREIGN KEY (account_platform, xuid) REFERENCES accounts(platform, external_id)
);
-- The indexes are NOT created here, on purpose — see migration 037 and the
-- note below: this file runs before any migration, so naming a column that
-- only a migration adds crashes startup for every existing database.
-- idx_seen_tg_unlocked is gone with `tg_id` itself (#52): who a row belongs
-- to is account_links' answer now, and the two indexes above are what the
-- reads actually use. Its old comment here explained why it could not be
-- created in this file — _apply_schema() runs the whole file on every
-- startup, before migrations, so a column a migration had not added yet
-- crashed startup (hit for real on the 009->011 upgrade). The hazard is
-- unchanged and worth remembering: nothing in this file may assume a shape
-- that only a migration produces.

-- What was actually published where. Separate from seen_achievements: a user can be
-- subscribed in two chats, and a failure in one must not lose the achievement in the other.
CREATE TABLE IF NOT EXISTS publications (
    chat_id        INTEGER NOT NULL,
    xuid           TEXT NOT NULL,
    title_id       TEXT NOT NULL,
    achievement_id TEXT NOT NULL,
    message_id     INTEGER,
    posted_at      TEXT NOT NULL,
    PRIMARY KEY (chat_id, xuid, title_id, achievement_id)
);

-- Anti-flood state (2026-09-09 user request), one row per (person, chat)
-- currently inside a counting or throttled window — see chat_settings'
-- flood_limit/flood_window_minutes above and poller/flood_flush.py. Scoped
-- to the whole person, not per platform: someone flooding a chat with mixed
-- Xbox/Steam/PSN unlocks is still one person spamming that chat.
-- `throttled = 0` just means "counting, nothing buffered yet" — the window
-- naturally lapses and gets replaced the next time an achievement arrives
-- with no cleanup needed. `throttled = 1` means further achievements this
-- window are left unpublished (buffered) instead of sent; poller/
-- flood_flush.py finds them again via publications' own absence, not a
-- separate queue table — an achievement not yet in `publications` for this
-- chat already means "not sent there yet", so there is nothing new to store
-- beyond the window's own start time.
CREATE TABLE IF NOT EXISTS notification_throttle (
    tg_id             INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    chat_id           INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    window_started_at TEXT    NOT NULL,
    count_in_window   INTEGER NOT NULL DEFAULT 0,
    throttled         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tg_id, chat_id)
);

-- Presence state — the polling engine
CREATE TABLE IF NOT EXISTS presence_state (
    xuid             TEXT PRIMARY KEY,
    state            TEXT,     -- Online / Offline
    title_id         TEXT,
    title_name       TEXT,
    changed_at       TEXT,     -- when title_id or state last changed
    last_ach_poll_at TEXT,     -- when achievements were last fetched (debounce)
    updated_at       TEXT
);

-- Steam's own presence (M-Steam-2c, SPEC 9) — separate table, not a reuse of
-- presence_state above: different shape (persona_state/gameid, not
-- state/title_id) and its own debounce, keyed by steam_id like the Xbox one
-- is keyed by xuid.
CREATE TABLE IF NOT EXISTS steam_presence_state (
    steam_id              TEXT PRIMARY KEY,
    persona_state         INTEGER,  -- Steam's own enum, 0=offline..6
    gameid                TEXT,     -- NULL when not in a game, right now
    game_name             TEXT,     -- gameextrainfo at the moment of the last change
    changed_at            TEXT,
    last_ach_poll_at      TEXT,
    updated_at            TEXT,
    -- Sticky through brief gaps, unlike gameid/game_name above: Steam's own
    -- presence intermittently stops reporting gameid for a few minutes even
    -- while someone keeps playing (found live — an achievement sat unseen
    -- for ~19 minutes because of exactly this). last_active_* remembers the
    -- last game we actually confirmed them in, and when, so the poller can
    -- keep checking it through a short gap instead of going idle
    -- (poller/steam_presence.py's grace period). Never read for /online —
    -- that still wants the raw, un-extended gameid above.
    last_active_gameid    TEXT,
    last_active_game_name TEXT,
    last_active_at        TEXT
);

-- PSN's own presence (issue #1, 2026-09-08) — separate table, not a reuse
-- of presence_state/steam_presence_state: its own poller, no achievement-
-- poll debounce at all (trophy sync has never been driven by presence
-- here — see this file's own PSN section in CLAUDE.md), keyed by
-- account_id like the other two are keyed by xuid/steam_id.
CREATE TABLE IF NOT EXISTS psn_presence_state (
    account_id TEXT PRIMARY KEY,
    state      TEXT,     -- Online / Offline, same vocabulary as presence_state
    title_id   TEXT,     -- npTitleId
    title_name TEXT,
    changed_at TEXT,
    updated_at TEXT
);

-- Title history cache (for /stats, /compare, /top)
CREATE TABLE IF NOT EXISTS title_history (
    xuid                  TEXT NOT NULL,
    title_id              TEXT NOT NULL,
    current_gamerscore    INTEGER,
    max_gamerscore        INTEGER,
    achievements_unlocked INTEGER,
    achievements_total    INTEGER,
    minutes_played        INTEGER,
    last_played_at        TEXT,
    updated_at            TEXT NOT NULL,
    PRIMARY KEY (xuid, title_id)
);

CREATE TABLE IF NOT EXISTS titles (
    title_id   TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    platform   TEXT,               -- xbox_360 / xbox_modern
    -- The game's own box art (titlehub's display_image), not an achievement
    -- icon — used as a stand-in icon for Xbox 360 achievement messages
    -- (fetcher.py's ensure_title_icon): contract 1 only ever gives a bare
    -- imageId int for an achievement, no documented way to turn it into a
    -- URL (verified live against the real API).
    icon_url   TEXT,
    -- How many achievements/trophies the game has in total (#46) — the
    -- denominator of the "47/50" beside a notification's game line. Only
    -- PSN fills it: Xbox states its own total per account in title_history,
    -- and Steam's is the length of its cached schema, so those two have an
    -- answer already. NULL until a platform that needs this one says so.
    achievements_total INTEGER,
    updated_at TEXT NOT NULL
);

-- HowLongToBeat lookups (SPEC 6.6), keyed by HLTB's own game id — cached
-- forever once someone actually picks a search result.
CREATE TABLE IF NOT EXISTS hltb_cache (
    hltb_id             INTEGER PRIMARY KEY,
    name                TEXT NOT NULL,
    release_year        INTEGER,
    main_hours          REAL,
    extra_hours         REAL,
    completionist_hours REAL,
    platforms           TEXT NOT NULL DEFAULT '[]',  -- JSON list, HLTB's profile_platforms
    game_url            TEXT,  -- game_web_link — the HLTB page itself
    image_url           TEXT,  -- game_image_url — HLTB's own cover art
    genre               TEXT,  -- HLTB's own profile_genre, comma-separated as HLTB writes it
    -- The game's own summary, HLTB's profile_summary (#2). English is what
    -- HLTB actually publishes; the Russian side is a one-off LLM translation
    -- of it, kept beside the original so a locale switch never re-pays for
    -- the same game. Either may be NULL: HLTB has no summary for every entry,
    -- and the translation is skipped entirely when no Anthropic key is set.
    description_en      TEXT,
    description_ru      TEXT,
    cached_at           TEXT NOT NULL
);

-- A PlayStation trophy list is split into groups: the base game plus one per
-- DLC (#46). A trophy says which group it came from, so a notification can
-- say which part of the game somebody is progressing through — but the
-- group's own name and size come from a separate call, made once per game
-- and cached here forever, the same way steam_schema_cache works.
--
-- PSN only: Xbox and Steam have no notion of groups.
CREATE TABLE IF NOT EXISTS title_groups (
    title_id   TEXT NOT NULL,     -- np_communication_id
    group_id   TEXT NOT NULL,     -- 'default' for the base game, then '001'...
    name       TEXT,
    total      INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (title_id, group_id)
);

-- Which chats already got their summary for a given day: the job wakes up every
-- minute, and without this a restart at the wrong moment would send it twice.
CREATE TABLE IF NOT EXISTS daily_reports (
    chat_id     INTEGER NOT NULL,
    report_date TEXT NOT NULL,   -- local date of the chat's timezone
    sent_at     TEXT NOT NULL,
    PRIMARY KEY (chat_id, report_date)
);

-- Every message the bot has sent to a group chat (SPEC 6.4) — Telegram gives
-- a bot no way to list its own past messages, only to delete by message_id
-- one at a time, so without this log there is nothing for the admin panel's
-- "стереть сообщения бота" to delete. Logged by a request middleware
-- (bot/services/message_log.py), not scattered calls in every handler.
CREATE TABLE IF NOT EXISTS bot_messages (
    chat_id    INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    message_id INTEGER NOT NULL,
    sent_at    TEXT NOT NULL,
    -- 1 = an intermediate/system message (prompt, confirmation, /help, the
    -- group hub, etc.) — a candidate for poller/message_cleanup.py's own
    -- auto-delete. 0 = one of the "stats" results (2026-09-05 follow-up:
    -- /stats, /recent, /summary + the daily итог, achievement messages,
    -- /online, /hltb's game card) — never auto-deleted. Set by
    -- MessageLogMiddleware from a ContextVar (services/message_log.py's
    -- own stats_category()), not passed in by each caller — defaults to 1
    -- (system) so a call site that forgets to mark itself fails safe by
    -- disappearing rather than by lingering forever.
    is_system  INTEGER NOT NULL DEFAULT 1,
    -- First couple of non-blank lines of the message's own text/caption
    -- (2026-09-09 user request) — /delete_last's own confirmation shows
    -- this back ("Удалено: ...") so repeated deletes in a row are each
    -- individually confirmable instead of a fast-vanishing toast being the
    -- only signal something happened. NULL for anything logged before this
    -- column existed, or a message with no text/caption at all — falls
    -- back to a generic confirmation, never a hard requirement.
    preview    TEXT,
    PRIMARY KEY (chat_id, message_id)
);

-- /online's live-updating table (Follow-up 2026-09-05, poller/online_refresh.py)
-- — one row per chat, not per message: a fresh /online supersedes whatever
-- was auto-refreshing before (the old message just goes stale, harmless).
-- created_at is what the 3h cutoff measures from, independent of how often
-- last_updated_at (the 10-minute refresh clock) has actually ticked.
CREATE TABLE IF NOT EXISTS online_auto_refresh (
    chat_id         INTEGER PRIMARY KEY REFERENCES chats(chat_id) ON DELETE CASCADE,
    message_id      INTEGER NOT NULL,
    created_at      TEXT NOT NULL,
    last_updated_at TEXT NOT NULL
);

-- A platform account, on its own terms (#52, 2026-09-12) — not "a person's
-- Steam", but "this Steam account", whoever currently has it linked. Split
-- out of `users` (Xbox) and the old `platform_links` (Steam/PSN) because
-- achievement history belongs to the account that earned it: a person who
-- swaps accounts must not inherit the previous one's history, and an account
-- that changes hands must take its history along.
--
-- `platform` here is the account's platform, so Xbox is one value: both
-- generations are the same account and the same platform to a person (owner
-- decision). seen_achievements.platform keeps the finer distinction.
CREATE TABLE IF NOT EXISTS accounts (
    platform     TEXT NOT NULL CHECK (platform IN ('xbox', 'steam', 'psn')),
    external_id  TEXT NOT NULL,     -- XUID / SteamID64 / PSN account_id
    -- The naming chains (#51): display_name is the current nickname,
    -- secondary_name that platform's own second step — Xbox's classic
    -- gamertag beside the modern one, Steam's vanity, PSN's previous
    -- online ID.
    display_name TEXT,
    secondary_name TEXT,
    gamerscore   INTEGER,           -- Xbox only, from the profile; NULL elsewhere
    psn_trophy_level INTEGER,       -- PSN only
    -- Whether the shared service credential could actually see this
    -- account's achievements/trophies as of the last check (#5) — NULL
    -- until checked once, then 1/0. A property of the account's own privacy
    -- settings, which is why it lives here and not on the link.
    achievements_visible INTEGER,
    achievements_visible_checked_at TEXT,
    first_seen_at TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (platform, external_id)
);

-- Who has an account linked now, and who had it before (#52). Unlinking
-- flips `is_active` and stamps `unlinked_at`; nothing is ever deleted, so
-- "which account was linked before this one" is just a row, and relinking a
-- previously-known account finds its history waiting.
CREATE TABLE IF NOT EXISTS account_links (
    tg_id       INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    platform    TEXT NOT NULL,
    external_id TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    linked_at   TEXT NOT NULL,
    unlinked_at TEXT,
    PRIMARY KEY (tg_id, platform, external_id),
    FOREIGN KEY (platform, external_id) REFERENCES accounts(platform, external_id)
);
-- One account per platform per person — **this single index is the only
-- thing enforcing that limit**. Dropping it is what multi-account support
-- (#10) needs; no query in the codebase assumes at most one active link.
CREATE UNIQUE INDEX IF NOT EXISTS idx_links_one_active_per_platform
    ON account_links(tg_id, platform) WHERE is_active = 1;
-- An account has at most one current owner, which is what makes a takeover
-- well-defined: linking an account somebody else holds deactivates their
-- link (and tells them), rather than quietly producing two owners.
CREATE UNIQUE INDEX IF NOT EXISTS idx_links_one_owner
    ON account_links(platform, external_id) WHERE is_active = 1;

-- Steam's own achievement schema for a game (M-Steam-2b, SPEC 9) — not about
-- any one person, one row per appid, JSON-blobbed like hltb_cache.platforms:
-- dozens of achievements per game, not worth a row-per-achievement table.
-- Cached forever, same as hltb_cache — a game's own achievement list/names/
-- icons/secrecy never change between polls.
CREATE TABLE IF NOT EXISTS steam_schema_cache (
    appid           TEXT PRIMARY KEY,
    game_name       TEXT,
    achievements    TEXT NOT NULL,   -- JSON: [{apiname, icon, hidden}] — name/description
                                      -- come from GetPlayerAchievements instead (already
                                      -- localized per person), not duplicated here
    cached_at       TEXT NOT NULL
);

-- Global unlock percentages per achievement (M-Steam-2b) — unlike the schema
-- above, the real percentage drifts over time as more people play, so this
-- one expires (bot/services/steam/achievements.py) instead of living forever.
CREATE TABLE IF NOT EXISTS steam_rarity_cache (
    appid           TEXT PRIMARY KEY,
    percentages     TEXT NOT NULL,   -- JSON: {apiname: percent}
    cached_at       TEXT NOT NULL
);

-- Bilingual achievement/trophy *descriptions* (2026-09-09 user request) —
-- names are never translated, only descriptions. Shared across every person
-- who ever unlocks this achievement, keyed by the achievement itself, not by
-- who unlocked it — seen_achievements is per-person by design (SPEC 9,
-- M-Steam-2) and would otherwise pay the same translation cost (or even the
-- same extra platform request) once per person instead of once ever.
-- `source` records how description_en/description_ru were obtained:
-- 'native' — the platform itself returned two genuinely different strings
-- for the two locales requested (no LLM involved, free); 'llm' — the two
-- came back identical (the platform has no real translation of its own,
-- only a silent fallback to its default language), so the missing side was
-- produced by services/translate. Ordinary achievement descriptions exist
-- on every platform including Xbox 360 (which has no rarity data at all,
-- CLAUDE.md) — nothing here is rarity-related.
CREATE TABLE IF NOT EXISTS achievement_description_cache (
    platform         TEXT NOT NULL,
    title_id         TEXT NOT NULL,
    achievement_id   TEXT NOT NULL,
    description_ru   TEXT,
    description_en   TEXT,
    source           TEXT NOT NULL CHECK (source IN ('native', 'llm')),
    cached_at        TEXT NOT NULL,
    PRIMARY KEY (platform, title_id, achievement_id)
);

-- The single live copy of a self-deduplicating message kind (Follow-up
-- 2026-09-06) — /panel, /summary, /recent and a specific person's /stats
-- card each replace their own previous copy in the same scope instead of
-- piling up: an old one has already scrolled away and nobody scrolls back
-- for it, so keeping only the latest is strictly better than letting
-- repeated commands spam the chat with duplicates. `/online` and `/admin`
-- are NOT here — each already has (or gets, admin_panel_refresh below) its
-- own dedicated one-row-per-scope table because they also auto-refresh in
-- place, which this plain dedup table has no concept of.
-- subject_id is 0 for chat-scoped kinds (summary/recent) or a person's own
-- tg_id for scopes that need one (panel: the owner; stats: the person the
-- card is about, not the requester — SPEC 9's own "по 1 шт на юзера").
CREATE TABLE IF NOT EXISTS tracked_messages (
    chat_id    INTEGER NOT NULL,
    kind       TEXT    NOT NULL CHECK (kind IN ('panel', 'summary', 'recent', 'stats')),
    subject_id INTEGER NOT NULL DEFAULT 0,
    message_id INTEGER NOT NULL,
    updated_at TEXT    NOT NULL,
    PRIMARY KEY (chat_id, kind, subject_id)
);

-- /admin's own live-updating screen (Follow-up 2026-09-06), same shape and
-- reasoning as online_auto_refresh above — one row per admin, not per
-- message: a fresh /admin supersedes whatever was auto-refreshing before
-- (the old message is deleted outright, not just left to go stale, unlike
-- /online's version — an admin only ever has the one panel open at a time,
-- there is no reason to keep a second copy around even briefly).
CREATE TABLE IF NOT EXISTS admin_panel_refresh (
    admin_id        INTEGER PRIMARY KEY,
    message_id      INTEGER NOT NULL,
    created_at      TEXT NOT NULL,
    last_updated_at TEXT NOT NULL
);

-- One game's trophy progress, last time we looked (M-PSN-2) — the only
-- cheap way to know "did anything change here since the last poll" without
-- spending a full trophies() call on every recently-touched game every
-- tick (poller/psn_fetcher.py is not presence-driven at all, unlike Xbox/
-- Steam — see M-PSN-2's own "ключевое отличие" paragraph for why). Updated
-- on every poll, not only when progress actually grew, so a game that
-- stays flat between polls doesn't get expensively re-checked forever.
CREATE TABLE IF NOT EXISTS psn_title_progress (
    account_id           TEXT NOT NULL,
    np_communication_id  TEXT NOT NULL,
    progress             INTEGER NOT NULL,
    updated_at           TEXT NOT NULL,
    PRIMARY KEY (account_id, np_communication_id)
);

-- One row per linked PSN account, when it was last polled (M-PSN-2) — the
-- debounce clock poller/psn_fetcher.py's tick() reads via cadence.py's own
-- debounce_passed(), reusing achievement_poll_interval (Settings) same as
-- Xbox/Steam's own achievement debounce. Separate from psn_title_progress:
-- that one is keyed per (account, game) and only ever touched for games
-- trophy_titles() actually returned, so it can't answer "was this account
-- polled at all" for someone with no trophy activity yet.
--
-- backfill_done gates the regular poller (#21): a freshly-linked account
-- starts at 0 and tick() skips it entirely until backfill() has finished
-- and flipped it to 1. Without the gate, a scheduler tick landing while the
-- fire-and-forget backfill is still running fetches the same trophies
-- backfill hasn't inserted yet and publishes the whole history as if it
-- were just earned.
CREATE TABLE IF NOT EXISTS psn_poll_state (
    account_id     TEXT PRIMARY KEY,
    last_polled_at TEXT NOT NULL,
    backfill_done  INTEGER NOT NULL DEFAULT 0
);
