# CLAUDE.md

## Project

Achievement Bot is a Telegram bot for a small, non-commercial gaming community
(roughly 20-30 people). It publishes newly unlocked achievements and trophies from
connected Xbox, Steam, and PlayStation Network accounts, with per-chat rarity
filters, personal stats, an admin panel, daily summaries, HowLongToBeat lookup,
and a Telegram Mini App.

This file is the single source of truth for current behavior, invariants, and open
work — read it in full before making product or architecture changes, and **keep it
current**: when a change alters something this file states (a rule, an invariant, the
file tree, a data model detail), update the relevant section in the same change, not
as a follow-up. A stale source of truth is worse than none — it gets trusted anyway.

**How this file is written** (owner, 2026-09-24). It is maintained mostly by an AI
and read in full every session, so each entry is **the rule, a short why, and a
link** — not the story of how the rule was found. Incidents, measurements, dates
and rejected first attempts go into GitHub issues: open work into open issues,
history into closed ones (`state_reason: completed`, one per logical unit of work,
see #6-#13 for the shape). The text this file carried before it was compressed is
kept verbatim in the design logs **#106** (Data model), **#107** (Platform
integrations), **#108** (Polling model, Publication rules), **#109** (User
interface), **#110** (Message formats), **#111** (Lists and tables, Statistics
rules) and **#112** (Versioning, Operations, HLTB, Security, Engineering rules).
When a rule needs its backstory, follow the link; do not paste the story back in.

The rejected-ideas appendix at the end is narrower than design rationale:
alternatives that were tried or considered and specifically rejected.

Keep the project working after every change — no step should leave it broken. The
product is optimized for one trusted operator, a single SQLite database, explicit
admin controls, and predictable behavior, not public SaaS scale.

### Non-goals

- No public web UI outside Telegram. The only browser surfaces are the Microsoft
  OAuth callback and the Telegram Mini App (`webapp/`, served separately; this
  process only answers `/api/mini/*` next to `/auth/callback`). Slash commands and
  chat notifications stay — the Mini App is an extra door, not a replacement.
- No `/compare` or `/top` (see the appendix).
- No per-platform visibility toggles: one `rarity_mode` per person per chat, for
  every platform (see the appendix).
- No live platform API calls from normal read-only commands or panels.
- No multi-tenant hosting model.

## Stack

Python 3.12+, aiogram 3, aiohttp (OAuth callback + Mini App API), httpx (platform
HTTP clients), aiosqlite, APScheduler (`AsyncIOScheduler`), pydantic v2 +
pydantic-settings, cryptography Fernet, xbox-webapi-python, the official Steam Web
API, psnawp (PSN), howlongtobeatpy, pytest + pytest-asyncio + ruff. The Mini App is
Vite + React (`webapp/`).

## Repository layout

Tracked files (`git ls-files`) and what each is for. `db/migrations/`, `tests/`,
`webapp/src/`, `bot/locales/` and `changelog/` are not listed file by file — their
names say enough. Update this tree whenever a file's purpose isn't obvious from its
name, or when the tree goes stale.

```text
.
├── .env.example / .env.test.example   environment templates (prod / test server; the dev
│                                       server keeps its own local .env.test)
├── .github/workflows/ci.yml   CI on every push; deploys `prerelease` → test server, `main` → prod (#4)
├── README.md / README.ru.md   the overview, in English and in Russian
├── CLAUDE.md                  this file
├── pyproject.toml             dependencies, ruff, pytest config
├── manage.ps1 / manage.bat    the dev server's process manager and its double-click dashboard
├── webapp/                    Telegram Mini App SPA (Vite/React); built by CI, never served by the bot
├── changelog/                 release notes per version: `<v>.ru.md` / `.en.md` (what a chat member
│                              notices), `.summary.<locale>.txt` (the announcement's bullets),
│                              `.contributors.md` (what changed about working here)
│
├── bot/
│   ├── main.py                  entry point, assembly, router registration
│   ├── config.py                settings from the environment (pydantic-settings)
│   ├── lock.py                  "one process per .env" guard
│   ├── util.py                  small helpers (UTC time, secret masking)
│   ├── constants.py             shared enums: platforms, badges, setting keys
│   ├── version.py               A.B.C.D and the "database newer than code" refusal (#56)
│   ├── i18n.py                  Fluent/aiogram_i18n wiring; `ru` is the default
│   ├── locales/                 ru/ (default and per-key fallback) and en/, both complete (#48)
│   │
│   ├── handlers/                aiogram routers — routing and actions only: no SQL, no platform
│   │   │                        API calls, no layout (#63)
│   │   ├── connect.py            /start, /connect_xbox, /disconnect_xbox
│   │   ├── steam.py, psn.py      /connect_* and /disconnect_* for Steam and PSN
│   │   ├── awaiting.py           whose next private message is a profile link, for which platform
│   │   ├── panel.py              the personal panel, "Мои чаты"
│   │   ├── chat.py               group commands and the group hub
│   │   ├── admin.py              /admin, bulk message wipe
│   │   ├── hltb.py               /hltb
│   │   └── delivery.py           safe_edit + the notice to an account's previous owner
│   │
│   ├── views/                   every screen's layout, one module per screen (#63): a view reads the
│   │   │                        database and renders a `Screen` (text, keyboard, photo/gallery), never
│   │   │                        sends and never decides when it is shown
│   │   ├── panel.py, chat.py, admin.py, admin_home.py, online.py, summary.py,
│   │   │   notification.py, hltb.py      one per screen (admin_home and online are redrawn on timers)
│   │   ├── keyboards.py          every inline keyboard, the close button, format_* helpers
│   │   ├── parts.py              shared vocabulary: badges, platform palette, counted nouns,
│   │   │                         per-platform header rows, value brackets
│   │   ├── lists.py              what every *text* list shares (#64)
│   │   ├── inline_lists.py       what every *keyboard* list shares: rows, paging, navigation, way out
│   │   └── date_picker.py        calendar pickers and month/day navigation (#75)
│   │
│   ├── services/                business logic; knows nothing about Telegram/aiogram
│   │   ├── achievements.py       whether an achievement may be published
│   │   ├── admin_settings.py     what the admin settings *are*: bounds, labels, defaults
│   │   ├── connect.py            one-time OAuth state, finishing a login
│   │   ├── relink.py             linking an account somebody else may already hold (#52)
│   │   ├── stats.py              aggregates for panels, /stats, summaries
│   │   ├── models.py, rows.py    ParsedAchievement and its AchievementRow, shared by all platforms
│   │   ├── naming.py             the naming chains (#51) — the only answer to "what is X called"
│   │   ├── profile_links.py      one profile-URL builder per platform
│   │   ├── presence_view.py      "where is this person right now" — /online's rule, for one person
│   │   ├── descriptions_view.py  an achievement's name/description in the reader's language (#48, #61)
│   │   ├── platform_format.py    game platforms and devices, formatted (#79)
│   │   ├── title_catalog.py      the game-level achievement catalog, 24h debounce (#99, #80)
│   │   ├── achievement_icons.py  achievement icons on disk under data/achievements/ (#99)
│   │   ├── images.py, avatars.py, covers.py   fetch, bound, hash and store pictures (#55)
│   │   ├── message_log.py        request middleware: logs every outgoing group message
│   │   ├── message_limits.py     request middleware: nothing exceeds Telegram's length limits (#68)
│   │   ├── single_message.py     delete-then-send for commands that replace their own last copy
│   │   ├── release_notify.py     the release announcement on startup
│   │   ├── notify.py             notifications to the admin
│   │   ├── mini_app.py           Mini App open-button URLs
│   │   ├── hltb.py               howlongtobeatpy wrapper, cached in hltb_cache
│   │   ├── crypto.py             Fernet
│   │   ├── credential_health.py  what one failed liveness check of a shared credential means (#62)
│   │   ├── rate_limiter.py       shared sliding-window limiter (Xbox, Steam)
│   │   ├── description_backfill.py  one Xbox title's descriptions in both locales (#48)
│   │   ├── xbox/                 auth.py (token storage, refresh), client.py (requests, retry,
│   │   │                         backoff), models.py (pydantic responses)
│   │   ├── steam/                auth.py (the admin-settable key, #17), client.py, achievements.py
│   │   │                         (fetch_unlocked + schema/rarity cache)
│   │   ├── psn/                  auth.py (NPSSO, PsnAuth), client.py (to_thread wrapper),
│   │   │                         achievements.py (sync_account, one game at a time, #26)
│   │   └── translate/            Anthropic API via raw httpx, *descriptions only*, never names:
│   │                             client.py, descriptions.py (cache-or-translate), auth.py (#17 shape)
│   │
│   ├── poller/                  APScheduler jobs, one tick a minute
│   │   ├── scheduler.py, cadence.py              job assembly; shared interval/dormancy math
│   │   ├── presence.py, steam_presence.py, psn_presence.py   presence per platform (#1, #90)
│   │   ├── fetcher.py, steam_fetcher.py, psn_fetcher.py      achievements, backfill, resync (#27, #90)
│   │   ├── catch_up.py, steam_catch_up.py        deltas for achievements earned offline (#82, #89)
│   │   ├── publisher.py          publication, digests, the send queue, the anti-flood write side
│   │   ├── flood_flush.py        the anti-flood read/flush side
│   │   ├── daily.py              scheduled summaries and the two on-demand summary commands (#14)
│   │   ├── avatars.py, covers.py                 pictures, a few per tick (#55)
│   │   ├── description_backfill.py, rarity_backfill.py, steam_localization.py
│   │   │                         cache walkers for what polls never bring (#48, #61)
│   │   ├── reminders.py          reminders for a dead Xbox login
│   │   ├── message_cleanup.py    auto-deletes system messages
│   │   ├── online_refresh.py, admin_refresh.py   self-refreshing /online and /admin
│   │   └── service_health.py     liveness of the shared credentials
│   │
│   ├── web/                     oauth.py (OAuth callback + Mini API mount), mini_api.py (JSON,
│   │                            Init Data auth), mini_auth.py, mini_me.py, mini_chat.py,
│   │                            mini_admin.py (secrets never leave it), mini_hltb.py, mini_avatars.py
│   │
│   └── db/
│       ├── schema.sql            full DDL for a brand-new database
│       ├── repo/                 all data access, the only place with SQL; one Repo from mixins
│       │                         (map in its __init__.py); `_sql.py` holds the shared joins (#52)
│       └── migrations/           one file per schema change, for existing databases only
│
├── scripts/                     one-off operational helpers, outside the running bot
│   ├── render_screen.py          draws any screen, prints it or sends it to the owner's DM (#63)
│   ├── xbox-deploy.sh            what CI runs on the server (/usr/local/bin/xbox-deploy)
│   ├── db_status.py              summary for `manage.ps1 status`
│   ├── pull_games_and_achievements.py, reconcile_achievements.py   bulk history syncs
│   ├── cache_achievement_icons.py                                   icon pre-caching (#99)
│   └── backfill_*.py             one-offs for data that predates a feature (each names its issue);
│                                 backfill_rarity.py and backfill_descriptions.py need the bot stopped
│
├── tests/                       pytest + pytest-asyncio; real platform/Telegram calls forbidden
├── backups/                     database copies and dumps — gitignored (see Operations)
├── data/                        databases, avatars/, covers/, achievements/ — gitignored
└── logs/                        gitignored
```

