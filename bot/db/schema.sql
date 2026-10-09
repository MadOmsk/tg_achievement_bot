-- Full schema, SPEC section 3. Applied once to an empty database; later changes
-- go to db/migrations/ so an existing bot.db is never recreated from scratch.

-- People. A person has an id of their own (#156, migration 071); a Telegram
-- account is one way to sign in, kept as `tg_id` — unique, and empty for a
-- person who signs in some other way. The tables about a person point at `id`
-- (078); what is Telegram by nature (`chat_seen`, the admins, the reset
-- cooldowns) keeps a Telegram id. Only the identity lives here
-- (#52): an Xbox account is an `accounts` row like any other, reached through
-- the active link in `account_links`.
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id           INTEGER UNIQUE CHECK (tg_id IS NULL OR tg_id > 0),
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
    -- The person's Telegram profile photo, for the mini-app (2026-09-13).
    -- Telegram's own `file_id` for the largest size, never an image and never
    -- a URL: a file_id is only usable together with the bot token, so the
    -- token stays on the server and this column is not a secret on its own.
    -- `photo_unique_id` is stable per photo, so a refresh can tell "still the
    -- same picture" without downloading it; `photo_checked_at` is stamped on
    -- every check, including one that finds no photo at all (a private
    -- profile), so poller/avatars.py does not ask again tomorrow.
    photo_file_id   TEXT,
    photo_unique_id TEXT,
    photo_checked_at TEXT,
    -- The downloaded copy, relative to data/avatars/ (#55): the mini-app
    -- serves an image rather than round-tripping getFile with the bot token
    -- on every render, and a face outlives whatever Telegram does with its
    -- own file ids.
    photo_path      TEXT,
    -- A picture chosen in the Mini App (#157, migration 077), shown instead.
    custom_avatar_path TEXT,
    -- The person's nickname, the only name shown for them (#157, migration 072):
    -- `handle` as typed ([A-Za-z0-9]{3,20}), `handle_norm` lower-case for
    -- uniqueness, `handle_number` the four digits added when it is taken (0 =
    -- none). The unique constraint is here for new databases; the migration
    -- creates the same index for existing ones.
    handle          TEXT,
    handle_norm     TEXT,
    handle_number   INTEGER NOT NULL DEFAULT 0,
    handle_confirmed_at TEXT,
    handle_changed_at   TEXT,
    -- Who sees this person's activity in the app (#157, migration 073).
    activity_visible TEXT NOT NULL DEFAULT 'all'
        CHECK (activity_visible IN ('all', 'friends', 'nobody')),
    -- An address the person proved with a code, lower-cased (#162, migration
    -- 079): a way to sign in besides Telegram. NULL = none.
    email           TEXT,
    email_linked_at TEXT,
    -- When a person with no email put off adding one (migration 083): the app
    -- asks once, on opening it.
    email_prompted_at TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE (handle_norm, handle_number),
    -- One person per address; here for new databases, migration 079 makes the
    -- same rule an index for existing ones (schema.sql runs before migrations,
    -- so a standalone index on a new column would fail on an old file).
    UNIQUE (email)
);

-- One user, one token. Refresh only; everything else lives in memory.
CREATE TABLE IF NOT EXISTS tokens (
    person_id         INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
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
    person_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    -- Which achievements go out is the person's (user_settings.rarity_mode),
    -- and how many at once make a digest is the chat's
    -- (chat_settings.digest_threshold) — both used to live here, per
    -- subscription, until #126: a person in many chats set the same thing
    -- in each.
    PRIMARY KEY (chat_id, person_id)
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
    person_id        INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    -- Which achievements this person publishes, in every chat they are
    -- subscribed to (#126): 'all', 'rare' (at or below each chat's own
    -- threshold), or 'hidden' — nothing published. Only notifications: the
    -- person still counts in a chat's summaries, rankings and /recent, and
    -- leaving those is unsubscribing (#167). One value for every platform: a platform with no
    -- rarity at all (Xbox 360) is exempt from 'rare' rather than getting a
    -- switch of its own. It was per subscription until #126 — somebody in
    -- many chats had to set the same thing in each.
    rarity_mode      TEXT    NOT NULL DEFAULT 'all'
                     CHECK (rarity_mode IN ('all', 'rare', 'hidden')),
    muted_title_ids  TEXT    NOT NULL DEFAULT '[]',
    tz_offset_min    INTEGER,                      -- minutes from UTC, NULL = global timezone
    -- Whether other people's /stats and /who cards get a clickable link in
    -- this person's nickname (Follow-up 2026-09-06). Default off; the admin
    -- picks what new users start with via app_settings, same pattern as
    -- default_rarity_mode (repo.py's ensure_user). /panel is exempt — it's
    -- only ever shown to its own owner, always shows links there.
    show_profile_links INTEGER NOT NULL DEFAULT 0,
    -- Mini App only: whether this person sees secret achievement names
    -- unspoilered. Off by default. Group posts are unchanged — Telegram
    -- cannot hide a published name from one viewer only.
    show_secrets     INTEGER NOT NULL DEFAULT 0,
    -- This person's own language, for DMs only (/panel, /stats in a DM,
    -- personal notifications) — a group always follows chat_settings.locale
    -- instead, see there (#48). Deliberately not seeded from Telegram's own
    -- language_code: plenty of this Russian-speaking community run Telegram
    -- itself in English, and auto-switching them would be a silent
    -- regression rather than a feature. Explicit opt-in, default 'ru'.
    locale           TEXT    NOT NULL DEFAULT 'ru',
    -- Whether to be told when someone follows this person (#157, migration 075);
    -- no longer read: 088 moved it onto the channels' lists.
    notify_followers INTEGER NOT NULL DEFAULT 1,
    -- Where the app's notifications go (#164, migration 080): pushed to the
    -- devices that allowed it, and as a Telegram DM (only with Telegram linked).
    notify_push      INTEGER NOT NULL DEFAULT 1,
    notify_telegram  INTEGER NOT NULL DEFAULT 1,
    -- Whose posts this person was told about (migration 081); no longer read:
    -- each channel says it in notify_push_on / notify_telegram_on (088).
    notify_posts     TEXT    NOT NULL DEFAULT 'friends'
        CHECK (notify_posts IN ('friends', 'following', 'none')),
    -- A switch per kind (migration 087); no longer read since 088, kept so a
    -- new database has the columns an upgraded one has.
    notify_new_posts INTEGER NOT NULL DEFAULT 1,
    notify_friends   INTEGER NOT NULL DEFAULT 1,
    notify_account   INTEGER NOT NULL DEFAULT 1,
    notify_game_news TEXT    NOT NULL DEFAULT 'all'
        CHECK (notify_game_news IN ('all', 'patch', 'news', 'none')),
    -- The kinds of notice switched on for each channel (migration 088), none
    -- by default; comma-separated keys of services/notifier.py::KINDS, a choice
    -- after a colon where the kind has one (new_post:friends, game_news:patch).
    -- The app's own list keeps every notice.
    notify_push_on      TEXT NOT NULL DEFAULT '',
    notify_telegram_on  TEXT NOT NULL DEFAULT ''
);

-- Rare-achievement threshold, daily-summary time and its timezone are always
-- explicit per chat (SPEC 5.5, 5.7) — briefly shared via app_settings with a
-- NULL-means-"follow the global value" fallback, reverted once real multi-
-- chat use showed chats want genuinely different values, not one shared
-- knob that moves every chat at once on every edit. The person picks the
-- rarity *mode* (user_settings.rarity_mode); this table supplies the
-- threshold that "rare" means in this chat.
CREATE TABLE IF NOT EXISTS chat_settings (
    chat_id                INTEGER PRIMARY KEY REFERENCES chats(chat_id) ON DELETE CASCADE,
    -- No longer read (owner, 2026-10-08): a minimum gamerscore held back
    -- every Steam and PSN achievement, which have none.
    min_gamerscore          INTEGER NOT NULL DEFAULT 0,
    daily_summary           INTEGER NOT NULL DEFAULT 1,
    muted_title_ids         TEXT    NOT NULL DEFAULT '[]',
    rare_threshold_percent  REAL    NOT NULL DEFAULT 10,
    -- This many achievements of one person at once make one digest instead
    -- of separate cards; 99 = never (#126 — it was the person's, per
    -- subscription, before).
    -- No longer read: the digest size is one for every chat (owner,
    -- 2026-10-08), app_settings['digest_threshold'].
    digest_threshold        INTEGER NOT NULL DEFAULT 3,
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
    -- "0 = off" convention as summary_top_limit.
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
    device          TEXT,                -- Specific device/platform where earned (#79, NULL for backfill)
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

CREATE INDEX IF NOT EXISTS idx_seen_achievements_title_id ON seen_achievements(title_id);
-- The indexes on migrated columns (unlocked_at, account_platform) are NOT created here,
-- on purpose — they are `_database.py::INDEXES_AFTER_MIGRATIONS`, made after the
-- migrations on every start. See migration 037 and the note below: this file runs before any migration,
-- so naming a column that only a migration adds crashes startup for every existing database.
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
    person_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chat_id           INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    window_started_at TEXT    NOT NULL,
    count_in_window   INTEGER NOT NULL DEFAULT 0,
    throttled         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (person_id, chat_id)
);

-- Presence state — the polling engine
CREATE TABLE IF NOT EXISTS presence_state (
    xuid             TEXT PRIMARY KEY,
    state            TEXT,     -- Online / Offline
    title_id         TEXT,
    title_name       TEXT,
    device           TEXT,     -- Xbox device (XboxSeriesX, XboxOne, WindowsOneCore, etc.)
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
    device     TEXT,     -- PSN platform/device (PS5, PS4, etc.)
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
    -- One row per version: one achievement list on one platform (#147),
    -- keyed by the platform and its own id as seen_achievements and
    -- title_achievements are — the id spaces overlap (Steam appids run to
    -- ~3.5M, Xbox title ids start below 1M). An Xbox game found to be the
    -- other generation moves, row and achievements together
    -- (`update_title_platform`; migration 090).
    platform   TEXT NOT NULL,     -- xbox_modern / xbox_360 / steam / psn
    title_id   TEXT NOT NULL,
    name       TEXT NOT NULL,     -- whatever the platform called it first
    -- Only PlayStation localizes a game's title (#61, verified live:
    -- "Marvel's Wolverine" / "Marvel: Росомаха"), and it arrives in the same
    -- once-per-game call the trophy groups do. Xbox returns the same title in
    -- both locales while localizing the achievement names in that response,
    -- and Steam's gameName is identical under l=english and l=russian — so
    -- these two columns are PSN's in practice, and somewhere to put it if
    -- another platform ever changes its mind.
    name_ru    TEXT,
    name_en    TEXT,
    platforms  TEXT,               -- JSON array of available platforms from API (#79)
    -- Failed titlehub lookups of `platforms` for an Xbox game, and when the
    -- last one ran (migration 060, #114). After three, `platforms` is '[]'.
    platforms_attempts   INTEGER NOT NULL DEFAULT 0,
    platforms_checked_at TEXT,
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
    -- The downloaded copy of `icon_url` above, and what maps this row to it
    -- (migration 050): a path relative to data/covers/, the sha256 of the
    -- bytes, and when the title was last looked at — stamped even when the
    -- platform offered no art, or a game without any would be asked about
    -- on every tick forever. Filled by poller/covers.py.
    cover_path TEXT,
    cover_hash TEXT,
    cover_checked_at TEXT,
    achievements_checked_at TEXT,
    -- Which HowLongToBeat entry this game is (#131, migration 063): matched
    -- automatically, never chosen by a person — bot/services/hltb_match.py
    -- scores every candidate a search turns up and only keeps one it is
    -- sure of. NULL until matched or given up on (three failed attempts,
    -- same shape as platforms_attempts above); `hltb_match_score` is the
    -- winning score, for telling a confident match from a Steam-appid one
    -- (always 1.0) apart when the operator needs to check by hand.
    hltb_id INTEGER,
    hltb_match_score REAL,
    hltb_attempts INTEGER NOT NULL DEFAULT 0,
    hltb_checked_at TEXT,
    -- The Steam app this game is (migration 069): a Steam game's own title_id,
    -- else looked up once — HLTB's page first, then Steam's store search — and
    -- given up on after three failed attempts, like the HLTB entry above. NULL
    -- also means "has no Steam page" once the attempts are spent.
    steam_appid INTEGER,
    steam_appid_attempts INTEGER NOT NULL DEFAULT 0,
    steam_appid_checked_at TEXT,
    -- When the achievements' tips (title_achievements.tip_*) were last worked
    -- out from the Steam app's guides.
    tips_checked_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (platform, title_id)
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
    -- The rest of the HLTB page (rating, studio, modes, spreads, speedruns),
    -- one JSON object; NULL until the page has been read for it (064).
    details             TEXT,
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
    name       TEXT,              -- whatever was stored first; the fallback
    -- Sony localizes these, unlike the game's own title (#61, verified live:
    -- "CTNS: The Heist" / "Город, который никогда не спит: Ограбление") — and
    -- the group name is the second line of every PSN card, so in a Russian
    -- chat it was the one English thing left on it. Both sides come from the
    -- same once-per-game call, made twice.
    name_ru    TEXT,
    name_en    TEXT,
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
    -- 1 = an achievement/trophy notification, single or digest (#101) —
    -- the one kind /delete_last must never take, whatever else it deletes.
    -- Set by MessageLogMiddleware from services/message_log.py's own
    -- achievement_category(), which the publisher wraps its delivery in.
    is_achievement INTEGER NOT NULL DEFAULT 0,
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
    -- The account's own picture (#55): Xbox's GameDisplayPicRaw, Steam's
    -- avatarfull, PSN's own avatars list — all three ride along in a
    -- response the bot already makes. `avatar_url` is what the platform
    -- says now, `avatar_path` the copy on disk (relative to data/avatars/),
    -- `avatar_hash` the bytes, so "same picture, new URL" costs one
    -- comparison and no write.
    avatar_url   TEXT,
    avatar_path  TEXT,
    avatar_hash  TEXT,
    avatar_checked_at TEXT,
    first_seen_at TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (platform, external_id)
);

-- Who has an account linked now, and who had it before (#52). Unlinking
-- flips `is_active` and stamps `unlinked_at`; nothing is ever deleted, so
-- "which account was linked before this one" is just a row, and relinking a
-- previously-known account finds its history waiting.
CREATE TABLE IF NOT EXISTS account_links (
    person_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform    TEXT NOT NULL,
    external_id TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    linked_at   TEXT NOT NULL,
    unlinked_at TEXT,
    -- Whether this account's achievements are announced in the person's chats
    -- (#20): the person's own switch, per account — with several PSN accounts
    -- (#10) each has its own. A muted account still counts in stats,
    -- summaries and /online; it only stops posting.
    publishes   INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (person_id, platform, external_id),
    FOREIGN KEY (platform, external_id) REFERENCES accounts(platform, external_id)
);
-- One account per platform per person — except PSN, where a person may
-- hold up to three (#10; the limit of three is enforced in code, not here).
CREATE UNIQUE INDEX IF NOT EXISTS idx_links_one_active_per_platform
    ON account_links(person_id, platform) WHERE is_active = 1 AND platform <> 'psn';
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

-- Full game achievement catalog (Issue #99, 2026-09-22) — stores all achievements
-- of a title (both unlocked and locked), with bilingual names and descriptions,
-- icons, secrecy, gamerscore, trophy tiers and rarity. Shared across all users,
-- keyed by the achievement itself, never by who unlocked it.
--
-- The one store of these facts (#119): it absorbed the description, name and
-- rarity caches that predated it (migration 062). A row may be partial — a
-- poll that learned only names or a percentage writes just those — and the
-- catalog refresh (services/title_catalog.py) fills in the rest.
--
-- Names are the platform's own strings, never translated. `rarity_percent` is
-- the latest the platform reported; `seen_achievements.rarity_percent` is only
-- a snapshot from the first unlock here and the fallback. A year-old
-- percentage is worth more than none, so nothing here expires.
CREATE TABLE IF NOT EXISTS title_achievements (
    platform        TEXT NOT NULL CHECK (platform IN ('xbox_modern', 'xbox_360', 'steam', 'psn')),
    title_id        TEXT NOT NULL,
    achievement_id  TEXT NOT NULL,
    name_ru         TEXT,
    name_en         TEXT,
    description_ru  TEXT,
    description_en  TEXT,
    icon_url        TEXT,
    is_secret       INTEGER NOT NULL DEFAULT 0,
    gamerscore      INTEGER,
    trophy_type     TEXT,
    trophy_group_id TEXT,
    rarity_percent  REAL,
    updated_at      TEXT NOT NULL,
    -- How the two descriptions were obtained, once they went through
    -- services/translate/descriptions.py; NULL until then.
    -- native: the platform returned two genuinely different strings.
    -- llm: it returned the same one twice (no translation exists there), so
    --   services/translate filled the gap.
    -- fallback: same as llm's case, but nothing could translate it yet — no
    --   Anthropic key, or the call failed. The text is shown untranslated,
    --   `description_ru` stays NULL, and the row is offered to the translator
    --   again; the other two never are.
    description_source TEXT CHECK (description_source IN ('native', 'llm', 'fallback')),
    -- 1 once the catalog's own writer (upsert_title_achievements) wrote the
    -- row, i.e. it is known to be one of the game's achievements with its name
    -- and icon. A row a poll created to hold just a percentage, a name or a
    -- description stays 0 — it is not counted as the game's list, or a list
    -- of one person's unlocks would pass for the whole game (#119).
    listed          INTEGER NOT NULL DEFAULT 0,
    -- How to get it, from the Steam community's guides (migration 069): the
    -- text sits in the column of its own language, the other is NULL until a
    -- translation fills it (`tip_translation` then says 'llm'). `tip_source`
    -- is the guide's Steam id.
    tip_en          TEXT,
    tip_ru          TEXT,
    tip_source      TEXT,
    tip_translation TEXT CHECK (tip_translation IN ('llm')),
    PRIMARY KEY (platform, title_id, achievement_id)
);

-- One Steam app's guides and patch notes (migration 069) — an Xbox, a
-- PlayStation and a Steam version of one game share them, so they are read
-- once for all. `*_checked_at` say when each was last read in full.
CREATE TABLE IF NOT EXISTS steam_apps (
    appid              INTEGER PRIMARY KEY,
    guides_checked_at  TEXT,
    patches_checked_at TEXT
);

-- What the model answered about one guide for one game (migration 070): the
-- fingerprint of what it was asked and the answer, each achievement's line ranges
-- as JSON. The model is asked again only when the fingerprint changes.
CREATE TABLE IF NOT EXISTS title_guide_reads (
    platform    TEXT    NOT NULL,   -- the game's, as `titles` (090)
    title_id    TEXT    NOT NULL,
    guide_id    TEXT    NOT NULL,
    fingerprint TEXT    NOT NULL,
    answer      TEXT    NOT NULL,
    checked_at  TEXT    NOT NULL,
    PRIMARY KEY (platform, title_id, guide_id)
);

-- A Steam app's latest patch notes, from its developer's announcements.
-- `*_ru` stay NULL until a translation fills them.
CREATE TABLE IF NOT EXISTS game_patches (
    steam_appid  INTEGER NOT NULL,
    gid          TEXT    NOT NULL,
    title        TEXT    NOT NULL,
    published_at TEXT    NOT NULL,
    text_en      TEXT,
    title_ru     TEXT,
    text_ru      TEXT,
    created_at   TEXT    NOT NULL,
    -- A patch, or any other post of the developer's (migration 084): the
    -- Mini App's «Новости» lists both, the game page only the patches.
    kind         TEXT    NOT NULL DEFAULT 'patch' CHECK (kind IN ('patch', 'news')),
    -- The post's first picture, for its card.
    image_url    TEXT,
    PRIMARY KEY (steam_appid, gid)
);

CREATE INDEX IF NOT EXISTS idx_game_patches_published
    ON game_patches(steam_appid, published_at);


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
    -- 'summary_day'/'summary_month': one slot per report (058); 'summary'
    -- only for rows the removed /summary left behind.
    kind       TEXT    NOT NULL CHECK (
        kind IN ('panel', 'summary', 'summary_day', 'summary_month', 'recent', 'stats')
    ),
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

-- Platform cooldowns for anti-abuse protection on account resets/re-links.
CREATE TABLE IF NOT EXISTS platform_cooldowns (
    tg_id          INTEGER NOT NULL,
    platform       TEXT NOT NULL,
    external_id    TEXT,
    reset_count    INTEGER NOT NULL DEFAULT 1,
    last_reset_at  TEXT NOT NULL,
    -- PSN only (068): re-links allowed free after a deletion (the accounts
    -- held then), and re-links made since.
    free_relinks   INTEGER NOT NULL DEFAULT 1,
    relinks        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tg_id, platform)
);

CREATE INDEX IF NOT EXISTS idx_platform_cooldowns_ext
    ON platform_cooldowns(platform, external_id);

-- The reset count of each account (#10: every PSN account protected on its own).
CREATE TABLE IF NOT EXISTS platform_cooldown_accounts (
    platform       TEXT NOT NULL,
    external_id    TEXT NOT NULL,
    tg_id          INTEGER NOT NULL,
    reset_count    INTEGER NOT NULL DEFAULT 1,
    last_reset_at  TEXT NOT NULL,
    PRIMARY KEY (platform, external_id)
);

-- Follows and blocks (#157, migration 073) point at the person id. Friends are two
-- follows facing each other, not a row.
CREATE TABLE IF NOT EXISTS follows (
    follower_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    followee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (follower_id, followee_id),
    CHECK (follower_id != followee_id)
);
CREATE INDEX IF NOT EXISTS idx_follows_followee ON follows (followee_id);

CREATE TABLE IF NOT EXISTS blocks (
    person_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    blocked_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (person_id, blocked_id),
    CHECK (person_id != blocked_id)
);
CREATE INDEX IF NOT EXISTS idx_blocks_blocked ON blocks (blocked_id);

-- Per pair: the last follow DM (one a day) and the last unfollow (a re-follow waits
-- ten minutes) — #157, migration 076.
CREATE TABLE IF NOT EXISTS follow_log (
    follower_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    followee_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    notified_at   TEXT,
    unfollowed_at TEXT,
    PRIMARY KEY (follower_id, followee_id)
);

-- Browser sessions (#157, migration 074): only a hash of the cookie's token.
CREATE TABLE IF NOT EXISTS web_sessions (
    token_hash   TEXT PRIMARY KEY,
    person_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at   TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    user_agent   TEXT
);
CREATE INDEX IF NOT EXISTS idx_web_sessions_person ON web_sessions (person_id);

-- Passkeys (migration 089): a key kept on a phone or a computer that signs its
-- person in, in place of an email's code. Only the public half is kept.
CREATE TABLE IF NOT EXISTS passkeys (
    id            TEXT PRIMARY KEY,
    person_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    public_key    BLOB NOT NULL,
    sign_count    INTEGER NOT NULL DEFAULT 0,
    transports    TEXT,
    name          TEXT,
    created_at    TEXT NOT NULL,
    last_used_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_passkeys_person ON passkeys (person_id);


-- One-time sign-in codes sent by email (#162, migration 079). Only an HMAC of
-- the code is kept; `person_id` is set when a signed-in person adds the address
-- (purpose 'link'), NULL for a sign-in.
CREATE TABLE IF NOT EXISTS email_codes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT NOT NULL,
    purpose     TEXT NOT NULL CHECK (purpose IN ('sign_in', 'link')),
    person_id   INTEGER REFERENCES users(id) ON DELETE CASCADE,
    code_hash   TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    used_at     TEXT,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_email_codes_email ON email_codes (email, created_at);

-- The app's own notifications (#164, migration 080): the list kept per person,
-- worded on reading.
CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    -- What the text is made from (who, which game…), JSON; worded on reading,
    -- in the reader's language at that moment.
    data        TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    read_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_notifications_person ON notifications (person_id, id);

-- One row per browser that allowed push (#164). `endpoint` is the push
-- service's address for that browser; `p256dh`/`auth` are its keys.
-- Invites (migration 082): a code a member made lets one new person sign up in
-- a browser — by email or Telegram's Login Widget. Inside Telegram nobody needs
-- one.
CREATE TABLE IF NOT EXISTS invites (
    code        TEXT PRIMARY KEY,
    created_by  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    used_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    used_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_invites_created_by ON invites (created_by, created_at);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    endpoint    TEXT PRIMARY KEY,
    person_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    p256dh      TEXT NOT NULL,
    auth        TEXT NOT NULL,
    user_agent  TEXT,
    created_at  TEXT NOT NULL,
    last_ok_at  TEXT,
    failures    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_push_subscriptions_person ON push_subscriptions (person_id);

-- Video guides from YouTube channels (owner, 2026-10-06; migration 086): every video of a
-- guide channel, and the moments its description marks — a timeline line,
-- or the whole video when its title names one achievement. Matched to our
-- achievements when a page asks, by exact name within the game, so nothing
-- here points at a game or an achievement of ours.
CREATE TABLE IF NOT EXISTS guide_channels (
    channel_id      TEXT PRIMARY KEY,
    uploads_id      TEXT,
    -- Where the first pass through the channel's history stopped.
    backfill_token  TEXT,
    backfill_done   INTEGER NOT NULL DEFAULT 0,
    checked_at      TEXT,
    -- When the last pass through the whole history ended: it is made again
    -- weekly, since a timeline is often added to a video long after upload.
    read_through_at TEXT
);

CREATE TABLE IF NOT EXISTS guide_videos (
    video_id      TEXT PRIMARY KEY,
    channel_id    TEXT NOT NULL,
    title         TEXT NOT NULL,
    -- The title's parts between " - ", each normalized, joined by " | ":
    -- a game is found by its name being the first part(s).
    title_key     TEXT NOT NULL,
    published_at  TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_guide_videos_key ON guide_videos (title_key);

CREATE TABLE IF NOT EXISTS guide_marks (
    video_id       TEXT NOT NULL REFERENCES guide_videos (video_id) ON DELETE CASCADE,
    -- What the moment is about, normalized as an achievement's name is.
    label          TEXT NOT NULL,
    start_seconds  INTEGER NOT NULL,
    -- "– PART 2" in a timeline; 0 when the line names no part.
    part           INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (video_id, label, start_seconds)
);
CREATE INDEX IF NOT EXISTS idx_guide_marks_label ON guide_marks (label);

-- ------------------------------------------------------------------ the store side (#147)
-- What each store says about a game: versions (a store product on one
-- console), DLC, HLTB entries, the raw answers and when to ask again
-- (migration 091). No foreign key points at `titles`.

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

-- ------------------------------------------------------------------ games (#147, stage 3)
-- A game over its versions; the link's kind, its state (linked / review /
-- rejected) and who decided it — the matcher rewrites only its own rows
-- (migration 092). A remake is another game, linked game -> game.

CREATE TABLE IF NOT EXISTS games (
    game_id     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    name_ru     TEXT,
    year        INTEGER,
    name_source TEXT NOT NULL DEFAULT 'auto',   -- auto / manual
    merged_into INTEGER REFERENCES games(game_id),  -- an old id keeps resolving
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS version_games (
    version_id INTEGER NOT NULL REFERENCES versions(version_id) ON DELETE CASCADE,
    game_id    INTEGER NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,   -- version / edition / remaster / compilation / demo
    state      TEXT NOT NULL,   -- linked / review / rejected
    source     TEXT NOT NULL,   -- auto / manual
    score      REAL,
    reasons    TEXT,            -- JSON list: the signals that decided it
    decided_by TEXT,
    decided_at TEXT NOT NULL,
    PRIMARY KEY (version_id, game_id)
);
CREATE INDEX IF NOT EXISTS idx_version_games_game ON version_games(game_id, state);

CREATE TABLE IF NOT EXISTS game_relations (
    game_id    INTEGER NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    related_id INTEGER NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,   -- remake_of
    source     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (game_id, related_id, kind),
    CHECK (game_id <> related_id)
);