## Localization

All user-facing text lives in `bot/locales/<locale>/LC_MESSAGES/*.ftl`, resolved
through `aiogram_i18n` in handlers and `bot.i18n.gettext` elsewhere. Never hardcode
user-facing text in Python — buttons, alerts, cards and published messages alike.
Code comments and log lines stay English.

- **The locale is decided per context, never per process** (#48,
  `bot.i18n.LocaleManager`, choices in `AVAILABLE_LOCALES`): a group renders
  in its `chat_settings.locale` (Telegram cannot show two viewers one message
  differently), a DM in the person's `user_settings.locale`. `normalize_locale()`
  coerces anything unknown back to `ru` instead of raising mid-render. Neither is
  seeded from Telegram's `language_code`: much of this Russian-speaking community
  runs Telegram in English.
- **Outside aiogram's update handling the locale is an explicit argument** —
  `gettext(module, key, locale=...)` or `translator(module, locale)` bound once per
  screen. Never a `ContextVar`: the publisher and the summaries loop over chats, and
  an ambient locale nobody re-set is how one chat's message ends up in another's
  language.
- **A missing key falls back to `ru`** on both seams, so a locale can be filled in
  file by file without breaking a screen.
- **`ru` and `en` ship complete.** `tests/test_locale_parity.py` enforces the same
  files, keys and `$variables`, and that every key renders — structure, never wording.
- **Plural forms are Fluent's job**: a counted string selects on `$count` and shows
  `$pretty`; Python never computes a form (Russian's one/few/many are not English's
  one/other).

## Configuration

Required environment variables: `BOT_TOKEN`, `ADMIN_TG_IDS` (comma-separated
super-admins), `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET`, `OAUTH_REDIRECT_URL`
(public HTTPS — Microsoft rejects `http://` and `localhost`), `FERNET_KEY`.

Optional: `STEAM_API_KEY`, `ANTHROPIC_API_KEY`, `OAUTH_LISTEN_HOST` /
`OAUTH_LISTEN_PORT`, `DB_PATH`, `LOG_LEVEL`, `MINI_APP_URL` (empty disables the Mini
App entry points), and the poller interval settings.

- **`STEAM_API_KEY` and `ANTHROPIC_API_KEY` are first-run seeds** (#17): the auth
  wrapper (`SteamAuth` / `AnthropicAuth`) imports the env value once into
  `app_settings`, encrypted, and from then on the admin panel's "🔑 Ключи платформ"
  owns it — set / change / clear with no restart. Clearing it in the panel disables
  the seed, so a stale env var cannot resurrect it. No Steam key: `/connect_steam`
  says "not configured". No Anthropic key: translation is skipped. Neither is fatal.
- **Everything else tunable lives in `app_settings`**, editable live from `/admin`:
  display limits, summary caps, HLTB limits, `account_reset_cooldown_hours` (see
  Data model, default 24h, 0 = off).

## Data model

The canonical schema is `bot/db/schema.sql`; this section describes the model, not
every column. History: #106.

### Bring-up and migrations

- **`schema.sql` runs on every start; migrations bring an *existing* database up to
  it.** A brand-new database is **baselined** — its migrations are recorded as
  applied without running — so a migration only has to work against the schema it
  was written for. The test is "was the file empty before schema.sql ran", not
  "does `schema_migrations` exist".
- **A migration adding a column schema.sql already created is not an error**:
  `_apply_one` swallows `duplicate column name`, and only that, and logs it. A
  database skipping versions meets both halves of the bring-up at once.
- **A failed bring-up stops the process.** `connect()` closes the connection before
  re-raising; an open aiosqlite connection keeps a non-daemon thread alive and the
  bot neither serves nor exits.
- **A database ahead of the code refuses to start** (`SchemaTooNewError`, #56) —
  that is how an older build learns a newer one already migrated its file.
- **Rehearse a migration on a copy of production before the release that carries
  it** — copy with `sqlite3`'s `backup()`, run the real `Database.connect()`, count
  rows on both sides. Production's particular history breaks migrations no test can.

### People and accounts (#52)

- `users` is keyed by Telegram `tg_id` and holds only the Telegram identity.
  `accounts (platform, external_id, display_name, secondary_name, gamerscore,
  psn_trophy_level, achievements_visible, avatar_*, …)` is a platform account on its
  own terms (`platform` is `xbox`/`steam`/`psn` — one Xbox account covers both
  generations). `account_links (tg_id, platform, external_id, is_active, linked_at,
  unlinked_at)` says who holds it now and who held it before.
- **Unlinking never deletes**: the link is deactivated, the account and its history
  stay, and relinking finds them. `idx_links_one_active_per_platform` allows one
  account per platform per person — **dropping it is all multi-account support
  (#10) needs**; `idx_links_one_owner` gives an account one current owner.
- `User` still exposes `xuid`/`gamertag`/`gamerscore` through the `XBOX_ACCOUNT`
  join in `db/repo/_sql.py`, so Xbox call sites kept their names.
- `accounts.achievements_visible` (#5) is the last *checked* answer to "can the
  shared credential see this account's achievements": `NULL` until checked, set at
  connect and by every backfill/resync, never read live from a UI path.
- **Reset cooldowns** (`platform_cooldowns`, migration 054): one free re-link after a
  full reset; further resets inside `account_reset_cooldown_hours` block re-linking.
  Tracked by `(tg_id, platform)` and `(platform, external_id)`, so switching
  Telegram accounts does not dodge it. A super-admin's reset clears it.

### Achievements and publications

- **`seen_achievements` is the dedup table, keyed by the account that earned the
  row** (#52): `(platform, xuid, title_id, achievement_id)`. Keying it by `tg_id`
  was #29's bug. A person's achievements are *the rows of the accounts they hold
  now*, resolved through `account_links` by the one join in `db/repo/_sql.py`
  (`OWNED_BY_PERSON`) — an account nobody holds is invisible, and an account that
  changes hands takes its history with it, retroactively.
- `platform` is `xbox_modern` (One, Series, PC Microsoft Store — one service, one
  contract), `xbox_360`, `steam` or `psn`; the GENERATED `account_platform` maps
  both Xbox values onto `xbox`. `xuid` is the generic external-account id (a
  SteamID64 or PSN `account_id` on other platforms). `is_backfill` means "never
  publish" — not "did not happen" (Statistics rules). `is_secret` renders behind a
  spoiler. `trophy_type` is the PSN tier; `trophy_group_id` is the PSN group
  (`default`, `001`…), `NULL` elsewhere and on PSN rows stored before #46 — which is
  how the poller knows a game's DLC trophies were never fetched. `device` is the
  hardware it was earned on (#79).
- `publications` records what was posted to each chat, with its message id.
  `bot_messages` logs every bot message in a group (`is_system`, `is_achievement`,
  `preview`) for cleanup and `/delete_last`; `tracked_messages` holds the one copy a
  self-replacing command keeps per scope; `online_auto_refresh` and
  `admin_panel_refresh` the self-refreshing screens.

### Chats and settings

- `chats` + `subscriptions` (who publishes where; `rarity_mode` and
  `digest_threshold` are per person *per chat*). `chat_settings`: rarity threshold,
  summary time, timezone, muted games, minimum gamerscore, daily-summary switch,
  anti-flood `flood_limit`/`flood_window_minutes`, `locale`. `user_settings`:
  timezone, muted games, `show_profile_links` (off by default; new users start from
  `app_settings['default_show_profile_links']`), `show_secrets` (Mini App only),
  `locale`.
- **Anti-flood state**: `notification_throttle (tg_id, chat_id, window_started_at,
  count_in_window, throttled)`. No buffer table — a held-back achievement is exactly
  one missing from `publications` for that chat, which `unpublished_achievements()`
  finds.

### Games, caches and pictures

- **Presence**: `presence_state` (Xbox), `steam_presence_state`, `psn_presence_state`
  (#1, unrelated to the trophy scan). PSN scan progress: `psn_title_progress`,
  `psn_poll_state`. Xbox history: `title_history`. Steam: `steam_schema_cache`,
  `steam_rarity_cache`. HLTB: `hltb_cache`.
- **`titles`** — one row per game: names (`name`, `name_ru`, `name_en`),
  `achievements_total`, `platform`, `platforms` (#79), cover art (`icon_url` +
  `cover_path`/`cover_hash`/`cover_checked_at`), `achievements_checked_at`.
- **All three platforms localize a game's title** (#61). PSN's comes in the same call
  as its trophy groups; Xbox's rides on the `ru-RU` contract-4 response already
  fetched for descriptions (x360 keeps the titlehub name); Steam's needs the
  storefront (`appdetails?l=russian`, once per game — the Web API ignores `l=` for
  names), walked by `poller/steam_localization.py`. To test whether something is
  localized, pick a title that *has* a localized name.
- **PSN trophy groups** — `title_groups (title_id, group_id, name, name_ru, name_en,
  total)`: the base game plus one row per DLC, refreshed when the stored count stops
  matching Sony's total. Per-account progress inside a group is counted from
  `seen_achievements`, never asked of Sony.
- **The achievement catalog** — `title_achievements` (#99, migration 053): every
  achievement of a game, earned by anyone or not, with both names, both
  descriptions, icon, secrecy, value and rarity. `TitleCatalogService` refreshes a
  title at most every 24h (`titles.achievements_checked_at`). Icons are cached under
  `data/achievements/{platform}/{title_id}/`.
- **Descriptions in both languages** — `achievement_description_cache (platform,
  title_id, achievement_id, description_ru, description_en, source)`, shared by
  everyone who unlocks the achievement, so a translation is paid for once. `source`:
  `native` (the platform gave two different strings), `llm` (it gave the same text
  twice, so `services/translate` filled the gap), `fallback` (no Anthropic key: the
  platform's text is stored with `description_ru` NULL, shown untranslated, and
  re-offered to the translator once a key exists). Only
  `services/translate/descriptions.py::bilingual_descriptions` writes it.
- **Names in both languages** — `achievement_name_cache`: the platform's own two
  strings, **never translated**, filled from the same two locale requests. Each
  platform's main call fixes one language (Xbox/PSN English, Steam Russian), which
  is why it exists.
- **What a message renders from**: `services/descriptions_view.py` swaps in the
  reader's language from those caches per chat, falling back to the other language
  and then to `seen_achievements`' own snapshot. Rows are copied, never mutated —
  the publisher renders the same list once per chat.
- **Rarity** — `achievement_rarity_cache`: see Lists and tables.
- **Pictures are downloaded, not linked** (#55): a Telegram `file_id` is useless
  without the bot token and a platform URL can break. Telegram photos
  (`users.photo_*`) and account avatars (`accounts.avatar_url/path/hash`) go to
  `data/avatars/`, covers to `data/covers/`, paths stored relative. Avatar URLs come
  from calls the bot already makes (Xbox `GameDisplayPicRaw`, Steam `avatarfull`, PSN
  `avatars`); `poller/avatars.py` re-checks each subject weekly and skips unchanged
  ones. Covers: Steam's is a fixed CDN path (`library_600x900`, portrait), PSN's
  rides in the trophy listing, Xbox's costs a titlehub call — `poller/covers.py`
  rations three a minute and visits each title **once** (art does not change).

### Secrets

`tokens` stores encrypted Xbox refresh tokens only (access/XSTS tokens stay in
memory); status is active / invalid / revoked. Shared credentials (PSN NPSSO, Steam
key, Anthropic key) are encrypted in `app_settings`.

## Platform integrations

History: #107.

### Xbox

Microsoft OAuth + Xbox Live APIs, one refresh token per user.

- **Tokens.** Store only encrypted refresh tokens. Refresh lazily, right before a
  request, when close to expiry, and serialize refreshes per user: Microsoft
  invalidates the previous refresh token when it issues a new one, so two concurrent
  refreshes log the person out. Persist a new token *before* the request that needed
  it. `invalid_grant` means dead access: mark it invalid, notify the user. Never log
  a token or a token-bearing payload.
- **One process refreshes.** `XboxAuthService`'s guard is an `asyncio.Lock` — it
  serializes callers inside one process, not across two. Anything touching Xbox from
  outside the bot (a script, another checkout) runs with the bot stopped.
- **Contracts.** Modern Xbox: contract 4, the only one with rarity. Only
  `progressState == "Achieved"` enters `seen_achievements` — an `InProgress` row
  would hide the achievement forever once it is earned. Xbox 360: contract 1 — no
  rarity from Microsoft and only a bare `imageId`, so its card uses the box art.
- **Identity.** Match an account by XUID, never by gamertag (gamertags change);
  `users.gamertag` is a display cache.
- **Timeouts.** The shared `SignedSession` gets a split timeout —
  `XBOX_CONNECT_TIMEOUT_SECONDS` = 10 so a dead connection fails fast,
  `XBOX_READ_TIMEOUT_SECONDS` = 45 because a 1000-title `title_history` is slow
  but fine — set through the client's `.timeout` setter (the session takes no timeout
  argument). `title_history()` also has a 60s overall deadline
  (`TITLE_HISTORY_DEADLINE_SECONDS`; httpx's read timeout resets on every chunk), and
  `startup_catch_up` bounds each account at 120s (`STARTUP_CATCH_UP_DEADLINE_SECONDS`)
  so one slow account cannot hold up the rest. Errors format with `{exc!r}`: a
  connection-level httpx error often stringifies to nothing.
- **Descriptions.** The contract-2 backfill brings the whole library in one request
  but in no language, so `poller/description_backfill.py` fills the bilingual cache
  a few titles per tick — a poller rather than a script because of the one-process
  rule above. Live polls (`poll_title`, `catch_up`) ask for `ru-RU` beside `en-US`
  for achievements not cached yet; backfill's x360 pass skips it (nobody sees that
  history).

### Steam

The official Steam Web API, one shared API key, no per-user OAuth.

- **The key** is read lazily through `SteamAuth` by every consumer, never a
  constructor copy, so a change in the admin panel applies on the next call (#17).
- People connect by profile URL, vanity URL or bare SteamID64. Their profile and game
  stats must be public — only they can change that.
- Presence comes in batches of up to 100 SteamIDs (`GetPlayerSummaries`).
- **Every stored achievement carries its game's name** (#70): `fetch_unlocked`
  takes `title_name` so the `titles` upsert has something to write — without it a
  game that arrived by backfill or catch-up stayed "без названия" forever.
- **Schema and rarity.** The schema is cached per app with no expiry but
  **re-fetched when an unlocked achievement is missing from it** (#49) — games add
  achievements after release, and a stale schema publishes a DLC achievement with
  no icon and no spoiler. One retry per game per process. Global rarity is cached
  with an expiry (it drifts).
- **Backfill** scans owned games with playtime, one call per game, under a two-level
  concurrency limit (people at once, games per person at once).
- **Descriptions**: `GetPlayerAchievements` is fetched with `l=english` beside
  `l=russian` only when some achievement in the batch is not cached yet.
- **Exit poll is delayed 180s** (`STEAM_DELAYED_EXIT_POLL_SECONDS`, #89): `GetPlayerAchievements` sits behind a CDN
  cache for 2–5 minutes and Steam Cloud syncs on exit, so an immediate poll misses
  the session's last achievements. Relaunching the game inside that window cancels
  the pending poll.

### PlayStation Network

One shared NPSSO for the whole bot, via `psnawp` — synchronous, so every call in
`services/psn/client.py` goes through `asyncio.to_thread`. There is no public API
for this; psnawp uses the private one the PlayStation App uses.

- **The design rests on one verified bet**: one admin NPSSO can read the trophies of
  *any* account whose trophy privacy is "Everyone", so nobody else logs in. Do not
  weaken the design without re-verifying it.
- **Verify an NPSSO with a real call (`check_alive()`) before saving it** — psnawp's
  token exchange is lazy.
- **Shared-credential health** (all three credentials, `services/credential_health.py`,
  #62): the admin is notified once per alive → dead transition, and once on recovery.
  A death needs `FAILURES_BEFORE_DEAD` consecutive failures, re-checked on the next
  tick — an unconfirmed failure leaves `checked_at` alone — because these services
  fail one request at a time for their own reasons. A dead PSN token stops polling
  *everyone* linked to PSN.
- **Presence and trophies** (#90): presence is one `get_presence()` per account, on
  the shared politeness cadence. Going Online → Offline fires an exit poll
  (`psn_fetcher.poll_account`), since trophies often sync when a session ends. Trophy
  titles are scanned every 120s while online, 30 min while offline and active, 24h
  when dormant (settings `psn_poll_interval`, `psn_offline_poll_interval`,
  `psn_dormant_poll_interval`); a title whose progress grew is fetched in full.
- **The scan persists one game at a time, trophies before the progress cache**
  (#26) — the other order silently lost trophies when a scan failed partway. An
  unmapped error on one game is logged and skipped.
- **A freshly linked account is gated out of the poller** by
  `psn_poll_state.backfill_done` until its first backfill finishes (#21) — otherwise
  a tick mid-backfill publishes the whole history. A stuck account is recovered by an
  admin resync.
- **Every trophy request asks for `trophy_group_id="all"`** (#46); psnawp defaults to
  the base game only. A game the bot knew only the base group of is widened once
  (`repo.psn_title_needs_widening`: rows stored, none carrying a group), and what that
  pass digs up publishes under the 24-hour relink cap (`PsnSyncOutcome.catch_up_rows`)
  instead of as fresh unlocks. Decided per account, never from the shared
  `title_groups`.
- **`trophy_earn_rate` arrives as a string** despite its `float | None` annotation —
  coerce it (`services/psn/client.py::_as_float`).
- **The PSN level** (`accounts.psn_trophy_level`) is refreshed after a backfill and
  after a tick that found new trophies — it only changes when a trophy is earned.
- PS3/PS4/PS5/Vita share one trophy service: no separate parsing branch.
- **Wording and badge**: PSN says "trophies" everywhere, and a trophy's badge is its
  tier (🥉🥈🥇💠) instead of the rarity badge — the tier already answers "how rare",
  on Sony's scale.
- **Descriptions**: psnawp fixes the locale per client, so `PsnAuth` keeps a second,
  lazily built `ru-RU` client (`get_translation_client()`), invalidated with the
  primary. Its failures are swallowed, never raised as `PsnTokenDeadError` — they say
  nothing about the shared NPSSO. Runs during backfill too.
- Open: more than one PSN account per person — #10 (drop the index above).

## Polling model

The scheduler ticks every minute; each poller decides whether a target is due.
History: #108.

- **Presence cadence** (Xbox, Steam) is state-based — fastest in a game, then online,
  then offline, slowest for someone long absent — for politeness, not quota.
- **Accounts idle more than 14 days are dormant** (`poller/cadence.py::is_dormant`,
  `catchup_idle_threshold_days`, from `last_online_at` or `linked_at`): their
  catch-up and PSN scans drop to once a day. Coming online (`touch_last_online`)
  wakes them at once; a fresh link counts as active.
- **Achievement polling and exit polls**: while in a game, poll that game on the
  achievement debounce. On leaving it or going offline, one exit poll catches the
  last unlocks — immediately on Xbox, after 180s on Steam, on Online → Offline for
  PSN (see each platform).
- **Isolate failures**: a poller never fails a whole tick because one user, account,
  title or batch failed — log and continue. Private profiles, empty responses, 429s,
  timeouts, dead credentials and outages are expected states, not exceptions.
- **Backfill** is mandatory on first connection and safe on reconnection: history goes
  in with `is_backfill = 1`, idempotently (`INSERT OR IGNORE`), and never publishes.
  Xbox modern uses the broad history endpoint, Xbox 360 a title-by-title pass, Steam
  owned games with playtime, PSN trophy titles directly. PSN backfill flips
  `backfill_done` last.
- **Catch-up** covers achievements earned offline or during downtime — on startup,
  hourly per account while the bot runs (`poller/catch_up.py` for Xbox via
  `title_history`, `poller/steam_catch_up.py` via `GetRecentlyPlayedGames`, one
  account per tick), and from the admin panel's refresh. Its rules:
  - the window starts at **the newest unlock already stored**
    (`fetcher.catch_up_since`), never at presence — `presence_state.updated_at`
    changes every tick, so a window from it is always empty (#82) — floored at
    `catchup_publish_window_hours` back;
  - only unlocks inside `catchup_publish_window_hours` publish; older ones are stored
    silently;
  - a row with no unlock date is placed by when its game was last played
    (`title_history.last_played_at`), not dropped.

## Publication rules

History: #108.

An achievement is published to a chat only if every check passes: the person is
subscribed there; not admin-excluded; `rarity_mode` isn't `hidden`; in `rare` mode a
known rarity is at or below the chat's threshold (a platform with no rarity at all —
Xbox 360 — is exempt, not hidden); its gamerscore meets the chat's minimum; the game
isn't muted there; it wasn't already published there.

- **The threshold is always `chat_settings.rare_threshold_percent`**, set per chat by
  an admin. Never hardcode a percentage; a person picks only a mode.
- **Digests**: at `subscriptions.digest_threshold` items a batch becomes one grouped
  message, grouped by platform and title. Every item is listed, never "и ещё N". The
  gallery dedupes by image URL.
- **Nothing may fail for being too long** (#68): `services/message_limits.py` is a
  request middleware that cuts any outgoing text to Telegram's limit (4096 message,
  1024 caption, 200 callback answer), keyed on which fields a method *has* so new
  sends are covered. It cuts only outside a tag or `&entity;`, prefers a word
  boundary, closes what is open, and logs a warning — a net, not a substitute for
  keeping screens short. Capping lists by rows does not replace it: the limit is in
  characters.
- **Delivery** goes through a send queue under Telegram's group rate limit. A 403
  means the bot was removed: deactivate the chat. Every send is logged
  (`bot_messages`) for cleanup and deletion.
- **Anti-flood filter**, per (person, chat), after every other check — so it only
  reacts to what would actually be announced. Up to `flood_limit` notifications
  (across all of a person's platforms) within a rolling `flood_window_minutes` post
  normally; reaching the limit restarts the window in "throttled" mode, and the rest
  of it stays unpublished. `flood_limit = 0` turns it off. Both numbers are per chat,
  set by an admin, never a global default.
- **The throttled backlog** goes out as one combined digest when its window closes
  (`poller/flood_flush.py`, `Publisher.publish_flood_digest` — it can mix platforms,
  so its header names the person, not a platform nickname). Forced sweeps right after
  startup and five minutes before each chat's daily summary keep a window from
  swallowing anything.

## User interface

User-facing text is Russian by default and English where a chat or person picked it
(Localization). History: #109.

### Naming people and accounts (#51)

**One chain per question, reused — never a new one at the call site.** Four
hand-rolled versions of "who is this" once coexisted and disagreed. A screen that
seems to need a third chain is a question for the owner, not a decision at the
keyboard.

1. **Who is this person?** `Имя Фамилия` → `username` → a connected platform's
   nickname (Xbox → PlayStation → Steam) → `id<tg_id>`.
2. **Which account is this?** That platform's own chain — used *only* where a line is
   genuinely about one platform: per-platform rows in `/stats`, `/panel` and the
   admin's user card, connect/disconnect notices, the achievement announcement, and
   `/online` rows **while the person is online** (an offline row names the person).

| Platform | Chain | Notes |
|---|---|---|
| Xbox | `ModernGamertag` → `Gamertag` → XUID | the `#1234` suffix is never shown; the profile **link** uses the classic `Gamertag` |
| Steam | `personaname` → vanity → SteamID64 | no vanity: `profileurl` degrades to `/profiles/<id>/` |
| PSN | current `onlineId` → previous `onlineId` → `account_id` | the previous id comes from the legacy endpoint, addressed by nickname, and from the value a refresh replaces |

- **Code that needs a specific value does not go through a chain** — lookup keys,
  URLs, comparisons with what a platform returned use the raw column.
- **Never an `@`**: usernames are shown bare, because a mention pings — and `/online`
  redraws every few minutes (#38).
- **A nickname refreshes from responses the bot already makes** (Xbox profile, Steam
  `GetPlayerSummaries`, PSN `get_presence`), written only when it changed. A stale
  nickname also breaks the profile link.
- **One platform order for every list: Xbox, PlayStation, Steam** —
  `constants.platform_display_rank`, never hand-ordered.

### Private chat

- Commands: `/start`, `/panel`, `/stats`, `/connect_*`, `/disconnect_*`, `/hltb`,
  `/help`. A private flow started in a group redirects to a DM, never fails silently.
- **`/start` greets and offers all three platforms**; anyone with *any* platform
  linked gets the panel instead (#53). Disconnecting is one tap-to-confirm, never a
  typed word.
- **Timezones**: the eight offsets this community lives in, "Другой ▸" for the full
  −12…+14 grid, "✏️ Ввести вручную" for one typed offset (`+3`, `+5:30`). Offsets,
  never zone names.
- **The stale-login reminder is the only DM the bot starts itself** (besides connect
  progress), and it says reconnecting will not replay history into chats.
- **`/panel`** is one self-editing message. Header: the person's identity and one line
  per connected platform, built by the same `platform_header_lines` as `/stats` (#5)
  with links off. Body: login state per platform (Xbox token; Steam/PSN visibility as
  last checked), where achievements publish, presence as **one row**
  (`presence_view.pick_presence`, the same rule `/online` uses — names the platform
  only while online), timezone. Keyboard: one row per platform in the display order
  — `[Profile, Disconnect]` or one wide "🎮 Подключить X" (#33) — then timezone, My
  chats, sync, `show_profile_links`, language (#48, DMs only), per-chat subscription
  cards. Nothing on it is Xbox-gated. Own profile links always show (only the owner
  sees it). It never calls a platform API except the explicit sync button.

### Group chat

- Commands: `/subscribe`, `/unsubscribe`, `/stats [@user]`, `/who`, `/online`,
  `/recent [N]`, `/summary_day`, `/summary_month`, `/hltb`, `/delete_last`, `/help`,
  `/panel` (the group hub). The group slash menu shows four: `/panel`, `/subscribe`,
  `/hltb`, `/help` (`bot/main.py`).
- **`/stats`**: cached stats and games; header `👤` + the person (chain 1), each
  platform on its own line. **`/who`** picks a known member and opens their `/stats`;
  its buttons name the person (#40).
- **Profile links** appear only when the person *the card is about* has
  `show_profile_links` on — no exception for your own card, because the message is
  the same whoever asked.
- **`chat_seen`** tracks anyone who wrote in the group; `/online` and `/who` use it,
  not just subscribers.
- **A capped leaderboard** gets one button that replaces the message with the same
  block uncapped, in a plain blockquote.
- **Bot replies to commands carry a "Закрыть" button** (`views/keyboards.py::
  with_close_button`); closing `/online` also stops its auto-refresh. Achievement
  notifications do not get one.
- **`/delete_last`** removes the bot's latest message in the chat whatever it is —
  **except an achievement notification**, single or digest, which it never takes
  (#101; `bot_messages.is_achievement`, set under the publisher's
  `achievement_category()`). The admin panel's and the Mini App's "delete last" share
  the query. It quotes the first lines of what it deleted, and that confirmation is a
  system message the cleanup job removes later.

### Admin

- **Two roles, named distinctly**: the **суперадмин** is the global operator
  (`ADMIN_TG_IDS`); the **админ чата** is the per-chat role #15 proposes, which does
  not exist yet.
- **`/admin`** (private, self-refreshing): credential health; "🔑 Ключи платформ" to
  set / change / clear the Steam key, PSN NPSSO and Anthropic key (#17) — a key is
  **never shown back**, and entering one is a single-message state with only a way
  out; API usage; global limits, each on its own row with its value and its own
  input, `0` rendered as "без ограничения"; defaults for new users; the user list;
  the chat list and per-chat cards; exclusion; bot-message cleanup.
- **The per-chat card** keeps its settings in three sub-screens — daily summary,
  anti-flood, message cleanup — each redrawing in place with the card's text above.
  Settings: rarity threshold, summary time, timezone, mutes, minimum gamerscore,
  summary switch, anti-flood, language (#48).
- **The per-user card**: the Telegram identity in full (`tg_id` passed to Fluent as a
  string, never `@N`), then one block per platform in the display order — nickname,
  lifetime count with completions (🌀/👾/💠) and level, today's count, diagnostics.
- **"🔄 Обновить"** is the only UI path besides `/panel`'s sync that calls a platform
  outside a background job: presence, the current game, then a catch-up since the
  newest stored unlock (publication inside `catchup_publish_window_hours`). For PSN it
  is the recovery path for a stuck first backfill (#27).
- **"🗑 Сброс"** (tap-to-confirm) wipes that *account's* `seen_achievements` (plus
  Xbox `title_history`, PSN `psn_title_progress`/`backfill_done`) and re-runs its
  backfill. It takes the account's id, not `tg_id`.
- **A keyboard test that never invokes its handler proves only that the keyboard
  exists** — `tests/test_handler_wiring.py` checks every handler's arguments and that
  none shadows its own translator `_`.

## Message formats

History: #110.

### An achievement card

- **A photo message**: the achievement's icon, everything else in the caption (1024
  characters). Xbox 360 uses the game's box art (contract 1 has no usable icon URL).
- Header: the name in bold + "получает достижение" / "получает трофей" (PSN), or
  **"получает секретное …"** for a secret one (#16) — the header is the one line never
  hidden, and a spoiler with no explanation reads as a glitch.
- **Game line**, italic: game, platform, and the person's progress `47/50` when the
  total is known (#46). Totals: Xbox 360 from `title_history`; modern Xbox from
  titlehub or, when titlehub says 0, the size of the per-title response stored in
  `titles.achievements_total` (Microsoft's count wins where it exists); Steam from the
  schema; PSN from `defined_trophies` for every listed title (#60), **DLC included**.
  A count, never Sony's tier-weighted percentage. No known total: no counter.
- **PSN group line** (#46), only when the game has more than one group: the group
  and progress inside it (`CTNS: The Heist · 3/7`). A name equal to the game's reads
  "Основная игра"; a name starting with the game's keeps only the rest; never a "DLC"
  prefix (a group is not always one) — `services/achievements.py::_group_label`.
- Then the badge and the name in quotes, gamerscore (if nonzero) and rarity (if
  known), then the description — behind a spoiler if secret.
- **Badges**: `rarity_badge()` — 💎 at or below the chat's rare threshold, 🏆
  otherwise (including unknown). PSN shows its tier instead (see PSN).

### Digests

- One header ("получает N достижений" / "N трофеев" for an all-PSN batch), one block
  per game with the game's own counter, every item in the card's line format. A
  `sendMediaGroup`, caption on the first image, images deduped.
- **The anti-flood digest is the same form**; only its header names the person
  instead of a platform nickname, because it can mix platforms.
- **A digest never names a trophy group** — one block is one game.
- `plural_achievements()` is never platform-specific: combined counts are
  "достижения" even when some came from PSN.

### Stats and lists

- **Lists render as sentence lines in a collapsible `<blockquote expandable>`**,
  never a `<pre>` table.
- **Windows**: "за сутки" is a rolling 24 hours, the same for everyone; the month is
  the **calendar month** since midnight on the 1st in the person's / chat's timezone
  (`stats.month_cutoff_utc`), labelled with the month's name ("с 1 сентября",
  `views/summary.py::month_window_label`). **No list uses a rolling N-day window.**
- **The two counter lines** in `/stats` say which window they mean ("За сутки", "С 1
  сентября") and end in the value bracket a games row uses — gamerscore, rare count
  by this chat's threshold, PSN tiers, zeros dropped (`views/parts.py::value_parts`).
- **A `/recent` row leads with PSN's tier where it has one**, and separates game and
  achievement with `·`.

### Summaries (#14)

- **Two reports, never both in one message**: the daily job sends the day report; the
  month-end job (last day of the month, the chat's summary time, its own
  `daily_reports` marker `YYYY-MM-monthly`) sends the month report in addition. `/summary_day` and
  `/summary_month` send them on demand, each replacing its own last copy.
  `build_summary(window=DAY | MONTH)` cannot express "both". (`/summary` sent both and
  is gone — #68.)
- **One form, different cutoff**: header (📅 Итоги дня / 🗓 Итоги месяца), the chat's
  **Всего** with the same brackets as `/stats`, **Игроки** ranked by what they
  earned (💎 count included), and **Игры** — the shared games listing for every
  subscriber.
- A day nobody earned anything still sends the roster at zero (#34); only a chat with
  no subscribed members gets nothing.

## Lists and tables

History: #111.

**A list is either text or a keyboard — a rendering decision, not a data one.**

- A **listing** is text — `views/lists.py::Listing`: header, rows, optional total,
  and a wrapper: **quoted** (collapsible blockquote, the default), **plain** (read at
  a glance: `/online`, the admin roster), or **code** (`<pre>`, gone since #64 —
  do not reintroduce).
- An **inline listing** is buttons — `views/inline_lists.py`: `button_rows`,
  `paginate`, the way out ("назад"/"отмена").
- **Rows are not shared** between lists — games and people are different things —
  except the games row, drawn identically everywhere (#64).
- **One navigation shape**: `◀️ 2/5 ▶️`. The counter is a button whose `noop`
  callback lives in its own screen's namespace (`a:noop`, `hltb:noop`).

| List | Kind | Source | Who appears | Sort | Cap |
|---|---|---|---|---|---|
| the games list: `/stats`, `/summary_day`, `/summary_month` | listing, quoted | `repo.users_games_achievements()` | `/stats`: the card's owner; a summary: every subscriber, summed | count ↓, then last unlock ↓ | `stats_games_limit` / `summary_top_limit` (0 = uncapped) |
| `/recent` | listing, quoted | `repo.chat_recent()` | the chat's subscribers | `unlocked_at` ↓ | `recent_limit`, or the command's `N` (≤ `RECENT_MAX`) |
| summary leaderboards | listing, quoted | `repo.chat_member_stats()` | every subscriber, **zeroes included** | the window's count ↓ | `summary_top_limit` |
| `/online` | listing, plain | `repo.chat_member_presence()` | subscribers ∪ `chat_seen` | playing → online → offline, then `updated_at` ↓ | — |
| the admin's user list | listing (plain) **and** inline | `repo.admin_users()` | anyone with a platform linked | `is_excluded` ↑, `last_online_at` ↓ | `PAGE_SIZE`, `◀️ N/M ▶️` |
| the admin's chat list | inline | `repo.admin_chats()` | every chat | `is_active` ↓, title ↑ | — |
| `/who`'s picker | inline | `repo.chat_member_presence()` | as `/online` | as `/online` | — (three per row) |
| `/panel`'s "Мои чаты" | inline | `repo.user_chats()` | active chats this person subscribed to or wrote in | title ↑ | — |
| the admin's limits | inline | `NUMERIC_SETTINGS` | the numeric settings | their own order | — |
| `/hltb` suggestions | inline | `repo.chat_recent_games()` | games | last played ↓ | `hltb_results_limit` |
| `/hltb` results | inline | the HLTB API | games | HLTB's relevance | `hltb_results_limit`, `hltb_page_size` |
| a chat's subscribers | one joined line | `repo.chat_subscribers()` | subscribers | rendered name ↑ | — |
| a digest's per-game block | caption rows | the publish batch | the achievements sent | by `(platform, title_id)` | none |

Pickers of fixed options (timezones, digest thresholds, hours) are not lists.

- **The games listing is one query, two scopes** — `users_games_achievements(tg_ids,
  since, …)`: one person for `/stats`, every subscriber for a summary (overlap adds
  up). Grouped by `(title_id, platform)` — a Steam appid and an Xbox title id can
  collide. Ranked by achievements earned, then latest unlock; gamerscore takes no
  part (it is always 0 on Steam and PSN).
- **A games row**: what was earned, then what it was worth in brackets — `🟢 Halo —
  12 достижений (+240 G · 💎3)`, `🔵 God of War — 31 трофей (💠1 · 🥇3 · 🥈7 ·
  🥉20)`. Every zero part is dropped.
- **Which rows fall inside a window**: Statistics rules.
- **`/recent`** is subscribers only; excluded people never appear; secret names stay
  behind a spoiler.
- **`/online`**: activity beats freshness (`presence_view.pick_presence`).
- **Summary leaderboards keep zero rows** — a report, not a feed (#34).
- **Rarity is read from `achievement_rarity_cache`** (`platform, title_id,
  achievement_id`), through `_sql.py`'s `rarity()` / `rarity_cache_join()`, with
  `seen_achievements.rarity_percent` as the fallback — rarity is a fact about the
  achievement, and the row is a never-updated snapshot. Xbox rarity comes only with
  contract 4, so the contract-2 history is filled by `poller/rarity_backfill.py` (and
  `scripts/backfill_rarity.py`, bot stopped) — one request per title covers every
  owner. Every platform's poll also writes the cache. `checked_at` orders the refresh
  queue and is not an expiry. Xbox 360 has no rarity: no 💎 there, and `rare` mode
  lets its achievements through.
- **The admin's user list** is text and buttons on purpose: columns to read, rows to
  tap. **The chat list** is buttons only — a row fits on its button.
- **`/who`** is split from `/online` so one stays a glance and the other a grid; its
  cancel button is the only way out of the prompt.
- **"Мои чаты"** lists unsubscribed chats too — subscribing is what it is for; chats
  the bot left are omitted.
- **`/hltb` suggestions** come from `title_history`, so they are Xbox-only — a known
  gap.

## Statistics rules

History: #111.

- **Normal stats read only cached data** — `seen_achievements`, `title_history`,
  account links, presence and level caches — never a live platform call.
- **Which rows fall inside a window** (#69), written once in `db/repo/_sql.py`
  (`earned_at`, `earned_date_is_real`, `earned_since`):
  - a row the platform dated is placed by that date;
  - an undated row a **live poll** found is placed by `created_at` — when the bot saw
    it is an honest stand-in;
  - an undated row an **import** brought in is ancient and outside every window — its
    `created_at` is only when the import ran.

  `is_backfill` means "do not publish", never "did not happen"; it decides nothing
  when the platform gave a date. Filtering on it hid real, dated achievements;
  ignoring it counted whole imported libraries as this month's play.
- **Undated rows**: Microsoft sends placeholder dates (`0001-01-01`, `1753-01-01`)
  for some Xbox 360 achievements; `parse_timestamp` discards them and the column stays
  NULL, recording what the platform said. The readers that build an `AchievementRow`
  hand the stand-in to the publisher so its age cap agrees with the stats.
- `/recent` has no window, so the rule applies as an exclusion: an undated import
  never tops the list.
- **Three readers keep plain `COALESCE(unlocked_at, created_at)` on purpose** and say
  so in place: `unpublished_achievements` (it already excludes imports),
  `account_latest_unlock` (it asks when data starts), `recent_achievements`.
- **Lifetime counts** count `seen_achievements` rows, never sum `title_history`; the
  x360 title-by-title backfill is the soft spot (#91). **Gamerscore** comes from the
  Xbox profile, never a sum.
- **Completions**: a 100% game and a PSN platinum answer the same question, so each
  shows as a count and a badge after the platform's total, only when nonzero — **🌀
  Xbox, 👾 Steam, 💠 PSN** ("1 💠"; a badge *inside* a value bracket goes first:
  "💎10"). 🏆 is taken: it is the ordinary achievement's badge.
- Cross-platform day and month counters aggregate by `tg_id`. Platform breakdowns
  ("🟢 3 · ⚫ 5") appear only for genuinely mixed activity. Excluded users are never
  polled, published or summarized.

## HowLongToBeat

History: #112.

- `/hltb` works in DMs and groups: asks for a game (a reply to the prompt works in
  groups), suggests recent games of known members, cleans platform-noisy titles,
  shows candidates instead of trusting the first result, and caches the chosen result
  by HLTB id forever. An HLTB outage is an expected failure.
- **Game descriptions come from HLTB itself** (#2): no id-matching between services,
  and console exclusives are covered. Read from the page's `__NEXT_DATA__`
  (`profile_summary`, beside `genre`), never from rendered HTML whose class names
  change every deploy.
- HLTB is English-only, so the Russian side is always Haiku's
  (`hltb_cache.description_ru`), **lazily** — once per game, the first time someone
  looks it up. No Anthropic key: the English text is shown.
- The card shows it as a collapsed blockquote capped at `DESCRIPTION_LIMIT` — the card
  is usually a photo caption (1024 characters).

## Versioning

**`A.B.C.D`** (#56) from `bot/version.py`, shown at the end of `/help` and the hub
and logged at startup (`… is up (v1.4.3.058)`). History: #112.

- **A** — the architecture; by hand, on a rewrite.
- **B** — the minor line: `TRUNK_LINE` on `main`, **one above it on every working
  branch**, so the test server reads the line its work will ship in and "which bot is
  this" is answerable from the version. Only a release that starts a new minor bumps
  `TRUNK_LINE` and tags `vX.Y.0` on `main`; one that does not (1.4.3) leaves both.
- **C** — commits counted from git at startup, never stored in a file: on a working
  branch since the **merge base** with `main` (so others' merges do not renumber it);
  on `main` since the **newest release tag**, **first parents only** — one per release.
  `?` without git; `0` on an untagged `main`. **Cutting a release is tagging one.**
- **D** — the newest migration this code ships, not what the database has. A database
  *ahead* of it refuses to start (Data model).

## Security and privacy

History: #112.

- Never commit `.env`, databases, logs, PID files or runtime data.
- Every stored credential is Fernet-encrypted: Xbox refresh tokens, the PSN NPSSO, the
  Steam key, the Anthropic key. Losing `FERNET_KEY` means every user reconnects and
  every shared key is re-entered — back it up.
- Never log a token, key, NPSSO, authorization header, or a URL with a secret in its
  query — `httpx` logs full URLs at INFO, and Steam's `GetOwnedGames` carries the key.
  Mask first. A user-facing error never shows an upstream token error's payload.
- Revoking Microsoft's consent happens in the person's own Microsoft account; the bot
  only links there.
- **PSN profile links point at PSNProfiles** (#30) — Sony has had no public trophy
  page since 2021. A first visit to an unindexed profile shows "not tracked" and
  indexes it. The bot never checks the link (automated requests get 403).
- Profile links in `/stats`/`/who` follow the card owner's `show_profile_links`.

## Operations

History: #112.

### Three branches, three servers

"Test" names only a server, never a branch (owner, 2026-09-24).

| branch | server | where it runs | how it updates |
|---|---|---|---|
| `dev` | **dev server** | the developer's machine (`manage.ps1 … -Test`) | local git hooks restart it after every commit / merge |
| `prerelease` | **test server** | the VPS: `xbox-bot-test` · 8081 | CI deploys on every push |
| `main` | **prod** | the VPS: `xbox-bot` · 8080 | CI deploys on the merge |

- **`main` is production; merging `prerelease` into it is the release.** Daily work is
  on `dev`; `prerelease` is what the test server runs and what ships next.
- The test server keeps its own names (`xbox-bot-test`, `.env.test`, `data/test.db`,
  deploy target `test`); the dev server's `-Test` flag and local `.env.test` are a
  historical name.
- **CI** (`.github/workflows/ci.yml`) runs pytest, both ruff checks and a real Mini
  App build on every push and PR; only `prerelease` and `main` deploy, and only when
  green. Nothing is deployed by hand. Rulesets protect both branches (no deletion,
  no force-push, required checks); `main` also requires a reviewed pull request, which
  the owner merges with an admin bypass — always as a **merge commit**, so C counts
  one per release.

### The dev server

`manage.ps1` (the bot cannot start itself): `start` / `stop` / `restart` / `status` /
`logs [-Lines N]` / `dashboard` (live view with hotkeys; `manage.bat` opens it), with
`-Test` for the `.env.test` instance on 8081 and `-Web` to tunnel the Mini App.
`status` shows uptime, the port, stray bot processes (two bots on one `BOT_TOKEN`
fight over updates) and a database summary. The restart hooks live in `.git/hooks`,
so a fresh clone does not have them. Never run the dev server on prod's `BOT_TOKEN`.

### The VPS

A VPS at Spaceship (Namecheap), Ubuntu 24.04, nginx + systemd, dedicated user
`botsvc`; nginx terminates TLS (Let's Encrypt, certbot timer) and proxies to the bots,
whose ports are never exposed (`OAUTH_LISTEN_HOST=127.0.0.1`).

```bash
systemctl {start|stop|restart|status} xbox-bot        # xbox-bot-test for the test server
journalctl -u xbox-bot -f
```

| | prod | test server |
|---|---|---|
| bot | `@xbox_achievement_bot` | `@tg_achievement_bot` |
| unit / port | `xbox-bot` · 8080 | `xbox-bot-test` · 8081 |
| checkout | `/opt/xbox_achievement_bot` | `/opt/xbox_bot_test` |
| env / database | `.env` · `data/bot.db` | `.env.test` · `data/test.db` |
| branch | `main` | `prerelease` |
| Mini App | `xbox.sultanpharm.com/app/` | `test.xbox.sultanpharm.com/app/` |
| SPA files | `/var/www/xbox-mini` | `/var/www/xbox-mini-test` |

- **Each server has its own hostname** because the SPA calls `/api/mini/*` by absolute
  path — one host cannot serve both — and a bot token signs its Mini App's Init Data,
  so the two cannot cross.
- The test server's OAuth callback stays on the prod host at `/auth/callback-test`
  (the redirect URL Microsoft already has).
- **Never run git on the server as root** — the deploy runs as `botsvc`, and
  root-owned files in a checkout break it. Use `sudo -u botsvc git …`, or better, CI.

### Deploys

`scripts/xbox-deploy.sh` (installed as `/usr/local/bin/xbox-deploy`, re-installed from
the checkout on every deploy) is the only thing the CI `deploy` user may run as root.
It:

1. backs up the database **every** time (`data/backups/`);
2. `git fetch --prune` and `git merge --ff-only` — never a robot's merge commit;
3. reinstalls dependencies only when `pyproject.toml` changed;
4. unpacks the Mini App CI built (built there, not on the 300 MB box);
5. restarts, then **verifies** the bot's own `is up (v…)` line, bounded by a timestamp
   taken before the restart.

GitHub holds four secrets (SSH key, host, user, host fingerprint); `.env`, `FERNET_KEY`
and databases never go near it.

**The deploy does not rehearse migrations.** That is a person's job, done on a copy of
production **before merging `prerelease` into `main`** — the last moment it is still a
decision. The test server migrates its own, smaller, differently shaped database and is
no substitute.

### Releases

- **Release notes are written before the merge into `main`** and committed to
  `prerelease`: `changelog/<v>.ru.md`, `.en.md`, `.contributors.md`, and
  `.summary.ru.txt` / `.summary.en.txt` (5–8 `•` bullets for the announcement), where
  `<v>` is `A.B.C`. `main` then always carries its own notes and the announcement
  links never 404.
- **On startup each bot announces a new version** (`services/release_notify.py`) once,
  tracked in `app_settings.last_announced_version`: to active group chats only, in each
  chat's locale. Prod sends the summary bullets and a button to the full notes on
  GitHub; the test and dev servers send no links. 0.05s between sends; a chat that
  forbids the bot is deactivated.

### Backups

- **`backups/` and nowhere else** (on the servers, `data/backups/`) for database
  copies, dumps and the scripts that make them; `.gitignore` also blocks
  `*backup*.json`, `*dump*.json`, `*tokens*.json` anywhere.
- **A dump never holds a decrypted secret** — copy the database or the encrypted
  column. A decrypted value, when genuinely needed (re-encrypting after a `FERNET_KEY`
  change), stays in memory; if it must touch disk, it lives in `backups/` and is
  overwritten and deleted before the task ends.
- **Back up with `sqlite3`'s `backup()`, never `cp`** — the databases run in WAL mode.
  Name copies for what and when: `bot-pre042-20260915-084500.db`.

## Engineering rules

History: #112.

- Handlers are thin — services and repo methods, never raw SQL or platform logic.
- All SQL lives in `bot/db/repo/`, `schema.sql` and the migrations.
- Platform clients (`services/xbox|steam|psn`) know nothing about Telegram.
- Everything is async; wrap synchronous libraries (`psnawp`) in `asyncio.to_thread`.
- No new dependency unless clearly needed.
- No stubs or TODO placeholders — if a step is too big to do properly, say so and
  split it.
- **A screen's layout lives in `bot/views/`, and its mockup is rendered, never written
  down** (#63). One module per screen; a view renders and never sends.
- **Agree a screen before building it**: render the proposal on real data (a copy of
  production, or a constructed example when none exists) and show it, then write the
  code. `scripts/render_screen.py <screen>` prints it; `--send` puts it in the owner's
  DM, keyboard and all — the only form a layout can be judged in. The preview message
  carries only the rendered screen; caveats and questions go in the chat reply.

  ```bash
  python scripts/render_screen.py --list
  python scripts/render_screen.py panel --locale en
  python scripts/render_screen.py admin-user-card --send
  ```

  The design *decisions* are what this file keeps in writing (Message formats, User
  interface, Lists and tables), because a rule is not visible in a screenshot.

## Tests

```powershell
.\.venv\Scripts\pytest
.\.venv\Scripts\ruff check .
.\.venv\Scripts\ruff format --check .
```

Real Xbox, Steam, PSN, HLTB or Telegram calls are forbidden in tests — mock at the
service boundary.

Required coverage: achievement/trophy dedup; first-connect backfill publishes nothing;
only earned items enter `seen_achievements` (`InProgress` never leaks in); rarity
filtering at different thresholds, and a platform with no rarity under `rare`; Xbox
token refresh ordering and serialization, `invalid_grant`; excluded users are never
polled or published; the dead-token reminder is rate-limited; a missing rarity block
doesn't crash parsing; no secret in a log line or exception; Steam/PSN linking,
presence, parsing, rarity/progress caching and backfill in isolation; every handler
actually invocable (`tests/test_handler_wiring.py`).

## Style

- Code identifiers and comments: English. Bot messages: Russian by default, English per
  chat/DM — only ever from `.ftl` files.
- **GitHub is kept in English** (owner, 2026-09-24): issues, comments, PR descriptions,
  commit messages — even when the conversation was Russian. The exceptions are the
  files deliberately kept in two languages: `README.md` / `README.ru.md`,
  `changelog/<v>.ru.md` / `.en.md` and their summaries, and `bot/locales/ru|en/`.
- Comment *why*, not *what* — especially in the pollers and around token refresh.
- Prefer small, precise changes that preserve behavior unless the task is to change
  it.

## Appendix: rejected ideas — do not reintroduce without a new decision

- **OpenXBL** as the Xbox source — a third-party proxy capped at 150 requests/hour that
  needed an all-access key to other people's accounts. Direct Microsoft OAuth gives
  each person their own 300-per-5-minutes budget. Everything that existed only to
  ration OpenXBL went with it: two credential types and a `credentials` table, a
  `/connect_key` command that had people paste secrets into chat, presence batching
  as a cost measure, an `api_budget` table, the one-account-per-person ban, and the
  requirement that the bot be friends with every player.
- **A `filters` table with a `scope` column** — replaced by `user_settings` /
  `chat_settings` combined with AND.
- **`/compare` and `/top`** — `/stats`, the summaries, `/recent` and `/online` cover
  the useful group views; a leaderboard command was not worth the surface.
- **A visibility toggle per platform** — tried twice, rejected twice: nobody needs a
  different mode per platform. One `rarity_mode` covers all; a platform without rarity
  (Xbox 360) is exempt from `rare` instead of getting a toggle. (Reconsideration is
  open as #20.)
- **Global rarity settings for every chat at once** — replaced by a per-chat
  threshold.
- **Live platform API calls from `/stats`, the summaries, `/online` or the panel** —
  every normal read is cache-only; the panel's own sync button is the exception.
- **Game descriptions from the Steam store** — HLTB supplies them for every platform
  with no id-matching, console exclusives included (#2). The storefront is used for
  one field only: Steam's Russian game title (#61).
