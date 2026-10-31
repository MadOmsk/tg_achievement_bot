# CLAUDE.md

## Project

Achievement Bot is a Telegram bot for a small, non-commercial gaming community
(roughly 20-30 people). It publishes newly unlocked achievements and trophies from
connected Xbox, Steam, and PlayStation Network accounts, with per-chat rarity
filters, personal stats, an admin panel, daily summaries, HowLongToBeat lookup,
and a Telegram Mini App.

**The app is called Unlocked** (owner, 2026-10-05): it is no longer only a bot.
The name and the logo (owner, 2026-10-26, redrawn for design E: the "U" of
Unlocked as an open shackle — its right leg shorter — in flat lilac
(`#eaddff`), a pink four-point sparkle (`#efb8dc`, softly glowing) beside the right leg,
on a deep violet ground lit from the top left (`#7457c9` → `#4f378b` →
`#2f1d63`) with a soft lilac glow behind the U (owner, 2026-10-27);
`webapp/public/logo.svg`, a rounded tile; `logo-192/512.png` are rendered from
it, and `apple-touch-icon.png` and `logo-maskable-512.png` from the same drawing
as a full-bleed square — iOS and Android round it themselves — with the mark
inside the safe zone; `badge-96.png` is the white U for a push's one-colour
badge; `logo-splash-512.png` is the bare U with no tile in its violet light on
the app's night (`#141218`, the manifest's background, so no edge shows), the manifest's 512
`any` icon that Android draws on its launch splash (the maskable one is
only 192 px, so a browser that draws its largest icon there — Edge — draws
the bare U, not the square tile); an iPhone's launch screen is
`public/splash/apple-splash-*.png`, the bare U on the app's night in a
wide violet light fading into it (owner, 2026-10-30), one a screen size (`index.html`). The sign-in screens write
the name as one word — the logo's U with its sparkle, no tile, then "nlocked" in Nunito ExtraBold, its seven
letters kept in `public/fonts`) are what the Mini App,
the installed app, pushes, sign-in emails and the Xbox sign-in page show. The bots keep their Telegram names until changed in
BotFather.

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
product is optimized for one trusted operator, a single PostgreSQL database, explicit
admin controls, and predictable behavior, not public SaaS scale.

### Non-goals

- No web UI of its own beyond the Mini App. Today the only browser surfaces are the
  Microsoft OAuth callback and the Telegram Mini App (`webapp/`, served separately;
  this process only answers `/api/mini/*` next to `/auth/callback`). Slash commands
  and chat notifications stay — the Mini App is an extra door, not a replacement.
  **The same Mini App opens in a plain browser too** (owner, 2026-10-02; #157):
  outside Telegram it shows a sign-in screen. **A person signs in by email or by
  Telegram** (owner, 2026-10-04, #162) and may keep both; Settings → «Вход» adds and
  removes them. SMS and WhatsApp were considered and dropped; Discord, phone, Google
  and a platform account (#156) are not planned. Telegram is still what publishing
  to group chats and the bot's DMs need. New code must not assume that every person
  has a Telegram id.
- No `/compare` or `/top` (see the appendix).
- One `rarity_mode` per person, for every platform and every chat — not one per
  platform (see the appendix). What a person *can* switch off is a whole account's
  posts (#20).
- No live platform API calls from normal read-only commands or panels.
- No multi-tenant hosting model.

## Stack

Python 3.12+, aiogram 3, aiohttp (OAuth callback + Mini App API), httpx (platform
HTTP clients), Pillow (re-encoding uploaded avatars), psycopg 3 (PostgreSQL, #234;
aiosqlite stays only to read the old SQLite files: the import tool, old scripts), APScheduler (`AsyncIOScheduler`), pydantic v2 +
pydantic-settings, cryptography Fernet, xbox-webapi-python, the official Steam Web
API, psnawp (PSN), howlongtobeatpy, pytest + pytest-asyncio + ruff. The Mini App is
Vite + React (`webapp/`), with hls.js playing the stores' HLS trailers wherever
the browser has Media Source (Android's WebView claims HLS and fails on their
fMP4 streams; loaded only when a trailer opens).

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
├── .claude/skills/mini-app-design/   the skill that holds any Mini App look to docs/design-system.md,
│                              and a phone-sized screenshot of the dev server as a signed-in person
├── pyproject.toml             dependencies, ruff, pytest config
├── manage.ps1 / manage.bat    the dev server's process manager and its double-click dashboard
├── deploy/                    the server's nginx sites, systemd units and SSH socket, as installed
│                              by scripts/provision.sh (a fresh Ubuntu 24.04 into the bots' server)
├── webapp/                    Telegram Mini App SPA (Vite/React); built by CI, never served by the bot;
│                              `src/`: `api/`, `i18n/`, `core/` (behaviour), `styles/` + `ui/` (the
│                              design system, the one source of look), `parts/`, `screens/`, `app/` (shell)
├── docs/                      guides for whoever runs a server, English and Russian
│                              (`mail-setup.md` / `.ru.md`: the mail server for email sign-in)
│                              (`mini-app-spec.md`: what the Mini App does, for its design;
│                              `mini-app-design-brief.md`: the task for that design;
│                              `design-system.md`: the look, its tokens, components, rules)
├── catalog/                   the games catalog's labels and fitted weights, by key (`scripts/catalog_files.py`)
├── changelog/                 release notes per version (`archive/`: those before 0.3): `<v>.ru.md` / `.en.md` (what a chat member
│                              notices), `.summary.<locale>.txt` (the announcement's bullets),
│                              `.contributors.md` (what changed about working here)
│
├── bot/
│   ├── main.py                  entry point, assembly, router registration
│   ├── config.py                settings from the environment (pydantic-settings)
│   ├── lock.py                  "one process per .env" guard
│   ├── moved.py                 the old bot after a move: points DMs and groups to the new one (#238)
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
│   │   ├── psn_token.py          a player's own PSN token: its screen, pasting, linking by it (#233)
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
│   │   │   notification.py, hltb.py, psn_token.py   one per screen (admin_home and online are
│   │   │                                 redrawn on timers)
│   │   ├── keyboards.py          every inline keyboard, the close button, format_* helpers
│   │   ├── parts.py              shared vocabulary: badges, platform palette, counted nouns,
│   │   │                         per-platform header rows, value brackets
│   │   ├── lists.py              what every *text* list shares (#64)
│   │   ├── inline_lists.py       what every *keyboard* list shares: rows, paging, navigation, way out
│   │   └── date_picker.py        calendar pickers and month/day navigation (#75)
│   │
│   ├── services/                business logic; knows nothing about Telegram/aiogram
│   │   ├── achievements.py       whether an achievement may be published
│   │   ├── admin_settings.py     the admin settings' keys, bounds, labels and defaults
│   │   ├── admin_registry.py     every admin setting, described once, for both panels (#176)
│   │   ├── admin_status.py       what the super-admin's home shows, for both panels (#176)
│   │   ├── admin_credentials.py  every shared credential, one registry for both panels (#176)
│   │   ├── admin_actions.py      every super-admin action, described once, for both panels (#176)
│   │   ├── roles.py              who may do what: four roles, one table, `Access` (#232)
│   │   ├── poll_cadence.py       how often each platform is asked: the admin's steps (#184)
│   │   ├── admin_accounts.py     refresh / reset one person's game account (an action's work)
│   │   ├── admin_cleanup.py      wiping the bot's messages from a chat (an action's work)
│   │   ├── connect.py            one-time OAuth state, finishing a login
│   │   ├── relink.py             linking an account somebody else may already hold (#52)
│   │   ├── stats.py              aggregates for panels, /stats, summaries
│   │   ├── models.py, rows.py    ParsedAchievement and its AchievementRow, shared by all platforms
│   │   ├── naming.py             the naming chains (#51) — the only answer to "what is X called"
│   │   ├── time_zones.py         a person's or a chat's zone by place: the offered places, local time
│   │   ├── handles.py            nickname rules: valid, normalized, shown, first one, digits (#157)
│   │   ├── logins.py             the ways a person signs in, as the admin's cards list them
│   │   ├── people.py             who may see whom: the relation between two people, `can_view` (#157)
│   │   ├── profile_links.py      one profile-URL builder per platform
│   │   ├── presence_view.py      "where is this person right now" — /online's rule, for one person
│   │   ├── descriptions_view.py  an achievement's name/description in the reader's language (#48, #61)
│   │   ├── platform_format.py    which platform a screen names: version played, release
│   │   │                         platforms, device (#79, #114)
│   │   ├── title_catalog.py      the game-level achievement catalog, 24h debounce (#99, #80)
│   │   ├── achievement_icons.py  achievement icons on disk under data/achievements/ (#99)
│   │   ├── images.py, avatars.py, covers.py   fetch, bound, hash and store pictures (#55)
│   │   ├── custom_avatars.py     a picture a person uploads in the Mini App, re-encoded (#157)
│   │   ├── post_picture.py       a low-res post picture enlarged on a square, at send time
│   │   ├── game_art.py           a game's poster, hero and header kept on disk, served signed
│   │   ├── steam_library_art.py  a Steam game's poster and head of now, asked when its page opens
│   │   ├── manual_games.py       a game added by hand: a store link read into its name
│   │   ├── media.py              where the games database's pictures live (`MEDIA_DIR`)
│   │   ├── x360_frame.py         Xbox 360 box art kept without the console's header or bar
│   │   ├── message_log.py        request middleware: logs every outgoing group message
│   │   ├── message_limits.py     request middleware: nothing exceeds Telegram's length limits (#68)
│   │   ├── single_message.py     delete-then-send for commands that replace their own last copy
│   │   ├── release_notify.py     the release announcement on startup
│   │   ├── notify.py             notifications to the admin
│   │   ├── email.py              sending mail: one `EmailSender`, SMTP or (dev) the log (#162)
│   │   ├── email_login.py        sign-in codes by email: rules, rationing, checking (#162)
│   │   ├── invites.py            invite codes: their form, and sign-ups waiting for one
│   │   ├── passkeys.py           passkeys: options, challenges, checking (py_webauthn)
│   │   ├── notifier.py           the app's own notifications: list, push, Telegram DM (#164)
│   │   ├── webpush.py            Web Push: RFC 8291 encryption and VAPID, on `cryptography` (#164)
│   │   ├── mini_app.py           Mini App open-button URLs
│   │   ├── hltb.py               howlongtobeatpy search and resolve over the mirror; ensure_title_match
│   │   │                         is the lazy trigger for hltb_match.py below
│   │   ├── hltb_match.py         which HLTB entry a game is, scored automatically (no DB access)
│   │   ├── steam_extras.py       a game's Steam side: its app, achievement tips, patches — stored
│   │   ├── steam_guides.py, steam_news.py   Steam community guides / announcements (no DB access)
│   │   ├── stores/               what each store says about a game (#147), network and parsing only:
│   │   │                         steam_store.py, xbox_catalog.py, psn_store.py, hltb_page.py
│   │   ├── store_collect.py      collecting one game from them: versions, DLC, HLTB, when due
│   │   ├── advice.py             the advisers' review of the games matcher: questions, answers,
│   │   │                         the agreement rule, `data/advice/` (#147, no DB access)
│   │   ├── game_series.py        game series proposed from relations, labels, franchise names
│   │   ├── label_conflicts.py    labels that contradict each other (#218), no DB access
│   │   ├── game_page.py          the Mini App's game page put together from the catalog (no network)
│   │   ├── game_descriptions.py  a game's description translated once, the achievements' rule (#230)
│   │   ├── news_translations.py, guide_translations.py   Steam posts and guide tips put into the other language
│   │   ├── crypto.py             Fernet
│   │   ├── credential_health.py  what one failed liveness check of a shared credential means (#62)
│   │   ├── rate_limiter.py       shared sliding-window limiter (Xbox, Steam)
│   │   ├── api_usage.py          every outside API's requests (and the model's tokens), last 24h
│   │   ├── description_backfill.py  one Xbox title's descriptions in both locales (#48)
│   │   ├── xbox/                 auth.py (token storage, refresh), client.py (requests, retry,
│   │   │                         backoff), models.py (pydantic responses)
│   │   ├── steam/                auth.py (the admin-settable key, #17), client.py, achievements.py
│   │   │                         (fetch_unlocked + schema/rarity cache)
│   │   ├── psn/                  auth.py (the shared NPSSO, PsnAuth), personal.py (a player's own
│   │   │                         NPSSO, #233), client.py (to_thread wrapper),
│   │   │                         achievements.py (sync_account, one game at a time, #26)
│   │   ├── translate/            Anthropic API (Haiku 5.5) via raw httpx, descriptions, news posts and guide-tip pointers, never names:
│   │   │                         client.py, descriptions.py (cache-or-translate), guide_tips.py (line numbers only), auth.py (#17 shape)
│   │   └── youtube/              video guides: auth.py (#17 shape), client.py (Data API v3), guides.py (what a
│   │                             video names, no DB access), videos.py (an achievement's videos)
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
│   │   ├── title_platforms.py    Xbox games' platforms, looked up until found (#114)
│   │   ├── patch_refresh.py      played games' patch notes, re-read every few hours
│   │   ├── translations.py       the backlog of news posts, guide tips and games' descriptions to translate
│   │   ├── octopus.py            the octopus's queue, a few games assembled a minute (#215)
│   │   ├── stand_in_links.py     games made of a list's stand-in alone, linked to their namesakes
│   │   ├── season_reset.py       TEMPORARY: the first season's pass wiped as the second begins
│   │   ├── guide_videos.py       guide channels' YouTube videos: the newest page, the whole history weekly
│   │   ├── psn_trophy_groups.py  the group of PSN trophies stored before #46 (#115)
│   │   ├── description_backfill.py, rarity_backfill.py, steam_localization.py
│   │   │                         cache walkers for what polls never bring (#48, #61)
│   │   ├── reminders.py          reminders for a dead Xbox login
│   │   ├── season_start.py       the season's start told at noon on the 1st
│   │   ├── message_cleanup.py    auto-deletes system messages
│   │   ├── online_refresh.py, admin_refresh.py   self-refreshing /online and /admin
│   │   └── service_health.py     liveness of the shared credentials
│   │
│   ├── web/                     oauth.py (OAuth callback + Mini API mount), mini_api.py (JSON,
│   │                            Init Data auth), mini_auth.py, mini_me.py, mini_chat.py,
│   │                            mini_admin.py (secrets never leave it), mini_game.py (the game page,
│   │                            the games search, favorite games), mini_avatars.py,
│   │                            mini_session.py (the cookie), mini_logins.py (email, the logins kept),
│   │                            mini_notifications.py (the list, push subscriptions),
│                            mini_invites.py (signing up with an invite, a member's codes),
│                            mini_passkeys.py (adding, listing, signing in with passkeys),
│                            mini_pass.py (the season pass: its state, claiming a theme),
│                            mini_share.py (a shared post's page with its card's tags)
│   │
│   └── db/
│       ├── postgres.py           psycopg 3 behind aiosqlite's face: placeholders, rows, autocommit,
│       │                         numbers and dates sent untyped (#234)
│       ├── pg/                   the PostgreSQL schema: app.sql (a server's own tables), games.sql
│       │                         (the shared catalog), migrations/ (numbered on from 144)
│       ├── repo/                 all data access, the only place with SQL; one Repo from mixins
│       │                         (map in its __init__.py); `_sql.py` holds the shared joins (#52);
│       │                         `_games_db.py`: which tables are the shared games catalog (#229)
│       ├── schema.sql, migrations/   the SQLite schema and its history up to 143: the import
│       │                         tool's tests build a source from them, and it reads the names
│       └── tools.py              a database opened by a script: `--schema`, `run`, `connect`, `backup`
│
├── scripts/                     one-off operational helpers, outside the running bot
│   ├── render_screen.py          draws any screen, prints it or sends it to the owner's DM (#63)
│   ├── check_integrity.py        stored achievements vs what each platform reports, read-only (#120)
│   ├── collect_game.py           collect one game from the stores now (#147), beside a running bot
│   ├── reparse_store_payloads.py the store side again from the kept answers, no request (#147)
│   ├── catalog_viewer.py         a bare local, read-only viewer of the games' store side (#147)
│   ├── sqlite_to_pg.py           a server's SQLite files into PostgreSQL: preflight, import, verify (#234)
│   ├── fit_match_weights.py      the games matcher's weights fitted to the operator's labels (#147)
│   ├── advise_pairs.py           the matcher's doubtful pairs to Claude and Gemini and back:
│   │                             export / import / status / apply / conflicts (#147)
│   ├── xbox-deploy.sh            what CI runs on the server (/usr/local/bin/xbox-deploy)
│   ├── db_status.py              summary for `manage.ps1 status`
│   ├── pull_games_and_achievements.py, reconcile_achievements.py   bulk history syncs
│   ├── cache_achievement_icons.py                                   icon pre-caching (#99)
│   ├── strip_x360_frames.py      the 360 frame cut off the covers and posters already kept
│   ├── collect_x360_addons.py    a 360 game's add-ons searched once, where never searched yet
│   ├── translate_game_descriptions.py   every game's description translated at once (#230)
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

Required environment variables: `BOT_TOKEN`, `SUPERADMIN_TG_IDS` (comma-separated
super-admins), `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET`, `OAUTH_REDIRECT_URL`
(public HTTPS — Microsoft rejects `http://` and `localhost`), `FERNET_KEY`.

The database (#234): `DATABASE_URL` (a PostgreSQL DSN; the dev default is the
project's own cluster, `postgresql://localhost:5433/unlocked?user=postgres`) and
`DATABASE_SCHEMA` (this server's own schema: `prod`, `test`, `dev`; the catalog is
the schema `games`, shared). `DB_PATH` no longer names the database: its folder is
where the server keeps its files (the lock, the advisers' answers).

Optional: `LEGACY_BOT_TOKENS` (the tokens of bots this one replaced, #238: the
Mini App opened from their posts arrives signed by them and is still accepted,
`Settings.mini_app_tokens`; never used to poll or send), `STEAM_API_KEY`,
`ANTHROPIC_API_KEY`, `YOUTUBE_API_KEY`, `OAUTH_LISTEN_HOST` /
`OAUTH_LISTEN_PORT`, `MEDIA_DIR`, `LOG_LEVEL`, `MINI_APP_URL` (empty disables the Mini
App entry points), the poller intervals (a first-run seed: the polling steps are
`app_settings` since #184 stage 0, see Polling model), and the mail server for email sign-in
(`SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY` starttls/ssl/none, `SMTP_USERNAME`,
`SMTP_PASSWORD`, `SMTP_FROM` — a bare address, it is also push's contact; #162;
setting it up: `docs/mail-setup.md`).

- **No mail server, no email sign-in** — not an error: the sign-in screen offers
  Telegram only. For the dev server only: `EMAIL_LOG_CODES=true` writes the codes to
  the log instead of sending them, and `EMAIL_SKIP_CODE=true` takes a typed address
  as proved with no code at all (anybody could sign in as anybody, so it is ignored,
  with an error in the log, whenever `SMTP_HOST` is set). Another way to send mail is one more class
  behind `services/email.py::EmailSender`.
- **The mail server's login is set from /admin** (owner, 2026-10-07;
  `services/smtp_auth.py`): «🔑 Ключи платформ» → «Почта (SMTP)», or the Mini
  App's admin → «Ключи», "login key" in one message, checked by logging in to the
  server, kept encrypted, read by the sender on every message (no restart; the
  sender and both panels share one `SmtpAuth`). `SMTP_USERNAME` / `SMTP_PASSWORD` are a
  first-run seed like the keys below; `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`
  and `SMTP_FROM` stay in `.env`. Both admin homes show sign-in emails sent in the
  last hour and day against the app's hourly cap and the mail service's daily one
  (`email_provider_daily_limit`, 300 — Brevo's free plan).

- **`STEAM_API_KEY`, `ANTHROPIC_API_KEY` and `YOUTUBE_API_KEY` are first-run seeds**
  (#17): the auth wrapper (`SteamAuth` / `AnthropicAuth` / `YouTubeAuth`) imports the env value once into
  `app_settings`, encrypted, and from then on the admin panel's "🔑 Ключи платформ"
  owns it — set / change / clear with no restart. Clearing it in the panel disables
  the seed, so a stale env var cannot resurrect it. No Steam key: `/connect_steam`
  says "not configured". No Anthropic key: translation is skipped. No YouTube key:
  no video guides. None is fatal.
- **Everything else tunable lives in `app_settings`**, editable live from `/admin`
  and the Mini App's admin (both from `services/admin_registry.py`): display
  limits, summary caps, HLTB limits, `account_reset_cooldown_hours` (see Data
  model, default 24h, 0 = off).

## Data model

The canonical schema is `bot/db/pg/app.sql` (a server's own tables) and
`bot/db/pg/games.sql` (the shared catalog), PostgreSQL since #234; this section
describes the model, not every column. `bot/db/schema.sql` and `bot/db/migrations/`
are the SQLite history (up to migration 143), kept for the import tool and its
tests only: a migration number or a column named below may point there. History: #106.

### One games database for prod and the test server (#229)

- **One PostgreSQL database, a schema a server and one for the catalog**
  (owner, 2026-10-30; #234): `prod`, `test`, `dev` (`DATABASE_SCHEMA`) hold each
  server's people, accounts, what they earned, chats and `app_settings`;
  `games` holds every table about games, achievement lists and the stores
  (`CATALOG_TABLES` — the lists and their achievements, Steam's caches, guides,
  the games catalog, the HLTB mirror, store answers, `fetch_state`, the
  octopus's queue), shared by prod and the test server. The connection's
  search path is `<server>,games`: a table nobody qualified is found in the
  server's schema first, then in the catalog — what attaching the games file
  did on SQLite — so queries name no schema. The catalog's pictures are one
  folder for both (`MEDIA_DIR`, below).
- **A migration touching the catalog runs once per server against the one
  schema**: it writes `games.<name>`, must only add (a table, a column, an
  index) and be idempotent (`IF NOT EXISTS`, a backfill that does not care that
  it ran before). The test server runs ahead of prod on the same catalog, so
  prod's older code must keep working on a catalog the newer one migrated.
  **A global rework of the catalog** — a migration that rebuilds, renames or
  drops a catalog table — **cannot be shared**: the two servers part for its
  duration (a copy of `games` for one of them), and join again once both run
  the new code.
- **One linker at a time across both bots** (`pg_try_advisory_lock`, `GameLinker`).
  **The catalog's background work may run on both bots**: the octopus and the
  store collection run wherever `store_collection` is on. A queue entry is
  taken by a conditional update that only one bot can win and held
  (`octopus_take`, half an hour), so two bots never assemble one game.

### Bring-up and migrations

- **A schema with no tables is made from its file; migrations bring an
  existing one up** (`db/repo/_database.py`, #234): `games` from `pg/games.sql`
  when it is empty, the server's schema from `pg/app.sql` when it is, and a
  schema made so is **baselined** — the migrations of `pg/migrations/` are
  recorded as applied without running, so a migration only has to work against
  the schema it was written for. A migration is one transaction
  (`BEGIN … COMMIT` around its file); a new column or index goes in the
  migration *and* in the schema file, for databases made after it.
- **Every foreign key is DEFERRABLE** (the `DO` block at the end of each schema
  file): merging two people moves a Telegram id from one row to the other and
  defers the checks with `SET CONSTRAINTS ALL DEFERRED` (`_merge.py`).
- **A failed bring-up stops the process.** `connect()` closes the connection
  before re-raising; the same holds for anything later in `run()` before polling
  starts: `main()` ends a run that raised with `os._exit(1)`, so systemd
  (`Restart=on-failure`) starts it again, and `bot.me()` at start-up is retried
  for ~2 minutes because Telegram is sometimes briefly unreachable.
- **A database ahead of the code refuses to start** (`SchemaTooNewError`, #56) —
  that is how an older build learns a newer one already migrated it. The
  version's D counts both migration folders (`bot/version.py`).
- **Rehearse a migration on a copy of production before the release that carries
  it** — a copy of the schemas (`pg_dump` / restore into a scratch database), the
  real `Database.connect()`, rows counted on both sides. Production's particular
  history breaks migrations no test can.

### People and accounts (#52)

- `users` has an id of its own (`users.id`, migration 071; #156 step 1) and keeps
  the Telegram identity as `tg_id` — unique, and empty for a person who will sign in
  another way. **The tables about a person point at `users(id)`** (migration 078,
  #156 step 2): `account_links`, `tokens`, `user_settings`, `subscriptions`,
  `notification_throttle`. What is Telegram by nature keeps a Telegram id:
  `chat_seen`, the admins' ids, and the reset cooldowns (`platform_cooldowns*`), which
  must outlive a deleted person to stop a delete-and-rejoin. **Code speaks in person
  ids** (#156 step 3): the repo's methods about a person, the services, the pollers
  (`target.person_id`), the publisher and the Xbox login all take `users.id`; the
  Mini App's request user carries `person_id`, and `PersonMiddleware` hands
  handlers theirs. **A Telegram id is resolved once, at a Telegram door** — an
  update, a callback, an old link that still names a Telegram id — with
  `repo.person_id(tg_id)` / `get_user_by_tg`, and `repo.tg_id_of(person)` goes
  back for what is Telegram's (a DM, the cooldowns). A chat's members
  are person ids (`_sql.member_source`, `(chat_id, person_id)`): subscriptions,
  and `chat_seen` through `users`. 071 and 078 rebuild their tables with foreign keys
  switched off inside the script itself (the pragma does nothing inside a
  transaction); a migration that rebuilds a parent table follows the same shape.
  **Each way to sign in is a field on the person** (#156, #162): `tg_id`, and
  `email` (migration 079 — lower-cased, unique, set only once a code proved it). A
  person may have no Telegram and no platform account at all — someone who signed
  in by email only to follow friends. Such a person has no person-side reset
  cooldown (it is keyed by Telegram id); the per-account count still holds. A
  column added to `users` that needs an index gets it in its migration, with the
  rule written into the `CREATE TABLE` for new databases: `schema.sql` runs before
  the migrations, so a standalone index on a new column fails on an old file.
  **Merging two people** (built; `services/merge.py`, `db/repo/_merge.py`): when a
  signed-in person adds a login that is somebody else's and proves it (an email's
  code, the Login Widget's signature, or writing to the bot through a `link_`
  token), the app is offered the merge instead of `taken`. **Opening a `link_`
  token is not consent** — anybody can be sent one: when that Telegram already is
  somebody with something to lose, the bot first asks *them* («Объединить» /
  «Отмена», naming both accounts, `lnkm:yes|no`), and only their yes offers the
  merge in the app (`PeopleMerge.ask_to_confirm` / `confirmed`). The person signed in
  stays, with their nickname; the other is folded in and deleted, in one
  transaction. One side empty: take the other's. Both have one (Xbox, Steam,
  Telegram, email): the person picks, and the account not picked is unlinked like
  any unlink, its history kept; the Xbox login follows the Xbox account kept. PSN
  accounts add up to `MAX_PSN_ACCOUNTS`, past that the person picks. Chats, follows
  and blocks (never a self-follow), sessions, notifications and push devices move;
  settings come from the side changed more recently. A person the bot made a
  moment ago (a Telegram account's first message, with nothing to lose) is folded
  in without asking. Offers and `link_` tokens live in memory for ten minutes. The
  merge defers foreign keys to commit (`chat_seen` points at `users.tg_id`, which
  moves between the two rows).
  **Roles** (owner, 2026-10-28/29; `users.role`, migration 140,
  `services/roles.py`, #232): `superadmin`, `admin` (the app admin), or none
  (an ordinary person); a chat's admin is not a person's role but the chat's
  (`chat_admins`, see Admin).
  The super-admins `SUPERADMIN_TG_IDS` names are always super-admins — written
  into the column on every start and on `/me`, never changed from the app —
  and must always keep a Telegram id: nothing (removing Telegram, a merge) may
  leave them without one; both refuse with `admin`.
  `accounts (platform, external_id, display_name, secondary_name, gamerscore,
  psn_trophy_level, achievements_visible, avatar_*, …)` is a platform account on its
  own terms (`platform` is `xbox`/`steam`/`psn` — one Xbox account covers both
  generations). `account_links (person_id, platform, external_id, is_active, linked_at,
  unlinked_at, publishes)` says who holds it now and who held it before, and whether
  the holder announces its achievements (#20: the person's own switch per account; a
  muted account still counts in stats, summaries and `/online`).
- **Unlinking never deletes**: the link is deactivated, the account and its history
  stay, and relinking finds them. `idx_links_one_active_per_platform` allows one
  account per platform per person — **dropping it is all multi-account support
  (#10) needs**; `idx_links_one_owner` gives an account one current owner.
- `User` still exposes `xuid`/`gamertag`/`gamerscore` through the `XBOX_ACCOUNT`
  join in `db/repo/_sql.py`, so Xbox call sites kept their names.
- `accounts.achievements_visible` (#5) is the last *checked* answer to "can the
  shared credential see this account's achievements": `NULL` until checked, set at
  connect and by every backfill/resync, never read live from a UI path.
- **Reset cooldowns** (`platform_cooldowns`, migration 054; per account
  `platform_cooldown_accounts`, 067; PSN allowance, 068), inside
  `account_reset_cooldown_hours`. Two sides, both checked on every re-link:
  - **the account's own count** — every account, each PSN account on its own,
    whoever deleted it, so switching Telegram accounts does not dodge it: one free
    re-link, a second reset blocks it;
  - **the person's count on the platform** (the Telegram-account ban): one deletion
    counts once. Xbox and Steam: one free re-link, a second deletion blocks. PSN
    counts re-links instead: **as many free as PSN accounts were held at the
    deletion** (owner, 2026-09-30), one more inside the window is blocked, and a
    second deletion adds none.

  A super-admin's reset clears both.

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
  spoiler. `trophy_type` is the PSN tier; `trophy_group_id` is the achievement's
  group (migration 118, owner, 2026-10-15): PSN's own (`default`, `001`…) —
  `NULL` there on rows stored before #46, which is how the poller knows a game's
  DLC trophies were never fetched —; **Xbox's own: `base`** (the list
  a game shipped with) **or `non_base`** (added later: a DLC, an update), from
  contract 6's `groupIds` (`["0"]` / `[]`; migration 121, owner, 2026-10-15) —
  what a Mythic achievement counts; Xbox has no group per DLC; **an Xbox 360
  list says nothing of its groups** (no `groupIds`, `sequence` 0, `flags` mixed):
  they are derived — in id order, base while the running gamerscore stays within
  the release's, 200 G for an Arcade game (title id 0x5841…), 1000 G otherwise
  (`xbox.models.x360_groups`, owner, 2026-10-15; an Arcade game's 400 G when its
  running sum stops at 400 — a stop at 200 on the way is a coincidence —, 200 G
  when it stops only at 200); **such a group is marked
  `group_source = 'derived'`** (migration 122) — provisional: a group the
  platform gives later (`'platform'`) replaces it, and a derivation never
  overwrites the platform's; `NULL` until a
  contract-6 read (the catalog's) says, and an earned row takes its group from
  the catalog when the list is read whole —; **`main_game` on Steam**, which has
  no groups (`constants.achievement_group`, applied where `seen_achievements`
  and `title_achievements` are written).
- **A Mythic and a completion are marks on the earned row that brought them**
  (migration 123, owner, 2026-10-16; Xbox, both generations): `mythic` on the
  last of the game's base list to be earned, `completes` on the last of its whole
  list — set by `repo.mark_xbox_completions` after each new unlock and when a list
  is read whole. A Mythic is kept for good (a base list never grows); a
  completion is taken back when the list grows past what was earned, and marked
  again on its new last achievement (owner, 2026-10-16). Only a
  list read whole (`listed`) counts; no Mythic where the groups are unknown. Not
  announced as achievements yet. The completion counters (🌀, `/stats`) still
  count as before. **A PSN trophy group past the base game is a
  DLC row (`dlcs.trophy_group_id`) of every version of its list**, stand-ins
  included, made whenever the groups are saved (`save_title_groups`); Sony names no
  store product for a group, so the link to a store's own DLC is by name, if ever.
- **`device` — what an achievement was earned on — is a fact or `NULL`, never a
  guess** (#79; owner, 2026-09-24; migration 059). Its sources: Xbox presence while
  that game is being played (the exit poll uses the device presence last reported);
  PSN presence while the person is online, on a game released on several
  platforms; otherwise `NULL` — a single-platform game needs none, its version is
  known from the game (#114). Steam stays `NULL` (PC or Steam Deck cannot be told
  apart). Presence codenames (`Scarlett`, `Durango`, `Web`, `PS5`) —
  `services/platform_format.py` normalizes them.
- **A game's platforms (`achievement_list_connectors.platforms`) are what it was released on** — from
  Xbox titlehub or PSN's title listing, never from presence. Presence codenames
  found there (`Scarlett`, `Durango`, `WindowsOneCore`, `Web`, …) were device
  guesses and were cleared by migration 059 for titlehub to refill. An Xbox game
  without them is looked up in titlehub (#114, migration 060): before its
  achievements publish (`Fetcher.ensure_title_platforms`) and by
  `poller/title_platforms.py` for the rest, at most three times an hour apart
  (`platforms_attempts`, `platforms_checked_at`); after the third failure
  `platforms` is `'[]'` — known to be unknown.
- `publications` records what was posted to each chat, with its message id.
  `bot_messages` logs every bot message in a group (`is_system`, `is_achievement`,
  `preview`) for cleanup and `/delete_last`; `tracked_messages` holds the one copy a
  self-replacing command keeps per scope; `online_auto_refresh` and
  `admin_panel_refresh` the self-refreshing screens.

### Chats and settings

- `chats` + `subscriptions` (who publishes where — nothing else: #126 moved the
  per-subscription settings out). `chat_settings`: summary time, timezone, muted
  games, daily-summary switch, anti-flood `flood_limit`/`flood_window_minutes`,
  `locale` (its `rare_threshold_percent`, `digest_threshold` and `min_gamerscore`
  columns are no longer read — the threshold and the digest size are global, see
  Publication rules). `user_settings`: **`rarity_mode`** (all / rare / hidden, one for every chat;
  new people start from `app_settings['default_rarity_mode']`), timezone, muted games,
  `show_secrets` (Mini App only), `locale`. (`show_profile_links` is left unread:
  profile links are one admin switch, `app_settings['show_profile_links']`, on by
  default — owner, 2026-09-29.) Somebody in many chats used to set the mode in each (#126).
- **Favorite games** (`favorite_games (person_id, game_id, anchor_key)`, migration
  130; owner, 2026-10-25): a person's hearts on games. `anchor_key` is the
  game's anchor version as `store:product_id:console`, and a favorite is
  found by it first — a catalog carried over or merged (`scripts/sqlite_to_pg.py`)
  may give a game another id and the old id to another game —, else by its
  id (a merged game leading on). A merge of two people moves them.
- **Season pass claims** (`pass_claims (person_id, palette, month)`, migration
  131; owner, 2026-10-27): the themes a person claimed, each checked against
  the month's points by the server (User interface: the season pass). The
  pass's levels are `pass_items` and a prize's codes `pass_item_codes` (133;
  a draft and waiting changes live on the row): a game prize is a game of the catalog or, when the
  catalog lacks it, one named by its title alone (owner, 2026-10-28; a key is
  for other services); a prize wears a tier as a theme does (`tier`: common / rare /
  legendary / mythic, common when none was set; owner, 2026-10-28) and says
  which platform it is for, `platform`, free text
  (Xbox, PlayStation, Steam or anything typed; 135); a code is taken once `claimed_at` is set, `person_id` says by whom (a
  merge moves it; a deleted person's code stays taken). The levels each person reached this month
  are `pass_reached (person_id, item_id, month)` (134; a merge moves them).
- **Anti-flood state**: `notification_throttle (person_id, chat_id, window_started_at,
  count_in_window, throttled)`. No buffer table — a held-back achievement is exactly
  one missing from `publications` for that chat, which `unpublished_achievements()`
  finds.

### Games, caches and pictures

- **Presence**: `presence_state` (Xbox), `steam_presence_state`, `psn_presence_state`
  (#1, unrelated to the trophy scan). PSN scan progress: `psn_title_progress`,
  `psn_poll_state`. Xbox history: `title_history`. Steam: `steam_schema_cache`,
  `steam_rarity_cache`. HLTB: the mirror (`hltb_entries`, #147). Steam guides and patches: `steam_apps`,
  `game_patches`, `title_guide_reads` (see Steam guides and patches).
- **The games catalog is the one place a game lives** (owner, 2026-10-30):
  wherever a game is shown — its name, its picture, a card, a list of games, a
  tap that opens it — it is the catalog's game (`games`, through
  `repo.game_of_list` from an achievement list), never an achievement list's
  row or a snapshot of it. A list that is in no game yet is adopted as one
  (`repo.adopt_list_as_game`). What stays per list is only what is the list's
  by nature: progress and completion (a game played on several platforms is
  one list each, never summed). **The Mini App takes it so everywhere**: the
  feed, the month's games, what is trending, news, notifications, an
  achievement's page, a list's page, what somebody is playing — each item
  carries its game (`game_page.games_of_lists`: `game_id`, name, poster,
  hero) and opens it by `game_id`; **the month's games are one card a game**
  (`mini_chat.month_games`): the month's count summed, the progress of the
  platform furthest along shown (the game's page switches between them). The bot's chats keep naming the list
  as before (owner: the chat bot is apart). **A list in no game yet** becomes
  a game on its first visit and is linked at once (`GameLinker.link_title`,
  local, no network), so the same game on two platforms is one game; the
  lists adopted before are walked by `poller/stand_in_links.py` (40 stand-in
  versions a tick, a version looked at rests a week, then two, a month:
  `fetch_state`). A game page opened by `game_id` is cached by the game *and*
  whose progress it shows (`GamePage.refKey`).
- **`achievement_list_connectors`** (formerly `titles`, migration 117; owner,
  2026-10-15) **is not a game**: it links a game's versions to one achievement
  list on one platform and keeps that list's own facts — the platform's name
  for it, its size, platforms, when it was checked. A game's name, cover and
  description are `games` and `versions`; a screen never presents a row of it
  as a game. A stand-in version's name follows its list's (a trigger); a list's own id is never a name (migration 132: an adviser cannot look a number up), the English name stands in, and `scripts/restore_list_names.py` takes names another copy learned.
  The code says `titles` in places (variables, `title_id`, `titles_on`): the
  name of the thing before it was renamed, not another table.
- One row per list (one achievement list on one platform),
  **keyed by `(platform, title_id)`** like `seen_achievements` and
  `title_achievements` (#147, migration 090): Steam appids and Xbox title ids
  overlap. Join on both (`_sql.titles_on`). An Xbox id is one game, so a
  lookup by any Xbox value matches either generation (`_sql.platform_is`,
  which also takes `xbox` for a caller that only knows the family, as
  presence does); a game found to be the other generation moves, row,
  achievements and catalog together (`update_title_platform` /
  `_move_title_rows`), and a 360 game stays 360 (`stored_xbox_generation`).
  `title_guide_reads` is keyed the same way; `title_groups` stays by id (PSN
  only). No foreign keys point at `achievement_list_connectors`. Its columns: names (`name`, `name_ru`, `name_en`),
  `achievements_total`, `platform`, `platforms` (#79), cover art (`icon_url` +
  `cover_path`/`cover_hash`/`cover_checked_at`), `achievements_checked_at` and
  `tips_checked_at`. **Which Steam app a list is** is not a column of it either
  (migration 114, owner, 2026-10-15): a Steam list is its own app, any other is
  known by the app found for it — HLTB's page, or Steam's store search — kept as
  a `steam_twin` id on the versions of the list (`versions.store_ids`), read by
  `_sql.STEAM_APP_OF_TITLE`, and when it was last looked for is `fetch_state`
  (`steam_app`).
  **Which HLTB entry a list is has one home, the links of its versions**
  (`version_hltb`, migration 110; owner, 2026-10-14): `achievement_list_connectors.hltb_id` and its
  three companions were a copy that the Mini App read and the operator's links
  never reached. Every list is at least one version (a stand-in made from the
  list, `stores.stand_in_for`), so it has somewhere to be linked;
  `repo.list_hltb_match` is the one reading (the operator's link before an
  automatic one, then the surer score, then the lower id; a list carried by a
  version as a regional twin is found through it). A link has a source: `auto`
  (the matcher, with its `score`), `manual` (the operator's, kept through every
  check and replacing a refusal) or `rejected` — said not to be this version's,
  by the operator, the advisers or the evidence check, so no collection or
  match makes it again. When a list was last asked about is `fetch_state`
  (`hltb_match`, subject `platform:title_id`).
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
- **The achievement catalog** — `title_achievements` (#99, migration 053) — is
  **the one store of an achievement's names, descriptions and rarity** (#119): the
  three cache tables that predated it were merged into it (migration 062), because
  a fact one side learned was invisible to the other. Keyed by the achievement,
  never by who earned it, so a translation is paid for once.
  - `TitleCatalogService` refreshes a title's full list at most every 24h
    (`achievement_list_connectors.achievements_checked_at`); those rows, and Steam's per-game response,
    are the whole list and are written `complete=True` → `listed = 1`. Everything
    else — a percentage, a name, a description, a live Xbox/PSN poll's earned-only
    rows, the seed migration 053 took from what people had earned — leaves
    `listed = 0`. **Only listed rows count as the game's list** (its size, the Mini
    App, 100% completions), or one person's unlocks would pass for the whole game.
  - **Descriptions**: `description_source` says how they came — `native` (the
    platform gave two different strings), `llm` (it gave the same text twice, so
    `services/translate` filled the gap), `fallback` (no Anthropic key: shown
    untranslated, `description_ru` NULL, re-offered to the translator), NULL (never
    through the translator yet: rendered as it is, and still queued). Only
    `services/translate/descriptions.py::bilingual_descriptions` sets it, and a
    catalog refresh never overwrites a description that has one. **A Russian side
    is trusted only when `description_source` is set** (#127): a platform with no
    Russian answers the Russian request with its English, and a catalog refresh
    that stored it under `description_ru` once made every poll skip the
    translator. **Russian means Cyrillic** (`util.looks_russian`, owner): text with
    Cyrillic, or with no letters at all ("100%"). Anything else — the English off by
    a period, "<Translated text>", another language — goes to the translator; the
    old test, "differs from the English", let all of those through as native.
    `poller/description_backfill.py` translates Steam/PSN rows from the English
    already stored, without a platform request.
  - **Names**: the platform's own two strings, **never translated**, from the same
    two locale requests. Each platform's main call fixes one language (Xbox/PSN
    English, Steam Russian), which is why both are kept.
  - Icons are cached under `data/achievements/{platform}/{title_id}/`, **at most
    1280 px on the longer side** (owner, 2026-10-23; `achievement_icons.shrink`):
    Xbox hands out 1920×1080 PNGs of 2–4 MB, which took 4 GB of the disk and
    reached phones whole. A larger picture is scaled down on download — PNG
    when see-through, JPEG otherwise; a smaller one is kept as it came. Icons
    cached before were shrunk once at start-up (`shrink_cached_once`).
  - **Tips** (`tip_en`/`tip_ru`/`tip_source`/`tip_translation`): how to get it, from
    the Steam community's guides. The text sits in its own language's column; the
    other stays NULL until a translation fills it and says so (`tip_translation =
    'llm'`, like `description_source`). **Every tip is translated into the other
    language** (owner, 2026-10-30; `services/guide_translations.py`): a game's tips
    together, a few a call beside their achievements' names and descriptions,
    as soon as they are worked out (`SteamExtras.on_guides_saved`), and the ones
    kept before by `poller/translations.py`; a changed tip loses its
    translation (`replace_title_tips`) and gets a new one.
- **What a message renders from**: `services/descriptions_view.py` swaps in the
  reader's language from the catalog per chat, falling back to the other language
  and then to `seen_achievements`' own snapshot. Rows are copied, never mutated —
  the publisher renders the same list once per chat.
- **Rarity**: see Lists and tables.
- **The games database's pictures are one cache for prod and the test server**
  (owner, 2026-10-28; `services/media.py`): `MEDIA_DIR` (on the VPS
  `/srv/unlocked-media`, owned by `botsvc`) holds `achievements/` and `covers/`
  (list covers, `art/`, `editions/`, `hltb/`) — and every picture the catalog
  adds later; unset, they stay under `data/`. A file's name never depends on the
  server and every write is a rename, so both bots share it. People's pictures
  (`data/avatars/`) stay each server's own; the dev server keeps its own cache.
- **An Xbox 360 game's art is kept without the console's frame** (owner,
  2026-10-28; `services/x360_frame.py`): the portrait box art loses its header
  (the "XBOX 360" logo, Platinum Hits, Games for Windows LIVE, ARCADE — the top
  13%), the store's 720×1080 poster its white "XBOX 360" band (the top 126
  px), the 1080 px square tile its green "XBOX 360" bar (the left 190 px).
  Cut on download — a 360 list's cover (`covers.download(platform=)`) and a
  poster from a 360 list's icon or its backward-compatible product's store
  page (marked `#x360`, so `game_art` cuts it; a fragment is never sent) —; anything else is left as it came, and a
  picture cut once is neither shape. What was kept before is cut by
  `scripts/strip_x360_frames.py` (no request, beside a running bot).
- **Pictures are downloaded, not linked** (#55): a Telegram `file_id` is useless
  without the bot token and a platform URL can break. Telegram photos
  (`users.photo_*`) and account avatars (`accounts.avatar_url/path/hash`) go to
  `data/avatars/`, covers to `data/covers/`, paths stored relative. Avatar URLs come
  from calls the bot already makes (Xbox `GameDisplayPicRaw`, Steam `avatarfull`, PSN
  `avatars`); `poller/avatars.py` re-checks each subject weekly and skips unchanged
  ones. Covers: Steam's is a fixed CDN path (`library_600x900`, portrait, else
  `header.jpg` for games older than the library view, #117; a game released
  lately is at neither — its art sits in a hashed folder, so the store's
  `header_image` is asked for then, one request, 2026-10-17), PSN's
  rides in the trophy listing, Xbox's costs a titlehub call — `poller/covers.py`
  rations three a minute and visits each title **once** (art does not change).

### The store side of a game (#147, stage 2; migration 091)

What the stores and HLTB say about a game. Games and their links came in
stage 3; the Mini App's game page (stage 5) shows them — see User interface,
«The game page».

- **A version is a store product on one console** (owner, 2026-10-08):
  `versions (store, product_id, console)` — PS4 and PS5, One and Series are two
  versions even when they share one achievement list; Xbox Play Anywhere's PC is
  `also_on`, never a version. Consoles are `platform_format`'s names (+ `steam`).
  **A PC version is named by its store wherever a version's platform is
  shown** (owner, 2026-10-12; `stores.console_label(store, console)`, one
  helper — and its SQL twin in the viewer — from one table, `PC_LABELS`, a
  new store being one line): the Microsoft Store's "xbox pc", Steam's
  "steam", later "egs pc", "gog pc"; a PC of no known store (an Xbox `Win32`
  list of a game bought elsewhere, HLTB's plain "PC") "pc (store unknown)".
  The stored value and the matcher's maps stay `pc`. **"pc (store unknown)"
  is a fallback** (owner, 2026-10-12): it only says "the game is on PC", so
  once the game has a PC version in a known store (xbox pc, Steam, later EGS,
  GOG) it takes the role `covered` — kept in its game (it still draws its
  namesake in) and shown nowhere but the game page's full table.
  A version points at its achievement list (`platform`, `title_id`) once that is
  proved; `versions.store_ids` (a JSON list of `[kind, id]`, migration 109 — it was
  the table `version_store_ids`) holds every id naming it (regional CUSAs, the Xbox
  title id). `origin` is `played` or `store` (found, nobody here owns it).
- **A PC version's store is `versions.store`** (owner, 2026-10-12): `xbox`
  (Microsoft's, console `pc`), `steam`, later `egs`, `gog` — one more value
  each, no schema change; a store not known is `unknown`
  (`stores.UNKNOWN_STORE`, migration 104) rather than a flag on a stand-in,
  so a known store slots in by value. An `xbox_modern` list whose platforms
  are `Win32` alone and that has no Microsoft Store product is the Xbox app
  seeing a PC game launched from another store (Heavy Rain on Steam, never on
  Xbox): its stand-in is such a PC version, never "xbox pc"
  (`stores.pc_of_unknown_store`). It sits in the game of its namesake
  (`unknown_pc_namesake`, a strong "same" sign: the very same release name,
  any store) and stands alone only when nothing here has that name. HLTB's
  "PC" is no version (it names no product, see below).
- **How a version came into the database is recorded** (migration 116, owner,
  2026-10-15): `versions.found_how` — `list` (a stand-in made from the list),
  `played` (the store product of a list somebody here has), `sibling` (another
  store's product found for a list), `hltb` (a Steam app an HLTB entry names),
  `search` (a store searched by name), `earlier` (made before this was
  recorded) —, `found_via` (what found it: `platform:title_id`, `hltb:<id>`,
  `name:<…>`) and `found_at`. Set when the version is made and never rewritten
  by a later look (`save_version(found=…)`); a stand-in that becomes its
  store's product turns `played`.
- **An edition's pictures** (migration 120, owner, 2026-10-15): `editions.media`
  in the versions' shape — the roles we use (`cover`, `poster`, `background`,
  Steam's `header`) and `images`, every picture with the tag its store gave it
  (Xbox's `ImagePurpose`, PSN's `role`, Steam's field) —, read by
  `services/edition_media.py` from Xbox's bundle product, PSN's product page,
  Steam's package (whose answer is kept now, `steam_package`); the cover on disk
  (`editions.image_path`, `data/covers/editions/`). `scripts/edition_media.py`
  fills it from what is kept and downloads the covers.
- **Kinds of link**: see Games below — a remaster, a remake, a compilation, a
  VR version are games of their own (2026-10-11); a demo, a tool (a
  Creation Kit, an editor — owner, 2026-10-10) and a mode (owner, 2026-10-12:
  a Steam app of type `advertising` launching one mode of another app, "Call
  of Duty: Black Ops II - Zombies") belong to one version of their game
  (`versions.of_version_id`, role `mode` since migration 100), joined to
  the game whose name opens theirs (`mode_of`, like `demo_of`; a mode's list
  being a part of its game's is no compilation's sign). Names: a leading
  Microsoft "COD" reads as "Call of Duty" (`game_match._COD`, one rule, no
  alias table). A **friend's pass** (owner, 2026-10-25: a free copy to play
  the whole game with its owner — It Takes Two, Split Fiction) is a role of
  its own, `pass`, joined like a demo (`pass_of`).
- **Sources**, one module each in `services/stores/`, network only:
  - Steam `appdetails` (no key; en + ru), each DLC named by its own request,
    `DLC_NAMES_PER_PASS` a pass, the rest in the next (due within the hour).
    **Every storefront request waits under one limiter**
    (`steam_store.LIMITER`): the stores' reads, the localization walker's
    names (`steam/client.store_name` reads through `app_details`) and the
    appid search alike;
  - Xbox `displaycatalog`, public, found by our title id (`lookup?alternateId=
    XboxTitleId`) — no login is spent. **A product is a version on the
    consoles the store calls it optimized for** (`XboxConsoleGenOptimized`;
    owner, 2026-10-12): a One game Series runs only by backward
    compatibility is a One version with `series` in `also_on`, and a version
    stored before on a console the product is not made for goes into the kept
    one, its labels and anchor moving with it (`retire_other_consoles`). A
    game does not list its add-ons: its editions do (`BundledSkus`); only
    Durables are kept, and **only those naming this game's products as their
    `addOnParent`** — an edition of several games bundles the others' too, and
    one an earlier collection stored goes. **A bundle is read from what it holds**
    (owner, 2026-10-24; migration 127, `stores.classify_bundle`): one game → its
    `edition` (`role` main; a `+`/`&` name is `complete`); several games, one
    primary → its edition, the rest `bonus` — unless its name says it is a set
    (Bundle, Collection, Trilogy: the PopCap Bundle flags one game primary);
    several equal games → `bundle`
    (`part`s); no game → `addon_pack` (shown with the game's DLC). Every game
    item keeps its version link; `reparse_stored` re-reads kept ones last
    (`classify_editions`, a kind set by hand kept); a save that gives no scope
    keeps it. **An add-on sold only on its own** is in no edition: the
    catalog's add-on search (`search_addons`: autosuggest's `Durable` products) by the
    game's names finds it, kept when it names the game's product as its
    parent (owner, 2026-10-27; `_xbox_addons_alone`, when due) — the only
    way to a **360 game's** add-ons (Gears of War 3's Season Pass), for its
    list, a modern list and the octopus's store-only Xbox products alike
    (`scripts/collect_x360_addons.py` searches every 360 game not searched yet). `9998-12-30` is "not on sale", no date. Each price period is an
    availability with its own end, so an answer is judged on sale **as of when
    it was given** — a stored one re-read later keeps its time
    (`sold(product, now)`; 2026-10-26: a re-parse read 548 games as off sale,
    mended by `scripts/xbox_on_sale.py`). Trailers are
    `CMSVideos`' https HLS/DASH links with their poster (the old `Videos` are
    http Smooth Streaming, unplayable); links only, nothing downloaded.
    Its cross-gen set (`versions.cross_gen_set`, 098) is one game on One and
    Series; its product group (`store_group`) can hold a whole series;
  - PSN products (owner, 2026-10-15; `stores/psn_product.py`,
    `services/psn_products.py`, `scripts/collect_psn_products.py`): a concept
    lists the ids of everything sold under it by category (`ADD_ON`, `GAME`,
    `PVU_GAME`, `DEMO`, `AVATAR`, `THEME`, `APPLICATION`) and names none; the
    product's own public page (`store.playstation.com/en-us/product/<id>`, one
    every two seconds) names it. The page's embedded JSON is kept (`psn_product`
    in `source_payloads`, prices dropped); an add-on becomes a DLC of the version
    of its console (`CUSA` PS4, `PPSA` PS5) with its name, day and description, a
    game-category product an edition. A trophy group names no store product, so
    the DLC of a group (`dlcs.trophy_group_id`) and the DLC of a page
    (`dlcs.store_id`) are two rows until the link between them is made.
    Scope so far: the games we have (`--scope played`). **A concept of more
    than `DLC_PAGES_MAX` (100) add-ons is kept as a list** (owner, 2026-10-24:
    DEAD OR ALIVE 5 Last Round has a thousand): its game pages are read, each
    add-on is a DLC by its id with no page, and one page is read when wanted
    (`psn_products.read_one`; the viewer's DLC page has the button). Whatever
    is checked against a game's DLC is checked against that list — an unread
    page is neither missing nor due.
  - PSN: the store is searched by name and a concept is accepted **only when
    Sony's trophy API says one of its title ids has our `NPWR…` list**, asked as
    an account that played it (`psn/client.trophy_lists_of`); never by name
    alone. Beside the search, the ids the game's own page on playstation.com
    names (`psn_store.game_page_title_ids`; the search misses GTA V). PSN
    add-ons have no names without the store's GraphQL, so a PSN
    version's DLC are its trophy groups for now;
  - the HLTB page (`hltb_games`, with DLC entries and per-platform times),
    linked to every version of a matched list (`version_hltb`). **Only an
    entry's own page sets its type, parent and times** (`page_read_at`,
    migration 101): a DLC's page lists its game among its relations — that
    one is its parent (`game_parent`), never its child — and another page's
    row of an entry (averages only) fills one whose own page was never read,
    and overwrites nothing. **An entry stays linked to a version only while
    the evidence agrees** (`hltb_match.entry_fits_version`, checked whenever
    the entry is looked at): no DLC's or mod's entry on a base game, no entry
    naming another Steam app (either of the two its page names), no version
    out more than `SAME_GAME_YEARS` (3) before the entry — an edition or a full
    release after early access is its game (Palworld 2024, its entry 2026), four
    years is a remake or a remaster (owner, 2026-10-14; it was a year). **An
    episode sold as a product of its own** (owner, 2026-10-15: Poppy Playtime's
    chapters) has an entry of its own, which HLTB may file as a DLC of the game:
    a version named "Episode N" / "Chapter N" keeps it (`is_episode`). **HLTB's DLC are put on our DLC only
    inside their game** (`match_dlc_entries`, `dlc_hltb`, owner, 2026-10-12):
    the entry's children against the DLC of the versions that entry stands
    for — by the Steam app a child's page names, else by the name with the
    game's taken off the front; a name two entries share, or one entry on two
    products of one store, stays unlinked. Never a store search. The consoles HLTB
    names are **not** versions (2026-10-11, 098: HLTB is matched by name, and a
    version nobody sells is no version); the game page shows them as "also
    released on" (#194).
- **On sale, off sale, unknown** (owner, 2026-10-12; `versions.on_sale`,
  `editions.on_sale`, `dlcs.on_sale` since migration 103: 1 / 0 / NULL).
  **Available** when the store offers the full product now, to buy or to
  download free — a pre-order counts; a trial, a demo SKU or a time-limited
  try does not. **Off sale** when the store still knows it and offers
  nothing more. **Unknown** when not asked, or there is no store page (a
  stand-in, a PSN DLC that is only a trophy group). Per store, from what is
  offered, never from prices: Xbox — a SKU that is not `IsTrial` with a
  current `Purchase` availability (The Crew's trial still "sells"); Steam —
  free, or some package on the app's page; PSN — a SKU granting
  `FULL_GAME`, a free-to-play app (`FREEMIUM_APP`, `UPGRADABLE`: Sony files
  those as trials) or a pre-order. The viewer says «в продаже» / «снято с
  продажи» / «неизвестно».
- **When**: `StoreCollector.ensure` — after a game's first new achievement is
  published (beside the HLTB match) and when its page is opened — in the
  background, and only what is due (`fetch_state`), so many people in one game
  cost what one does. An answer is trusted 7 → 14 → 30 → 90 days while it does
  not change; a change, or a Steam patch in the last 30 days, sets it back to 7
  (a live-service game keeps being asked). A failure is retried in an hour, given
  up on for 30 days after three. **No whole-library walk** (owner, 2026-10-09).
  **All of it waits for the super-admin's switch** (`store_collection`,
  /admin → Прочее, off by default; `store_collect.collection_on`, read on
  every run): off, neither the bot's collection nor the octopus asks a store,
  so a release carrying the catalog changes no traffic by itself. The
  operator's tools (`collect_game.py`, the catalog viewer) ignore it.
- **Raw answers** are kept in `source_payloads`, zlib JSON, the latest only, not
  rewritten when the hash is the same — never as columns on `achievement_list_connectors`.
  **Prices are not kept** (owner, 2026-10-12): each store module drops its
  price fields (`PRICE_KEYS`: Steam's `price_overview` and package prices,
  Xbox's `Price`, price history and price offers, PSN's SKU prices and
  offers) from an answer before it is parsed or hashed, so a price change is
  never "the game changed" and never sets the schedule back. No price
  columns, no currency.
- **An Xbox 360 game's store page is its backward-compatible product, proved
  by its own mark** (owner, 2026-10-12): such a product's group is
  `[Fission] <name> (<hex 360 title id>)`, read only in exactly that form
  (`xbox_catalog.fission_title_id`; the hex found anywhere else matched
  picture numbers). A product seen in passing (an edition's, a bundle's
  contents, or found by the list's names — the catalog's lookup by title id
  knows no 360 game, so `StoreCollector.x360_by_name` searches the catalog by
  name and keeps only what the mark proves; owner, 2026-10-15,
  `scripts/collect_x360.py`) is kept as `x360:<title id>`, and the 360 list's
  stand-in becomes
  the selling one (a `Purchase` ever offered, not its content twin) as its
  360 version — no release day, the product's being its comeback's
  (`link_x360_product`). `resolve_title` also asks titlehub for the
  `productId` decoration and reads `modernTitleId`; those products count
  only when their mark names that very 360 title id
  (`StoreCollector.remember_title`). **Derived from the documentation, not
  yet seen live**: the operator checks it on two or three games (Kameo,
  Banjo-Tooie, one never made compatible). No old-marketplace page: that
  store closed in 2024; a 360 game never made compatible has no store page.
  `resolve_title` reads titlehub's JSON itself (xbox-webapi's model lost a
  whole answer to `developerName: null`) and keeps its `detail`: kept as
  `titlehub:<title id>`, it gives a stand-in its studio, publisher, day and
  genres.
- **Every achievement list is at least one version**: when no store describes it
  (a 360 game, an Xbox card the catalog dropped, a PSN list not proved) a
  stand-in (`store = 'list'`) is made from `achievement_list_connectors`, and goes once a store
  product is found. A version's first proved list stays its list; another one
  (a regional twin) is kept beside it, as every list is, in `versions.store_ids`
  (`list`, `platform:title_id`).
- **A game's year is the earliest of its versions', its developer and publisher
  the earliest version's** (owner, 2026-10-10; `game_match.game_facts`, migration
  096): a version's year (`game_match.candidate_year`, the matcher's too) is
  the earliest its name ("(Classic, 2005)") or its store gives, and its HLTB
  entry's only for a stand-in (2026-10-11); a version with no studio of its own (a stand-in)
  takes its HLTB entry's; demos and compilations say nothing. Refreshed after
  every linking, the matcher's or the operator's. Beside them the game keeps how
  far its versions spread (097: the latest year, other studios, other
  publishers), shown as «2006–2025», «Epic Games и другие»; companies compare
  by `game_match.company_key` ("CD PROJEKT S.A." is "CD Projekt").
- **The advisers' full run** (owner, 2026-10-16/17): question files for every
  game, link, series, edition (`scripts/argon_export.py`), answered by Gemini
  Argon, GPT Pro and Sonnet; a decision two or three give alike is a label
  (`adviser_labels`, migration 124; `scripts/argon_import.py`,
  `services/advice_import.py`), weighed by `match_fit.label_weight`: the
  operator 0.9, three advisers 0.8, two of three 0.4. Only what all three agree
  on is written into the games (pairs of versions, refused HLTB links); the rest
  teaches. What they disagree on is the operator's, in the viewer's one
  review tab (`/review`; `/trial` is an old address of it).
- **The octopus** (#204, #215; owner, 2026-10-16/17, 2026-10-24;
  `services/octopus.py`, `scripts/octopus.py`, migration 126): **one game
  assembled whole** — every version of the same game, each with its store
  data, achievement list, DLC, editions and HLTB — by a chain with a goal, not
  a crawl. Entry → anchor (an achievement → its list; a DLC → its version; a
  product, a list → itself; an HLTB page → the versions linked to it, else a
  search by its name; a name → one entry per game it finds; a game → its
  anchor version) → the game it is in → each version expanded (its list or
  Steam app collected; the game searched by every different name — its own,
  Russian, versions', editions', HLTB's and alias, normalized, six at most;
  PSN concepts' products) → the linker (`game_link.link_and_spread`) over
  this game's neighbourhood → again while the game gains versions
  (`MAX_ROUNDS` 4). **Only what the linker puts in this game is expanded**: a
  remaster, a remake, a compilation, a series, another game or a doubt for
  review is kept and never followed. Done: every version's anchor stamped
  (`fetch_state`, source `octopus`), so another entry to the same game waits
  until due; stand-ins and HLTB reported. The queue (`octopus_queue`) keeps
  entries by keys a relink cannot change (`list:`, `product:`,
  `achievement:`, `dlc:`, `hltb:`, `name:`, `game:`; stage 2: `storeid:` — a
  PSN title id or an Xbox product id from `versions.store_ids` — and `news:`,
  a Steam post's app). **Three entries spread** into what they hold instead
  of assembling: `edition:` (every version in a bundle), `series:` (its games
  and a search by its name), `account:` (a player's lists). A pasted Steam,
  Xbox, PlayStation Store or HLTB link is read into a key (`entry_key`), so
  the queue keeps keys only. The viewer's **«Осьминог»** (`/octopus`): links,
  keys or names one a line into the queue, a run in the background (one at a
  time), the queue, and the step-12 checks — versions in no game, stand-ins,
  games with no HLTB; a game page has «собрать осьминогом». **In the bot**
  (stage 3, `poller/octopus.py`): a list published for the first time and a
  game page opened in the Mini App queue `list:` beside `StoreCollector.ensure`
  (reason `published` / `page`); a job takes `octopus_entries_per_tick` a
  minute (1; 0 = off; /admin → Таймеры), one run at a time.
- **Games** (migrations 092, 099; the model after the review, owner,
  2026-10-11; decisions in #147). **The operator's decisions are input, a
  game's versions are output**: a decision is a label on a pair of versions
  (`match_decisions`: same / demo_of / tool_of / mode_of / remaster_of /
  remake_of / contains / vr_of / other, with the pair's signs and the model that
  saw them — what the weights will be fitted to). **Every answer is kept**
  (migration 128, `label_log`, append-only; the training audit, 2026-10-24):
  `match_decisions` and `game_series` hold the one that counts, the log each
  event — a label, an undo, a «позже» (`skip`), and an adviser's answer on a
  pair the operator (`viewer`) answered, which never replaces theirs
  (`refused`); series answers likewise. «Отсоединить» labels `other` against
  the version the model likeliest calls the same game, the link that was
  wrong, not the anchor. Which game a version is in
  (columns of `versions` since migration 108 — `game_id`, `role`, `of_version_id`, `link_p`, `linked_at`; the old table `game_versions` was one row per version —, **one game per version**, its role version / enhanced / demo / tool / mode / extra / pass / covered and the version a demo, tool, mode, extra or pass is of; the roles are checked in `game_link.py`, not by a CHECK, which would mean rebuilding `versions`) and how games relate
  (`game_relations`) are rebuilt from the labels and the model by
  `services/game_link.py`, so a decision outlives every rebuild. **A label
  outlives its versions too** (migration 106, 2026-10-12): `match_decisions`
  has no foreign keys, so a store re-parse deleting a version keeps every
  answer about it, with which product each side was (`subject_key`,
  `other_key`: store:product_id:console); the linker reads only labels between
  versions that exist, the fit reads a gone pair from its feature snapshot.
  **Contradictions are shown, never settled by code** (#218 step 5,
  `services/label_conflicts.py`): a label keeping two versions apart that
  joining labels link anyway, or two labels between the same two groups
  saying different things. Each new label is checked (the viewer's message,
  `web_labels`' output); the viewer's «Contradictions» lists them as cards,
  and taking one answer back settles it. A game keeps
  its id through rebuilds by its **anchor** (`games.anchor_version_id`, its
  first plain version); a list's stand-in that becomes a store product keeps
  its row and id.
  - **A remaster, a remake, a compilation, a VR version is a game of its own**,
    related to the original: `remaster_of` / `remake_of` / `vr_of` point at the
    **earliest** original (no chains through remasters), `contains` from a
    compilation to each part. **A remake is an original of its own** (owner,
    2026-10-12): a remaster of a remake points at the remake. Inside a game:
    the same product across platforms (PS4 and PS5, One and Series released
    together under one name are one game, even with two lists), demos (betas
    and tech tests too), tools and modes, and **enhanced editions** (role
    `enhanced`, `of_version_id` the plain version; by its name,
    `game_match.is_enhanced`, or an `enhanced_of` label — one game to a fit).
    A pack a store sells around one version is an edition (`editions`), not a
    version. Such a game is named by its own release.
  - **Enhanced, remaster, remake** (owner, 2026-10-27):
    - an **enhanced edition** is an edition under an id of its own in a
      store, mostly the game with added content, with no focus on better
      graphics (GOTY, Complete, Definitive, Director's Cut);
    - a **remaster** is a release with improved graphics that keeps the
      original's main assets, not rebuilt;
    - a **remake** is a game made on the basis of an old one.

    **Every instruction to a model that labels pairs gives these
    definitions as they stand** — the advisers' prompt (`advice.DEFINITIONS`
    inside `advice.RULES`), the web-searching agents', Gemini's. Which one a
    given game is, is the labels' answer, never a rule written here: this
    file keeps principles, not per-game decisions.
  - **Where an enhanced edition goes** (owner, 2026-10-25): one sold under
    its own product id on a platform (a store page and id of its own, apart
    from the plain game's) is **a game of its own**, related to the original
    as `enhanced_of`, like a remaster; one that is the same product upgraded
    (a free update, the same id) stays inside the game with the role
    `enhanced`. Built as a split after joining (`game_link._split_enhanced`;
    #218): the model joins an enhanced edition to its game (its own class,
    `enhanced_of`, joins like "same"); then, where one store sells both the plain game
    and the enhanced one, every enhanced version of the group leaves it for
    a game of its own, related `enhanced_of` (a family relation for series
    too). Where no store sells both — Steam sells only the Complete Edition
    — it is the game there and stays, role `enhanced`.
  - **A game's name keeps the words that tell it apart** (owner, 2026-10-12;
    `game_match.game_name`): the full release name, platform tails cut ("-
    Xbox Series X|S", "(PC)", "for Windows 10", "Windows 10 Edition"), when
    every version of it carries the same release tail
    (`game_match.release_tail`: Ultimate, Remastered, Definitive, Director's
    Cut, GOTY …; "Standard Edition", "The Game", a demo's or a beta's words
    are no tail), when it is a compilation, and when it is a remaster, remake,
    VR version or compilation of another game. Only a game whose versions
    differ in their tails (Control and CONTROL Ultimate Edition) gets their
    common core. Named once a rebuild knows its relations.
  - **A game's kind** (`games.kind`, migration 102; owner, 2026-10-12):
    `game`, `compilation` (holds more than one game: its name — Collection,
    Trilogy, Anthology, "X + Y" —, its HLTB entry filed `compil`, or two
    `contains` relations or more) or `extra`, **not a game** — a soundtrack,
    an artbook, an app: the store's type first (Xbox `Application`, Steam
    `music` / `video`), else its name (`game_match.is_extra`). **A soundtrack
    or an artbook is a part of its game** (owner, 2026-10-14; migration 107):
    role `extra`, label `extra_of`, joined to the game its name names before
    its extra words, whole ("DOOM: The Dark Ages Digital Artbook and
    Soundtrack" is DOOM: The Dark Ages', never DOOM's; `extra_game_name`).
    An Insider build is a beta (`demo`). An extra of no game (an app) stays an
    entry of its own, related to nothing (`extra_pair`, `extra_both`). A
    compilation is never one game with a single game (`compilation_word`).
    The linker sets the kind on every rebuild; the operator's choice on the
    game's viewer page (`kind_source = 'manual'`) stands. The viewer marks
    them «📦 compilation», «🎵 not a game», and a compilation's page lists
    its parts, warning below two.
  - **The model** (`services/game_match.py`, no DB access): every pair that
    could be one game (a telling word of the name — none in more than
    `COMMON_WORD` versions —, a store's group or cross-gen set, an HLTB entry,
    one list) is read from its subject's side (the VR one, the compilation, the
    later one) — and each directed class from whichever side makes it likelier,
    the relation pointing from there (#218: `subject_of` is a guess); its
    classes are one game, an **enhanced edition** (one game too, a class of
    its own — owner, 2026-10-27), a remaster, a remake, a compilation, a VR
    version, or "other"; each class sums its `WEIGHTS` over the pair's signs and a
    softmax against "other" gives probabilities (owner, 2026-10-10: every rule a
    weight, nothing certain). The likeliest at `LINK_P` (0.95 while the fit runs
    overconfident, #218) and `CLOSE_CALL`
    ahead is taken; from `REVIEW_P` (0.15) the pair goes to the **review list**
    (`match_pairs`, one per pair of games). Versions join a game from the surest
    pair down, **never across a veto** (a pair under `VETO_P` "same" that
    also shows a sign the two differ — `DIFFER_SIGNS`: a number, subtitles,
    the same name far apart, achievement lists apart, … — or whose likeliest
    answer is a relation: a remaster is another game; or a label saying no; a shared name alone vetoes nothing; a demo, a tool or a mode vetoes nothing — a beta is far from its game's port
    years later): A~B and B~C no longer drag A and C together. The operator's
    labels come first. One linker at a time; a component is written in one
    transaction. The viewer's «rules» page shows every weight.
  - **The model's relation is a first guess, rechecked** (owner,
    2026-10-27): whatever the linker sets by itself that is neither one game
    nor nothing — a relation between games, or a role in a game (enhanced,
    demo, tool, mode, extra, pass) — is written so the catalog has one, and
    stays on the viewer's «To recheck» (`review_questions.to_recheck`) until
    a label settles it; `review_questions --recheck` asks them all of the
    web-searching advisers (a VR version: this game in VR, or another game of
    its series made for VR). The model only has to tell one game, related
    and other apart well; which relation it is is the advisers'.
  - **A name never learned is no name** (the training audit, 2026-10-24): a
    stand-in named by its own id («1881441063») has no names for the model;
    its pairs show `name_unknown` instead of any name sign, and veto nothing
    (its year is often wrong). `year_unknown` starts from the labels' fit.
  - **The stores' texts are signs too** (owner, 2026-10-13): a version's
    genres and short description (`versions.genres`, `description_en`) and its
    HLTB summary give `TEXT_SIGNS` — the subject's text says remastered,
    remake, a collection, VR, a demo; either says sequel; it names the other
    game; the two say much the same or little; no genre in common. Every class
    starts at 0 on them, so they change nothing until a fit weighs them.
  - **Rules the owner gave in conversation** (2026-10-14), in the model and in
    the advisers' prompt (`advice.RULES`): the word **"Remake"** in a name marks
    a remake (`_REMAKE`), "Intergrade", "Director's Cut" or "Special Edition"
    alone do not (Final Fantasy VII Remake and its Intergrade are two games,
    both remakes of Final Fantasy VII, by the operator's label); a
    **next-generation release** is a remaster when it is a separate product
    (its own page and achievement list) sold beside the previous release, the
    same game when one product runs on both generations or it replaced the
    previous release by an update (`one_list`, `cross_gen_set`,
    `later_list_same_family`); **a demo, a beta, a tool or an extra gets no
    automatic HowLongToBeat entry** (`game_match.is_part`: the store's kind, the
    linker's role or the name — `ensure_title_match`, `record_hltb_match`, the
    evidence check and `_hltb` all skip it), unless the entry is the demo's own
    (its name says demo or beta: Resident Evil 2's "1-Shot Demo"); the operator
    may link one by hand.

  - **Fitting the weights** (`services/match_fit.py`, `scripts/fit_match_weights.py`):
    every label's pair is read as the model reads it now (the label's own
    version as the subject; scored from both sides as the linker reads it),
    and the weights are fitted by gradient descent **pulled towards the
    current ones** (a proximal step, `strength` 0.0001, step 0.5, until no
    weight moves by `tol`); then **one temperature** fitted on the held-out
    answers scales every weight, so a probability means what it says (#218); **the bias is never fitted** (labels come from the
    review list), and a class with fewer than `FEW_LABELS` labels is pulled
    harder. A label weighs by who gave it (`label_weight`). **A fit is judged
    held out by game** (labels joined by a game sit in one fold — a random
    split flattered it by ~4 points) **and on the operator's labels alone**
    (`gate`; the advisers' scores are printed beside, never decide) — or,
    once frozen, **on a fixed set of pairs** (`--freeze-eval`,
    `data/advice/eval_set.json`; #218: the operator's set grew harder with
    every batch, so fits could not be compared), their labels as they stand.
    It prints each class's recall, their average and the viewer's labels
    alone, and judges by **one game / related / other** (`match_fit.coarse`,
    owner, 2026-10-27: every relation is rechecked): a fit must lower that
    log-loss, answer no fewer right, and **lose none of the three** (recall
    down more than 2 points on 10+ labels). The
    script also scores every pair the linker compares with both weights and
    counts what would move. **A fit lives in the database** (`match_weights`,
    migration 129): `--save` keeps it and makes it the active set only when
    the gate passed, `--activate N|hand` switches, `--list` lists; the linker
    (and everything that scores pairs) reads the active set before it scores
    (`game_link.load_weights`), the hand `WEIGHTS` being the prior a fit is
    pulled towards and the fallback with none active. A pair keeps which set
    scored it (`model_name()`, `multiclass-1/w<id>`). Relink a copy and look
    at what moved before activating a set on the working database.
  - **Doubtful pairs go to two advisers first** (owner, 2026-10-12;
    `services/advice.py`, `scripts/advise_pairs.py`). Where the model is
    sure it decides alone; the pairs it is not sure of — the review list
    (game ↔ game, version ↔ game), an HLTB match in the grey zone (score
    under `ACCEPT_SCORE` + half `CLEAR_MARGIN`, 0.92), an HLTB DLC left
    unlinked as ambiguous — and a seeded 5% audit of the sure ones (a hash
    of the pair, so a pair picked stays picked; two versions of one list
    are left out) are asked of Claude and Gemini, each on its own, without
    the model's guess. All three agree: a label `model+claude+gemini` (still
    a training example); Claude and Gemini agree against the model:
    `claude+gemini`; they disagree, or either is unsure or of low
    confidence: nothing is written, the pair is the operator's (`conflicts`
    → the viewer's review tab). "Another of the series", "not related"
    and "not a game" agree (Claude's word kept); a directed relation agrees
    only in one direction. **An operator's label is never overwritten**
    (anything not an adviser's `decided_by`). Labels are written as the
    viewer writes them (`save_decision`, then the linker); an HLTB match
    agreed on becomes a `manual` link. Questions and answers are JSON in
    `advice/` in `DB_PATH`'s folder (`pair_state(pair_id, dir)` for the
    viewer), never in the database. An HLTB entry refused is kept as a
    `rejected` link (never made again), a DLC's HLTB entry written by hand is a
    `manual` link in `dlc_hltb` (or `rejected`), so every answer can be written.
  - **Series** (owner, 2026-10-12; migration 105, `services/game_series.py`,
    `db/repo/_series.py`): a series is an entity of its own (`series`), and a
    game may be in several (`game_series`) — a crossover (Street Fighter X
    Tekken) is in both and **never merges the two**. A membership's `source`
    is `auto` (the linker's proposal, with `p` and the `reason` it got there),
    `advisers` or `manual`; the last two are never overwritten, and `member =
    0` keeps a game out for good. Evidence: a remaster, remake or VR version
    is in its original's series and a compilation in its parts' (0.95 / 0.9);
    the labels "another game of the series" (the operator's 0.97, the
    advisers' 0.9); a shared **franchise** — the name before ":", " - ", a
    number or a platform (`franchise_key`: "Halo 3", "Halo: Reach" → halo) —
    only by the same studio or publisher, a weak 0.5. Grouping: a game and its
    remasters are one unit; units join along evidence whose franchises agree
    (one the other's word prefix); otherwise a game already of a series whose
    name holds the other's franchise is a crossover — one more member of the
    other; a lone game joins the one series its evidence leads to (Crisis Core
    into Final Fantasy); a compilation reaching several series is a member of
    each; other strong evidence joins a lone game, but **between two series
    of their own it makes each game a crossover of the other's, never one
    series of both** (owner, 2026-10-24: chained labels had put LEGO Batman,
    Marvel and Harry Potter in Star Wars); weak does nothing. **A label
    naming no series is weaker than its 0.97** (the training audit,
    2026-10-24: ten labels on LEGO Harry Potter Collection, meaning LEGO, had
    built a "Harry Potter" of LEGO games): between names with no first word
    in common it joins only a lone game with one way in, and its other end
    only as a series already, by a name one holds of the other, or with no
    other label out; two LEGO games of different licences labelled one
    series are LEGO's, never a sign for either licence. A name is the
    franchise more than half its games share ("Gears of War"), else the
    prefix common to all ("Sonic"), lengthened to the words all go on with
    ("Cities: Skylines"), as most of them write it. Proposed again after
    every linking (`SeriesBuilder`, whole: cheap); a series keeps its id by
    its anchor game, an operator's merge stands (`merged_into`, `merged_by =
    'operator'`); a merge the builder made (`merged_by = 'auto'`, migration
    125) leads nowhere on the next rebuild, so an old chain comes apart.
    **Series a rule names** (owner, 2026-10-14; migration 111, `series.rule_key`,
    no anchor game, `game_series.umbrellas`): every LEGO game is in the series
    **LEGO** (0.95) *and* in its licence's series — `franchise_key` reads
    "LEGO Star Wars" as Star Wars, and `_licence_evidence` (0.9) joins it to the
    games of that franchise whoever made them, the same name or a longer one of
    two words or more ("Worlds" is not "Worlds Adrift") —; a franchise has **local series** inside
    it, a longer name two of its games share ("Star Wars Jedi" in Star Wars,
    key `key:…`) or a subtitle two games of one studio or publisher share
    ("Modern Warfare" in Call of Duty, key `sub:franchise|subtitle`; edition
    words, one name twice and the whole franchise make none); a franchise of
    two words or more has the series named by a longer form of it as members
    (Star Wars Jedi, by Respawn, is of Star Wars). A game is so in several
    series, and such a series is found by its key, never merged.
    `game_series.series_questions` lists the unsure memberships (under
    `SURE_P`, nobody answered) for the advisers, `answer_series_question`
    keeps their answer; the viewer has `/series`, a series' page (games by
    year, how each got there; rename, merge, add, "not in this series") and
    a game's series.
- **A fixed parser is applied to what is kept, not by asking again**:
  `scripts/reparse_store_payloads.py` (`StoreCollector.reparse_stored`, no
  request) reads every kept answer through today's parsers, writes it as a
  collection would (and keeps the answer again without prices), checks the
  HLTB links, then rebuilds every game. Dry run on a copy by default, printing
  what would change; `--apply` backs the database up into `backups/` first,
  with the bot stopped. What only a request brings (a Steam DLC's or
  package's own answer, the Russian appdetails) stays as it was.
- **The catalog is one schema, never carried** (#229, #234): prod and the test
  server read the same `games`. What travels between copies is labels and
  weights, below.
- **Labels and weights are files in git** (owner, 2026-10-27; `catalog/labels.jsonl`,
  `catalog/weights.json`, `scripts/catalog_files.py`): one training serves
  production, the test server and the dev server. A label names its versions by
  key (`store:product id:console`), never by id — each copy numbers its own; the
  weights are the active fitted set. Trained in one place (a fresh anonymized
  copy of production); after a labelling session or a fit that passed
  (`fit_match_weights --save` writes them), `export` and commit; another copy
  `import`s them — a label set as the file has it, a key it has not collected
  counted and left, the weights made active — and its catalog is linked there.
- By hand: `scripts/collect_game.py <platform> <title_id> [--force]`; to look and
  decide: `scripts/catalog_viewer.py` (bare HTML; games and their family, the
  labels; merge / relate / detach / "not related" are labels too; rename,
  collect, re-link). **An action whose other side is typed as an id asks
  first** (owner, 2026-10-24; `_confirm`): merging or relating games, merging
  series, adding a game to a series by id show what each id is — name,
  years, versions — then «да, выполнить» / «отмена».
  **Every name opens our own page** (owner, 2026-10-12) —
  a game, a version, a DLC (`/dlc/<id>`: its version and game, its store,
  whether it is sold, its HLTB entry and times), an HLTB entry, an
  achievement list; a store page is always a separate small "↗" beside it,
  with «в продаже» / «снято с продажи» / «неизвестно», and never a search.
  **One tab of manual review** (owner, 2026-10-23; `/review`): the advisers'
  disputes (`scripts/trial_page.py::cards`) first, then the model's doubtful
  pairs, filtered — never more tabs (Proposals, Advised, Trial left the
  menu; answers already given are «История ответов», `/decisions`). An
  adviser card is **one tap**: a button per answer the advisers gave, saying
  who gave it; every other answer and a field for one typed under «Свой
  ответ…»; «Позже». **«Одна серия» names the series** (owner, 2026-10-24):
  a button per series both games are in, or a field for its name with ours
  suggested; kept beside the label as `<qid>|relation.series` (an id, or a
  name typed for a new series). Own answers follow the template; free text
  only where a name is asked. «Недостающие версии» (M) are not the operator's — the
  octopus (#204) searches the stores; they show only with `kind=M`.
  **The model's doubts have two questions** (owner,
  2026-10-11): version ↔ game (one game, an edition, a demo, a tool — or
  another game) and game ↔ game (a remaster, a remake, a compilation, a VR
  version — or not related), the latter answered game against game, as a
  label between their anchors; "not related" clears every relation the model
  found between the two, and a pair of games once answered is not asked
  again. **Answers are a tap** (owner, 2026-10-11): two games — "✓" the
  model's guess, "another of the series" (label `series`: relates nothing,
  like `other`, but tells the fit the model mixed up a series), "other: ask
  later" (nothing written, the pair comes back after the rest); "another of the
  series" **names the series** (owner, 2026-10-24): a button per series both
  games are in, or a field for its name (ours suggested) — both games are put
  in it by hand beside the label (several typed by commas — no series name
  has one); two versions —
  same game, a different game, a remaster of it, a remake of it (one tap moves
  the version out and relates the games). The rest is under "more…". **No authentication
  yet** (#186).

### The platforms' answers, kept whole

**Every answer about achievements is kept as it came** (owner, 2026-10-15;
`services/raw_answers.py`): Xbox's achievements service (every contract and
page, `xbox_achievements`), Steam's player achievements, schema and global
percentages (`steam_achievements`), PSN's trophies and groups as psnawp read
them (`psn_trophies`, `psn/client.as_json`) — in `source_payloads`, compressed,
the latest per subject, not rewritten while unchanged. What a poll parses is a
part of what came; the rest (types, time windows, rewards, progress targets,
grey icons, Xbox's `groupIds`) can be read again with no request. The clients
hand an answer to `raw_answers.keep`; the bot's assembly points it at
`repo.save_payload`; with no sink (tests, scripts) nothing is kept.

### Secrets

`tokens` stores encrypted Xbox refresh tokens only (access/XSTS tokens stay in
memory); status is active / invalid / revoked. Shared credentials (PSN NPSSO, Steam
key, Anthropic key, YouTube key) are encrypted in `app_settings`. **A player's own
PSN token** (owner, 2026-10-29; #233; migration 142, `psn_tokens`,
`services/psn/personal.py`) is kept by PSN account, encrypted, active or dead,
and counts only while its person holds the account (`_psn_tokens._HELD`): an
unlink deletes it, a takeover leaves it unread and the daily check forgets it,
a merge moves it with the person. **A token pasted where a nickname is asked**
(the bot's prompt, `/connect_psn`, the Mini App's field) is recognised by its
form (`personal.looks_like_token`), deleted from the chat and linked as a
token — never logged, sent to Sony's search or quoted back. A person has
Sony check at most five tokens in ten minutes (`too_soon`).

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
- **Contracts.** Modern Xbox: contract 6 — contract 4 (the only one with
  rarity) and each achievement's `groupIds` (2026-10-15). Only
  `progressState == "Achieved"` enters `seen_achievements` — an `InProgress` row
  would hide the achievement forever once it is earned. Xbox 360 takes two
  (#121): contract 1 (`/achievements`) lists what the caller earned, with no
  rarity and only a bare `imageId`, so its card uses the box art; contract 3
  (`/titleachievements`) lists the whole game with its rarity and total. The
  earned ones come from 1, their rarity and the game's list from 3.
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
- **Xbox 360 history comes from the achievements service's own lists** (#91, #92):
  contract 1 `/achievements` with no titleId gives every 360 unlock page by page, and
  `/history/titles` every 360 game with its name and total. Titlehub forgets games not
  played for a while; these do not. Backfill uses them (game by game through titlehub
  only if refused), and linked accounts are topped up once at startup
  (`Fetcher.fill_x360_gaps_once`, marked in `app_settings`). A forgotten game's total
  on `achievement_list_connectors.achievements_total` is what lets a finished one count as 🌀.
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
- **Hidden achievements are not a dead key** (2026-10-12): Steam answers a
  profile whose game details are hidden with 403 and a JSON
  `playerstats.error`, a bad key with 403 and an HTML page;
  `client._get` raises `SteamGameDetailsPrivateError` for the first. A
  backfill that meets it on every game tells the person (as for a hidden
  library) and leaves `achievements_visible = 0` — "the history waits".
  The first achievement read again (any poll), or a library that answers
  the catch-up while the flag is 0, starts `fill_library_gaps` in the
  background: every game with nothing stored, as history, never published;
  still hidden, it stops at its first game.
- **Achievement icons moved off Akamai** (2026-10-17): the schema still hands
  out `steamcdn-a.akamaihd.net/steamcommunity/public/images/apps/…`, which has
  no icon for a game released lately (a post went out as text only);
  `shared.fastly.steamstatic.com/community_assets/images/apps/…` serves old
  and new alike. `images.current_url` mends the address where it is used —
  the schema (fresh and cached), the post, every bot download, the Mini App's
  icon links — and stored rows keep what the platform said.
- Presence comes in batches of up to 100 SteamIDs (`GetPlayerSummaries`).
- **Every stored achievement carries its game's name** (#70): `fetch_unlocked`
  takes `title_name` so the `achievement_list_connectors` upsert has something to write — without it a
  game that arrived by backfill or catch-up stayed "без названия" forever.
- **Schema and rarity.** The schema is cached per app with no expiry but
  **re-fetched when an unlocked achievement is missing from it** (#49) — games add
  achievements after release, and a stale schema publishes a DLC achievement with
  no icon and no spoiler. One retry per game per process. Global rarity is cached
  with an expiry (it drifts).
- **Backfill** scans owned games with playtime, one call per game, under a two-level
  concurrency limit (people at once, games per person at once). `GetOwnedGames`
  asks for `include_played_free_games` (#120): without it every free-to-play game
  was left out. Accounts linked before that are topped up once at startup
  (`SteamFetcher.fill_library_gaps_once`, marked in `app_settings`), as history.
- **Games Valve folded into another are listed beside their host** (#123,
  `steam/client.py::FOLDED_APPS`): Half-Life 2's episodes became part of Half-Life 2
  in 2024, their achievements stayed on apps 380/420, and no API lists those apps
  any more. A table, because nothing else can know.
- **Descriptions**: `GetPlayerAchievements` is fetched with `l=english` beside
  `l=russian` only when some achievement in the batch is not cached yet.
- **A secret achievement's description comes from the profile page** (#132): no
  Web API call gives it, even once earned. `steam/client.py::community_descriptions`
  reads `/profiles/<id>/stats/<appid>/achievements/` (the `?xml=1` form is gone),
  matched to ids by icon file name, the language set by the `Steam_Language`
  cookie (`?l=` is lost in the redirect to a vanity URL). Asked at poll time for an
  earned one with no text, and by `poller/description_backfill.py` for history, a
  game a tick. Best effort: a private page leaves it empty, as before.
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
- **Two levels** (owner, 2026-10-29; #233): the shared admin NPSSO reads every
  account without a token and everything about games (the catalog, the store,
  trophy groups' names, the Russian client); **a player's own NPSSO**, opt-in, reads
  its own account (`PsnAuth.client_for`: presence, the trophy scan, groups, the
  avatar, a resync). An account without one is polled `shared_slowdown` times
  less often (×3, the PSN group of «Опрос статуса») — the shared token is the
  bottleneck; what is new and costly (play time, hero stats) is read only with an
  own token. A refused own token is marked dead (`PsnAuth.refused`), its account
  falls back to the shared one, its owner is told once (`psn_token_dead`, on until
  switched off), and the shared token's health is never touched; every live own
  token is checked once a day (05:10). psnawp's own logger is pinned to WARNING:
  at DEBUG it logs request headers, bearer token included.
- **Verify an NPSSO with a real call (`check_alive()`) before saving it** — psnawp's
  token exchange is lazy.
- **Pacing is psnawp's own limiter, one request every 2 s per client**
  (`client.py::REQUEST_RATE`, owner, 2026-10-01; the library's default is 3 s).
  Its bucket file is per process and per instance, so prod, the test server and
  the dev bot never share one; a game's backfill costs ~5 requests.
- **Shared-credential health** (all three credentials, `services/credential_health.py`,
  #62): the admin is notified once per alive → dead transition, and once on recovery.
  A death needs `FAILURES_BEFORE_DEAD` consecutive failures, re-checked on the next
  tick — an unconfirmed failure leaves `checked_at` alone — because these services
  fail one request at a time for their own reasons. A dead PSN token stops polling
  *everyone* linked to PSN.
- **Presence and trophies** (#90): presence is one `get_presence()` per account, on
  the shared politeness cadence. Going Online → Offline fires an exit poll
  (`psn_fetcher.poll_account`), since trophies often sync when a session ends. Trophy
  titles are scanned every 2 min while online, 30 min while offline and active, 24h
  when dormant (the PSN group of «Опрос статуса», `services/poll_cadence.py`);
  a title whose progress grew is fetched in full.
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
- **Trophies stored before #46 get their group back** (#115,
  `poller/psn_trophy_groups.py` → `regroup_title`): a game with some grouped rows is
  never widened, so its older rows stayed ungrouped and the card's group counter
  undercounted. One request per (account, game); earned trophies never stored go in
  as backfill — history, not news. Only accounts somebody holds. The same walker
  takes a game with progress and no trophies stored (#120): the scan records
  progress even when the fetch failed, and then never asks again.
- **A game known only from the database is a `TitleRef`** (`title_ref(id,
  platforms)`), never a hand-built psnawp `TrophyTitle` (a TypeError). Its platform
  picks Sony's trophy service, so it is the game's newest console, not a default.
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

- **Presence cadence** is state-based — fastest in a game, then online, then
  offline, slower for someone offline a while (`idle_after`), slowest for a
  dormant account — **global admin settings, per platform** (owner,
  2026-10-29; #184 stage 0; `services/poll_cadence.py`): /admin → Настройки →
  «Опрос статуса: Xbox / Steam / PlayStation», in both panels from the registry,
  whole minutes (the tick is a minute), PSN's trophy-scan steps beside them. The
  pollers read them on every tick, so a change needs no restart; the
  environment's `presence_interval_*`, `achievement_poll_interval`,
  `psn_*_poll_interval` only seed them once (`seed_once` at start-up). A dormant
  account's presence is asked once an hour, its PSN trophies once a day. Steam is asked in one batch for everybody due, so
  its steps are a minute everywhere. How long an account has been offline is its
  own presence row's (`changed_at`).
- **Accounts idle more than `dormant_after` days (7; owner, 2026-10-29) are dormant**
  (`poller/cadence.py::is_dormant`, the platform's setting, from `last_online_at` or
  `linked_at`): their catch-up drops to once a day and PSN scans to the dormant
  step. Coming online (`touch_last_online`) wakes them at once; a fresh link counts
  as active.
- **Achievement polling and exit polls**: while in a game, poll that game on the
  achievement debounce. On leaving it or going offline, one exit poll catches the
  last unlocks — immediately on Xbox, after 180s on Steam, on Online → Offline for
  PSN (see each platform).
- **Isolate failures**: a poller never fails a whole tick because one user, account,
  title or batch failed — log and continue. Private profiles, empty responses, 429s,
  timeouts, dead credentials and outages are expected states, not exceptions.
- **Backfill** is mandatory on first connection and safe on reconnection: history goes
  in with `is_backfill = 1`, idempotently (`ON CONFLICT DO NOTHING`), and never publishes.
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

An achievement is published to a chat only if every check passes: the chat's
publishing switch is on (#232); the person is subscribed there; not admin-excluded; the account's posting switch is on (#20); the
person's `rarity_mode` isn't `hidden`; in
`rare` mode a
known rarity is at or below the rarity threshold (Xbox 360 included since #121;
an achievement whose rarity is unknown is held back); the game
isn't muted there; it wasn't already published there.

- **`hidden` is about notifications only** (owner, 2026-10-06; #167): a person who
  publishes nothing still counts in a chat's summaries, rankings, `/recent`, its
  subscriber list and the Mini App. Leaving a chat's statistics is unsubscribing;
  who sees one's activity in the Mini App is `users.activity_visible`.

- **The rarity threshold is one for every chat** (owner, 2026-10-01):
  `app_settings['rare_threshold_percent']`, 10% until an admin changes it in
  /admin → «⚙️ Настройки» → Правила; no chat overrides it. The repo reads it wherever a
  chat's settings are read (`_sql.py::GLOBAL_RARE_THRESHOLD`), so callers still
  take `chat.rare_threshold_percent`. Never hardcode a percentage; a person picks
  only a mode.
- **Digests**: at `digest_threshold` items — one size for every chat (owner,
  2026-10-08; `app_settings['digest_threshold']`, 3 until changed, 99 = never;
  read as `chat.digest_threshold` through `_sql.GLOBAL_DIGEST_THRESHOLD`) — a batch
  becomes one grouped message, grouped by platform and title. Every item is listed, never "и ещё N". The
  gallery dedupes by image URL.
- **Nothing may fail for being too long** (#68): `services/message_limits.py` is a
  request middleware that cuts any outgoing text to Telegram's limit (4096 message,
  1024 caption, 200 callback answer), keyed on which fields a method *has* so new
  sends are covered. It cuts only outside a tag or `&entity;`, prefers a word
  boundary, closes what is open, and logs a warning — a net, not a substitute for
  keeping screens short. Capping lists by rows does not replace it: the limit is in
  characters.
- **A post always goes out, with a picture whenever one exists** (owner,
  2026-10-07; `Publisher._deliver`): the achievement's icon by URL (Telegram
  fetches it), the same bytes fetched by the bot (Telegram cannot always reach a
  platform's CDN), the icon cached on disk, then the game's cover (its file, its
  URL; never behind a spoiler); text alone only when there is none.
  A digest of several pictures sent as one photo — an album cannot carry
  the Mini App button — shows the game's cover first, its first icon only
  when there is no cover (owner, 2026-10-18).
- **A low-resolution post picture is enlarged on a square** (owner,
  2026-10-10; `services/post_picture.py`). **Nothing drawn is stored**
  (the icon cache keeps the icon, at most 1280 px; cover; URLs); the square is drawn when a post is
  sent, single or album, and kept nowhere. **A high-resolution picture goes
  as it is** — unless more than a tenth of it is see-through (2026-10-12:
  Aniimo's white PSN trophies on nothing reached the chat as an empty
  square, Telegram flattening the transparency): that one is set on the
  card at its own size, never enlarged. A low-resolution one (smaller on its longer side than
  `post_picture_low_res`: 128, 200 — the default —, 256 or 512 px; Steam's
  and Xbox 360's icons are 64 px, PS4's trophies 240) is enlarged by a cheap
  filter (bicubic) and set in the middle of a card, rounded, with a shadow.
  Four global admin settings (/admin → Правила): that limit; the ground, `post_picture_style`
  — `color` (the icon's average colour; the default), `cover` (the game's
  cover, blurred and darkened; the colour without one) or `off` (as
  before); the card, `post_picture_size` — `1024x1024` (default),
  `720x1280`, or `original` (no card: the enlarged icon alone); the scale,
  `post_picture_scale` — ×1 to ×8 (×4 default), never past 90% of the
  card. Anything that cannot be drawn goes as before. «🖼 Тест
  уведомлений», one global action beside these settings (/admin → ⚙️
  Настройки → Правила; the Mini App's admin settings), sends the newest
  achievement earned on each platform, whoever earned it
  (`repo.latest_per_platform`), as the whole post a chat gets
  (`Publisher.sample`: text, progress, Mini App button) — as today, then
  on each ground — to the super-admin's own DM, recording nothing.
  **The Mini App draws a small achievement picture by the same rule**
  (owner, 2026-10-12; `/me`'s `picture`: `on`, `scale`, `low_res` from these
  settings): under the limit it is not stretched over the block — it is
  enlarged `scale` times (the 1024 px card is the reference, so a 64 px icon is
  a quarter of the block's shorter side, never past 90%) and set in the middle
  on a ground of its own. A larger one fills the block. Every achievement
  picture does it; a game's cover never.
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
  its header names the person, as every post does). Forced sweeps right after
  startup and five minutes before each chat's daily summary keep a window from
  swallowing anything.

## User interface

User-facing text is Russian by default and English where a chat or person picked it
(Localization). History: #109.

### People, nicknames and follows (#157)

Agreed with the owner on 2026-10-02, built in stages on top of #156's person id.
**Shipped: nicknames, the follows backend, the People tab, and the Publishing and Privacy screens.** The rest is planned; until a stage ships, the rules
elsewhere in this file still describe the bot.

- **A person is named by a nickname only** (shipped) — never by their Telegram first
  and last name, anywhere (the Mini App, group messages, DMs; the admin's user card
  shows the nickname too). A nickname is 3–20 Latin letters and digits, unique
  ignoring case; a taken one gets four random digits, `RideTheSun#4821`, always
  shown after it. Nobody picks or edits the digits; a change to a free nickname
  drops them, to a taken one gives new digits. The first choice is free, then one
  change a day (owner, 2026-10-03) (only the letters' case may change at any time). The rules are
  `services/handles.py`, the storage `db/repo/_handles.py` (`users.handle`,
  `handle_norm`, `handle_number` — 0 means no digits —, `handle_confirmed_at`,
  `handle_changed_at`; migration 072).
  - **Where a first nickname comes from** (`give_handle`): the Telegram username,
    then the Xbox, PSN, Steam nickname, then the part of an email before the @,
    else `Player` (and its digits) — the first that keeps three Latin letters or
    digits. Given at `ensure_user` from a username; on linking a platform account
    (owner, 2026-10-07: somebody who skipped everything in Telegram is named by
    their account at once); at an email sign-up; and, for anybody still without
    one, at start-up and on their first Mini App visit. Until then the person is
    `id<person id>`. The Mini App shows
    "Твой ник" once (`handle.confirmed` false) to keep or change it; later it is
    Settings → Никнейм.
  - **An avatar of one's own** (owner, 2026-10-03; migration 077,
    `users.custom_avatar_path`): Settings → «Как тебя видят другие» (nickname and
    picture on one screen). The Mini App crops the picture to a 512 px square JPEG;
    `PUT /api/mini/me/avatar` takes the bytes (JPEG/PNG/WebP, 2 MB at most) and
    **decodes and saves them again** as a JPEG of at most 512 px with no EXIF
    (`services/custom_avatars.py`, Pillow): the server does not trust the client's
    crop. `DELETE` goes back to the Telegram photo; a super-admin takes a picture
    down from the user card in `/admin` («🖼 Сбросить аватар», `a:avclr:`), and
    deleting the account removes the file. `/api/mini/avatar/p/{person_id}` (and, for
    links already out, `/api/mini/avatar/{tg_id}`) serves the
    chosen picture first, with an ETag and `no-cache` so a change shows at once;
    then the Telegram photo kept on disk (`users.photo_path`), then Telegram by
    `file_id`, and last the game accounts' pictures (`accounts.avatar_path`,
    Xbox, PlayStation, Steam) — owner, 2026-10-27: a `file_id` opens only for
    the bot that saw it, so the test server on a copy of production showed no
    faces (`repo.face_paths`).
  - Endpoints: `PUT /api/mini/me/handle` (`error` is `invalid` or `too_soon`),
    `POST /api/mini/me/handle/confirm`; `/me` carries a `handle` object.
- **Follows, as on Xbox** (backend shipped, migration 073): following is one-way and
  needs no consent; following each other makes two people friends — friends are
  not stored, they are two rows in `follows`. A person can unfollow and block someone; a follower is never removed by the
  one followed (owner, 2026-10-02) — blocking is the way to end it (a block deletes the follows between the two and hides each from
  the other's search and lists; the blocked one cannot follow). Search is by
  nickname only: a prefix of 3+ characters, or an exact `Name#1234`, 20 results.
  People from a shared chat (subscribed or seen writing) are suggested, and friends of friends above them — «Возможно, ты знаешь», people followed by those you follow, the most shared first (`repo.people_you_may_know`, `/api/mini/people/may-know`). A new
  follower is told through the app's own notifications (below); push and Telegram
  carry it only when switched on there (075's `notify_followers` is no longer read).
  New posts are told as well, by the follower's own choice (below). **Following is not a way to ping somebody**
  (owner, 2026-10-03; `follow_log`, migration 076): one such DM per pair a day, and
  following a person again within ten minutes of unfollowing them is refused
  (`FollowTooSoon` → 429 `too_soon`). These tables and routes speak in **person
  ids** (`users.id`); a row's `tg_id` goes only to a viewer who may see that
  person's activity — a Telegram id is not public. Nickname and face are, so
  the face is asked for by person id.
  Code: `db/repo/_follows.py`, `services/people.py`, `web/mini_people.py`.
- **Privacy is one setting** (`users.activity_visible`): who sees my activity in the
  app — everyone (default), friends, nobody. The one rule is
  `services/people.can_view` (a block either way first, then the setting; oneself
  always), and `repo.can_view_activity` adds that **"everyone" means everyone who
  knows you**: the viewer shares an active chat with the person or follows them
  (owner, 2026-10-03) — not anybody who found the nickname. Nickname and avatar
  are not activity and stay visible. Routes:
  `GET/PUT /api/mini/me/privacy`. Enforced on a person's page (`/club/people` answers `hidden: true` with
  the name only) and in the «Подписки» scope. **Not** on a chat's own feed, ranking or
  `/online`: those show what the chat was already told. Every new screen that shows
  another person's activity must call `repo.can_view_activity`. Publishing to
  chats is unrelated and works as before.
- **Publishing** (shipped): Settings → «Посты в чатах» has the rarity mode, a
  switch per chat and a switch per game account (#20). Settings → Профиль →
  Приватность has the one privacy setting and the list of blocked people.
- **The Mini App's interface is designed again from nothing** (owner,
  2026-10-26; branch `feature/organic-ui`): `docs/mini-app-spec.md` says what it
  does — every screen's job, the flows, the rules, the endpoints — and nothing of
  how it looks; `docs/mini-app-design-brief.md` is the task for the new design.
  The previous interface is in git (`f49fa3b`), for behaviour only. **The new
  one is design E, "Expressive"** (owner, 2026-10-26, chosen from mockups):
  Material 3 Expressive's language in the app's own violet — a tonal scheme from
  the logo's lilac (a pink accent on the search button), shapes that morph
  (faces cut as scalloped "cookies", a flower for rarity), progress as a running
  wave, connected button groups, Roboto Flex whose width is a voice (narrow
  numbers, wide headlines); dark first, the same scheme light. **Seven
  palettes** — Violet (the default, always open), then Graphite, Ocean, Mint,
  Amber, Rose, Halloween (owner, 2026-10-28), each opened by the season pass — and a mode (auto, light,
  dark), picked in Settings → Appearance and kept on the device. How to make
  anything new look like the rest is `docs/design-system.md` (its rarity tiers —
  mythic green, legendary orange, rare purple — are the app's Fortnite note).
  **The app counts its own points, not G** (owner, 2026-10-27): an
  achievement is worth 10, 20 (≤10 %), 30 (≤1 %) or 100 (an Xbox Mythic, a
  PSN platinum — owner, 2026-10-29: far harder to get) on every platform
  (`_sql.points`, `views.POINTS`); the
  Ranking, Home's month card and the race count them. The bot's chat
  messages keep G. A game's page
  takes a muted tonal scheme from its own art (`app/artTheme.ts`; stores whose
  pictures refuse CORS — PSN — keep the violet), and the pages inside the game
  (its achievements, one achievement, its gallery, a post) take the same. **Its one source** is
  `webapp/src/styles/tokens.css` (colour, radii, spacing, motion; the theme set
  on `<html data-theme>` from Telegram's scheme inside it, the system's
  elsewhere) and the components of `src/ui/` (Face, AchPic/Cover with the
  small-picture rule, Wave, Button, Segmented, Group/Row, Toggle, Field, Page,
  Sheet, Confirm, BottomBar, Viewer, RichText, Toast); a screen never styles a
  control of its own. `src/parts/` holds what several screens share (a post, an
  achievement row, months, the month's games, the follow button), `src/screens/`
  one folder per screen, `src/app/` the shell (the run mode — Telegram, browser
  or installed — the layer stack, the context). Tabs: Главная · Лента ·
  Рейтинг, search a separate button. **The feed groups an achievement got by
  several people within ten minutes into one post «вместе»** (owner,
  2026-10-26), and **mixes in the news of the viewer's favorite games only**,
  laid out as a post (the game in a person's place); every post of one game is
  on its page — there is no news tab (owner, 2026-10-26). A post, a news post
  and an achievement open as one kind of page (`ui/Hero.tsx`: the picture under
  the see-through bar, kind and date, the title, the game a tap away). Where a rule below names a screen, it says what the screen must
  do, not how it looks.
  **Scope** (owner, 2026-10-02): there is no chat picker — the Feed, the Ranking, Home's
  people and `/club/online` are always about oneself plus the followed people
  whose privacy lets the viewer see them (`?scope=following`, answered by the same
  queries through `_sql.member_source`, a list of people standing in for
  `subscriptions`, chat id 0). Chats only help to find people to follow. Search
  is of our own catalog (owner, 2026-10-25: never the internet;
  `/api/mini/game-search`, from two letters; a dotted or apostrophed name
  reads as one word — «stalker» finds S.T.A.L.K.E.R.; owner, 2026-10-29: found
  the way people type — «the» and accents aside, «2» for «II», words in any
  order, words written together («spiderman»), one typo («witchr»), the
  first letters («gta»); `game_page.rank_search`) and of people by nickname (from
  three). A person's card is `/api/mini/people/{id}`; whom somebody follows and
  who follows them, `/api/mini/people/{id}/following|followers`, only to a viewer
  `can_view_activity` lets in. No chat is needed to use the app.
- **Browser sign-in** (shipped; Telegram by migration 074, email by 079): in a plain
  browser the Mini App shows a sign-in screen with Telegram's Login Widget and, when
  a mail server is set up (`/api/mini/auth/config` says `email`), an address field. `POST
  /api/mini/auth/telegram` checks the widget's signature (`mini_auth.
  validate_login_widget`: HMAC with SHA-256 of the bot token, at most 10 minutes old)
  and sets an HttpOnly, SameSite=Lax cookie `ab_session`; `web_sessions` keeps only a
  hash of its token (30 days). A request with no Init Data header falls back to that
  cookie (`_require_user`); a *bad* Init Data header is never rescued by it. CORS
  never allows credentials, so only the same origin carries the cookie. `POST
  /api/mini/auth/logout` ends it. **Setup per bot**: BotFather `/setdomain` must name
  the Mini App's host (`xbox.sultanpharm.com`, `test.xbox.sultanpharm.com`, and the
  dev tunnel) or the widget refuses to render. A session resolves to the person
  (`repo.session_person`), who may have no Telegram id (`MiniAppUser.tg_id` is then
  None and the Telegram corners — chats, publishing — are empty).
  **The sign-in screen signs in with Telegram in the same tab** (owner,
  2026-10-07): «Войти через Telegram» goes to `oauth.telegram.org/auth` (the
  bot's public id from `/api/mini/auth/config`'s `bot_id`) and comes back with
  `#tgAuthResult=` — the same signed fields the widget gives, checked the same
  way; the Login Widget's popup opened as another tab on phones and its answer
  was lost. The widget stays where no `bot_id` is known, and in Settings →
  «Вход», where a phone links through the bot instead. Somebody the app already
  knows — by address or by Telegram — never meets the invite step.
  - **Email** (#162, `services/email_login.py`, `web/mini_logins.py`): `POST
    /api/mini/auth/email/start` sends a six-digit code, `/verify` checks it and opens
    a session — for the person with that address, or a new person without Telegram,
    who gets a nickname at once. A code lives 10 minutes and takes 5 guesses; only an
    HMAC of it is stored (keyed from `FERNET_KEY`); a new one replaces the last; one
    address gets one a minute and five an hour. **A guess is counted before it is
    compared, in one statement** (`take_email_code_attempt`), so parallel requests
    cannot share one count; a code marks itself used only once. Per client
    (nginx's `X-Real-IP`, in memory, `mini_logins`): ten codes sent an hour and
    twenty checked in ten minutes, and a hundred sent an hour by the whole app —
    the mail server's reputation is everybody's. All three are the admin's global
    settings (`email_codes_per_client_hour`, `email_checks_per_client_10min`,
    `email_codes_total_hour`), read on every request. **An address nobody has
    brings its invite to `/start`** (owner, 2026-10-07): without a usable one the
    answer is `invite_required` / `invite_invalid` and no mail goes out — a
    stranger costs the mail service nothing. So the answer does tell a known
    address from an unknown one; the owner chose that over mailing codes nobody
    could use. The sign-in screen asks for the invite at that moment and then
    sends the code. Errors are codes the Mini App words: `invalid`, `too_soon`,
    `unavailable`, `send_failed`, `wrong_code`, `expired`, `taken`, `already`,
    `last_login`, `admin`, `in_telegram`, `not_linked`; a `taken` that a merge can
    answer carries a `merge` preview (`GET|POST|DELETE /api/mini/me/merge`).
  - **Invites** (owner, 2026-10-05; `services/invites.py`, `web/mini_invites.py`,
    `db/repo/_invites.py`, migration 082): for now **somebody new signs up in a
    browser only with a code** — by email, or by the Login Widget. Inside
    Telegram (the bot, the Mini App there) nobody needs one: those people come
    from the community's chats. Any member makes codes in Settings → «Пригласить
    друга» (`XXXX-XXXX-XXXX-XXXX`, no look-alike symbols): one code lets one
    person in, never expires, no limit, and who came by it is kept and shown. A
    sign-in that proved somebody new without a usable code (a Telegram one, or an
    invite spent between an email's code and its check) answers
    `invite_required` (403) with a `signup` token, kept in memory 15 minutes;
    the app asks for the code and `POST /api/mini/auth/signup` finishes it. A
    shared link (`?invite=`; a code's copy icon puts the code and its link in
    the clipboard) carries the code into the sign-in, and no step shows. An
    unused code is deleted by its trash icon.
    `invite_invalid`, `signup_expired`. The dev server's no-code email mode still
    asks for an invite.
  - **Passkeys** (owner, 2026-10-08; migration 089, `services/passkeys.py`,
    `web/mini_passkeys.py`, `db/repo/_passkeys.py`): a key on a phone or a
    computer signs its person in in place of the email's code. Settings →
    «Вход» → «Ключи доступа» adds one (named by the device, «iPhone · Safari»),
    lists them and removes one; only in a browser — inside Telegram the app
    signs in with Telegram. **There is no separate «sign in with a key»**: the
    sign-in screen sends `/auth/email/start` with `passkey: true` when the
    browser can use keys, an address with keys is answered with their options
    instead of a mail, and the phone asks for the key; refused or not at hand,
    the screen asks again with `passkey: false` and the code goes out.
    `POST /api/mini/auth/passkey/verify` checks the answer and opens a session.
    The checking is py_webauthn's (the one dependency added for it: CBOR, COSE
    and a signature over the browser's data are no place for code of our own):
    the challenge given out (in memory, five minutes, spent by any answer), the
    origin and RP id from `MINI_APP_URL` (no https address, no passkeys —
    `/auth/config` says `passkey`), the stored public half and its count. A key
    belongs to its domain: one made on a dev tunnel dies with the tunnel. A
    merge moves the keys with the person.
  - **Asked once for an email** (owner, 2026-10-05; migration 083): somebody
    with no address meets «Добавь почту» on opening the app, after the nickname,
    wherever they opened it — until they add one or say «Позже»
    (`users.email_prompted_at`, `POST /api/mini/me/email/later`); `/me` says
    `email_prompt` only where a mail server can send the code.
  - **Telegram through the bot** (#162): «Открыть Telegram и привязать» gets a
    `t.me/<bot>?start=link_<token>` link (`GET /api/mini/me/telegram/link`); writing
    to the bot through it adds that Telegram, or offers the merge when it already is
    somebody — for a phone, or a host the Login Widget does not render on
    (`handlers/connect.py::_link_telegram`).
  - **Settings → «Вход»**: `GET /api/mini/me/logins`. **Email is the main way in
    and is never removed** (owner, 2026-10-05) — only added or changed, by the same
    code (`/api/mini/me/email/start|verify`). Telegram is added through the Login
    Widget (`POST /api/mini/me/telegram`) and taken away (`DELETE`) only while an
    address is left, never from a super-admin, and only from a browser — inside
    Telegram the app signs in with that very account (`mini_logins._telegram_blocked`:
    `last_login`, `admin`, `in_telegram`). Taking it away drops what came with it:
    the chats (publishing needs Telegram), `chat_seen`, Telegram's names and photo;
    the nickname, accounts, history and follows stay, and that Telegram account
    becomes a new person if it opens the bot again (`repo.remove_telegram`). A login
    that belongs to another person is refused (`taken`).
  - A person without Telegram has no chats to publish to: the app offers to link
    Telegram there. A first nickname for such a person comes from the part of the
    address before the @. `ApiError` keeps a refusal's `error` and body for the
    screens.
- **The Mini App names people by person id** (#156): every person in its JSON
  (feed items, ranking rows, `/online` rows, a person's page, `/me`) carries
  `person_id`, and the app keys faces, profiles, lists and "is this me" by it — a
  person with no Telegram is a person like any other. Faces:
  `/api/mini/avatar/p/{person_id}`; a person's page: `/api/mini/club/people?person=`
  (`chat_id` optional — only which chat it was opened from; the privacy check is
  the gate); a game's progress: `?person=`. A post's «Открыть» button carries
  `p<person id>` (`services/mini_app.py`); a button posted before carries
  `u<tg id>`, which the app still reads: a profile is looked up by it
  (`/api/mini/people/tg/{tg_id}`), and a game page asks by it (`?tg_id=`) and learns
  the person from the answer's `viewed` (person id and nickname). **The super-admin is named by Telegram id** (`SUPERADMIN_TG_IDS`);
  **the people the admin manages, by person id** — somebody who signed in by email
  has no Telegram id: `/admin`'s buttons carry `p<person id>` (`a:u:p12`, a bare
  number from a button drawn before is a Telegram id and still works), the Mini
  App's admin `/api/mini/admin/users/p<person id>`, and the roster's day and month
  counts are per person.
  - Connecting Xbox from the browser works without Telegram: the pending login is
    keyed by the person (`ConnectService`), and with no Telegram id the history is
    read quietly instead of with a status DM.
- **The app's own notifications** (#164; owner, 2026-10-04): what a person is
  told goes through `services/notifier.py::Notifier.notify(recipient, kind, **data)`,
  which keeps it in their list (`notifications`, the latest 200, worded on reading in
  the reader's language from `notifications.ftl`), pushes it to every browser that
  allowed it, and sends it as a Telegram DM. **Every notice is kept in the list; push
  and Telegram each carry only the kinds switched on there — none by default**
  (owner, 2026-10-06; `user_settings.notify_push_on` / `notify_telegram_on`, comma-
  separated `KINDS` keys with a choice after a colon where the kind has one,
  migration 088, which keeps the follower DMs of whoever had them; 087's per-kind
  switches are left unread). Beside that, each channel has its own switch (`notify_push`, `notify_telegram`;
  migration 080), and the DM needs Telegram. One channel failing never stops the
  others, nor what caused the notice.
  Each kind (`notifier.KINDS`) says which channels it takes. Today: a new follower,
  a new friend, a dead Xbox login (`xbox_login_dead`, from
  `XboxAuthService.on_token_dead`) — that one in the list and as a push only: its
  DM is `poller/reminders.py`'s, which carries the relogin button — and a new post.
  - **A new post** (`new_post`; owner, 2026-10-05): somebody followed earned new
    achievements in one game. Every follower's list has it; each channel picks
    whose (friends or everyone followed, `new_post:friends` / `new_post:following`;
    `repo.post_notice_recipients` says who is a friend), and
    `repo.can_view_activity` still gates it.
    It names the first achievement that is not secret, and carries its picture.
    `Publisher.publish` fires it once per call, before any chat filter and after
    the account's own posting switch (#20), in a background task
    (`Publisher.on_new_post` → `Notifier.tell_about_post`), so it never holds up
    publishing. One game is one post: a person hears of it once in
    `POST_NOTICE_INTERVAL` (3 h), however many polls bring its achievements in.
  - **A game's news** (`game_news`; owner, 2026-10-06): a developer's post read
    for the first time (`SteamExtras.refresh_patches` → `on_new_posts` →
    `Notifier.tell_about_game_news`) is told to everybody who earned something in
    that game in the last 60 days (`repo.game_news_readers`): in the list always,
    on a channel by its choice (all, patches, news). Only posts of the last two days, two at most a
    read, and none from an app's first read (its history). **A new post is
    translated before it is told about** (owner, 2026-10-30;
    `SteamExtras.translate_posts`), so a Russian reader's notice names it in
    Russian. **A tap opens the
    post itself** (owner, 2026-10-08): the notice keeps its `appid` and `gid`,
    the list hands them on as `news`, a push's link carries `n=appid:gid`, and
    `GET /api/mini/club/news/post?appid=&gid=[&title_id=]` gives the post (and
    the game's name and picture); the post opens on its own, its game a tap
    away — never the game page under
    it, which a phone's back would close first. A notice from before keeps
    opening the game.
  - **Web Push without a new dependency**: `services/webpush.py` seals a message
    (RFC 8291, `aes128gcm`) and signs it (VAPID, ES256) with `cryptography`, posts it
    with `httpx`; `tests/test_webpush.py` checks it against the RFC's own example.
    The server's key pair is made once and kept encrypted in `app_settings`
    (`vapid_private_key`) — a new one would orphan every subscribed browser. A
    browser that unsubscribed (404/410) is forgotten at once, one that keeps
    refusing after five tries. **Only a known push service is stored as an
    endpoint** (`mini_notifications.PUSH_HOSTS`: FCM, Mozilla, Apple, Windows; https
    on 443): the server posts to it, and an arbitrary address would make it call
    any host, an internal one included. **Push goes only to the app's own
    address** (owner, 2026-10-29; `push_subscriptions.origin`, migration 143): a
    browser keeps one subscription per address, and every dev tunnel kept
    getting the same notice; one of another address is forgotten at start-up.
    Push needs `MINI_APP_URL` (where a tap opens) and a
    contact for the push services (`SMTP_FROM`, else the app's https address).
  - Routes: `GET /api/mini/notifications`, `POST …/read`; `GET /api/mini/push/key`,
    `POST|DELETE /api/mini/push/subscription`; the switches through
    `PATCH /api/mini/settings`; `/me` carries `notifications_unread`.
  - **Reading them**: a notice is read once tapped (`POST …/read` with `ids`), or
    all at once (no `ids`). A tap opens what it is about: a new post's game on the
    author's progress (`game` in the list, `g=` beside `p=` in a push's URL —
    `Kind.game`), and the very achievement a new post names when the notice
    carries it (`achievement_id`, `a=` in a push's URL; owner, 2026-10-26),
    else the person. `listed()` words each notice as `bold`,
    `lead`, `detail` and `image`. The channels' choices are stored as tokens,
    `new_post:friends`, `game_news:patch`, `game_news:favorites`
    (`notifier.carries`); 081's `notify_posts` is no longer read. `core/push.ts`
    says why a device cannot get pushes: inside Telegram (the bot's DMs are the
    notices there), an iPhone page not on the Home Screen (Safari pushes only
    then), a browser without push, push not set up on the server, or blocked in
    the browser.
  - **The app is installable** (a PWA): `webapp/public/manifest.webmanifest` and
    `sw.js`. The service worker only shows pushes and opens the app on a tap — **no
    offline cache**, so a deploy is never hidden behind an old copy. It is
    registered only outside Telegram. Paths are relative or `BASE_URL`, since
    production serves the app under `/app/`. A browser that can install it gets
    offered it (`core/install.ts`: Chromium's own install dialog,
    `beforeinstallprompt`, caught at start-up in `main.tsx`; on an iPhone the
    Share → Add to Home Screen steps) — never inside Telegram or once installed;
    dismissed, it rests 14 days.
- **The phone's "back" steps back inside the app** (owner, 2026-10-05;
  `core/back-stack.ts`): Android's back in the installed app, and Telegram's
  header button (`BackButton`) inside Telegram, close the topmost open layer —
  a screen with a back arrow, a sheet, the game page, a person's
  page, then any tab back to Home — and only then leave. Each layer calls
  `useBackHandler`; a new layer that reuses a component (one arrow, another
  title) passes `layer` so it counts as new. The history holds **one entry per open
  layer, pushed when it opens** — never after a back: Chrome lets back skip an
  entry added without the user's gesture, and a re-armed one closed the app on
  the second back. Changes are reconciled once a moment's layers settle (a
  layer closing as another opens is no step at all), and nothing is pushed
  while a step back of our own is on its way. A new screen with its own way out registers too.
- **A reload comes back where it was** (owner, 2026-10-06; `core/launch.ts::PLACE_KEY`):
  the screen, the person and the game open are kept in `sessionStorage` for the
  tab's session, and a reload with no link of its own (`c`, `p`, `u`, `t`, `g`,
  a start parameter) opens them again instead of Home. A link always wins;
  connecting an account starts over at Home.
- **The game page** (#147, stage 5; owner, 2026-10-25/26;
  `GET /api/mini/game?game_id=` or `?platform=&title_id=`, `web/mini_game.py`,
  `services/game_page.py`): a tap on a game anywhere opens it. One game whole,
  read from the catalog with no network (`docs/mini-app-spec.md` lists its
  parts). DLC the newest first — three on the page, all of them on a page of
  their own with a search (a game may have a thousand), each named without
  the game's name it opens with, and each opening a page of its own (its
  picture, kind and day, what its store says, its hours, its store pages;
  owner, 2026-10-29) —, editions the shortest name first, a
  series its newest game first; a game of a series opens in place and back
  steps back through them. A list in no game yet becomes a game of its own on
  its first visit (`repo.adopt_list_as_game`); the linker places it later.
  **Its gallery** (a rail on the page, all of it on a page of its own with
  videos and pictures apart) **plays the stores' trailers** before the screenshots (owner,
  2026-10-26; `game_page.videos_of`: PSN's mp4, else Xbox's and Steam's HLS,
  each with its picture, six at most), in the app, full screen — links only,
  nothing is downloaded.
  **Its poster, hero and header come from our server** (owner, 2026-10-28;
  `services/game_art.py`): `art_of` hands the app `/api/mini/art/{sig}?u=<store
  address>`, signed with a key from `FERNET_KEY` so the route (no sign-in: an
  `<img>` carries no Init Data) fetches only addresses the server gave out, from
  the stores' picture hosts only. The first request downloads it, shrinks it
  like an icon (1280 px) and keeps it under `data/covers/art/` (named by the
  address's hash); the octopus keeps a game's art as it assembles it. Screenshots
  and trailers stay the stores' links. **Steam's library art of now comes
  first** (owner, 2026-10-30; `steam_store.library_art`,
  `IStoreBrowseService/GetItems`, a hundred apps a request, no key): a live
  game changes its poster and head every season, and the fixed
  `library_600x900.jpg` keeps the launch art, a store's box art may carry
  print marks. It is kept on the Steam version (`media` `poster` / `hero`) by
  the store collection, and again when the game's page is opened
  (`services/steam_library_art.py`, in the background, every 6 hours a game,
  under the store switch); a re-parse of the kept `appdetails` keeps it.
  The poster: Steam's of now, Xbox's, Steam's fixed capsule, PlayStation's;
  the head: Steam's of now, then as before. `scripts/steam_library_art.py`
  fills every Steam version once.
  **Its description follows the achievements' rule** (owner, 2026-10-28;
  #230, migration 138, `services/game_descriptions.py`): a store's Russian is
  kept only when it is Russian (Cyrillic, not its English handed back;
  `_stores.native_ru`) and marked `native`; with none, the English a Russian
  reader is shown — a version's or HLTB's summary — is translated by Haiku
  and kept with a hash of that English (`versions.description_source = 'llm'`,
  `description_ru_of`; `hltb_entries.summary_ru_of`). A changed English text is
  translated again; a store's own Russian replaces ours; no key leaves it
  English. **A game is translated whole, by one job with three doors** (owner, 2026-10-31;
  `services/game_descriptions.py`): its description, every achievement of its lists
  (a Russian side the catalog holds is only marked), its tips, its newest posts. The
  doors: a page opened in the Mini App (`pending`: the text shows blurred, `.translating`,
  and the page asks again; no page waits), the octopus and store collection (`later`),
  and the queue (`poller/translations.py`: `translation_batch_games`, 20, every
  `translation_interval_minutes`, 5; those played here first), **off by default, a
  super-admin's switch** (`translation_queue`, an action beside them in /admin →
  Таймеры). The
  bot's posts wait for their translation instead. What failed rests an hour.
  `scripts/translate_batch.py` runs a share of the queue and prints its tokens.
  **The achievements** of a list (`/api/mini/games/{platform}/{title_id}`) are
  the list and its guides only (owner, 2026-10-26).
  **An Xbox list is split in two** where some of it came later (owner,
  2026-10-27): the main game (`base`) and the add-ons (`non_base`), named
  after the add-on when the list's versions have exactly one, else «Дополнения».
  An achievement's group is the catalog's, else any earned row's
  (`repo.earned_groups`) — the catalog's list often names none; one nobody
  earned and the catalog does not name stays with the main game.
  **A game played on several platforms is one list each, never summed**
  (owner, 2026-10-27): `progress` and every player carry `lists`, the most
  earned first (`repo.game_players`); the progress card and the achievements
  page switch between them, the most earned shown first.
- **Favorite games** (owner, 2026-10-25; `PUT|DELETE /api/mini/game/{id}/favorite`,
  `GET /api/mini/game-favorites?person=`): a heart on a game's page — in the
  page's bar, opposite the way back, over the art and after it alike, its
  count beside it (owner, 2026-10-27) — puts it on
  the person's profile, seen only by a viewer `can_view_activity` lets in. A
  favorite's news are read every hour (`poller/patch_refresh.py`), and told to
  whoever keeps it, played or not — «Новости игр: только избранные» carries
  only those.
- **The season pass** (owner, 2026-10-27; `bot/services/season_pass.py`,
  `web/mini_pass.py`, `core/season-pass.ts`, `screens/season-pass/`, migration 131): the
  month's points (`repo.points_for_person`, the person's own calendar month)
  climb five levels, the calmest theme first and the most colourful last, each
  giving one of the app's themes to claim («Получить», with a burst). **The
  server is the judge**: `POST /api/mini/pass/claim` refuses a theme whose
  points are not reached, and `pass_claims (person_id, palette, month)` keeps a
  claim for good (a merge moves them); `GET /api/mini/pass` is the state every
  screen reads. Violet is everybody's; every other theme opens in Settings →
  Appearance only once claimed, and a theme on the device the server does not
  give is taken off. **A pass a month** (owner, 2026-10-28; migration 136,
  `pass_items.month`): each month's pass is its own levels, **empty until the
  super-admin publishes one**; the editor works on this month or any of the
  eleven ahead (`?edit=`, `EDIT_MONTHS`, picked in a sheet that counts each
  month's levels), so a pass is built ahead and shown on its 1st. A month's
  pass may have a name, its theme («Хэллоуин»; `pass_seasons`, migration 137,
  `PUT /api/mini/pass/season`), shown on its card and waiting for the
  month's publish like a level — and a cover (migration 139,
  `PUT|DELETE /api/mini/pass/season/image`, saved again by
  `pass_pictures`, placed and zoomed in a 16:9 `Cropper` first): the pass's head is an achievement's (`Hero full`:
  the cover edge to edge with the months' arrows on it, a flower on its corner
  with the days left, then «Сезон · Октябрь» and the season's name),
  and the page takes its colours from it (`useArtTheme`), no colour picked by
  hand.
  The super-admin's arrow › goes on into the months ahead that have a pass
  being built, each shown as anybody will see it on its 1st (a preview). Earlier months
  are looked back on (`GET /api/mini/pass?month=`, the arrows by the month's
  name): their points, what was claimed, one's own codes — nothing is taken
  from them. A theme once claimed is kept for good, whatever month. A prize's
  codes left are a badge on its card's right, loud when a quarter or fewer
  are; a tap lists who took them (`GET …/items/{id}/takers`: nickname, face,
  when — never the codes). Home's month card shows the race of friends and, under
  it, the door to the pass. Every month runs the same levels again.
  **The pass is the super-admin's to build** (owner, 2026-10-28; migration
  133: `pass_items` — a level each, `theme` / `game` / `code`, its points,
  `state` draft / live / removed and its waiting changes in `pending` —, and
  `pass_item_codes`; `db/repo/_pass.py`): the app's five themes are written
  once as live levels (`ensure_pass_seeded`), and from then on any level may be
  added, changed or deleted in the Mini App's pass («Изменить», the
  super-admin's alone — an exception to the admin registry's rule of both
  panels) **only while nobody has it**: a theme claimed or a code taken locks
  it (409 `taken`). Every edit is a **draft only the super-admin sees**: a new
  level is `draft`, a change to a live one waits in `pending`, a deletion is
  `pending.remove`; **one «Опубликовать»** (`POST /api/mini/pass/publish`)
  lays it all in, in one transaction, skipping a level claimed meanwhile;
  «Сбросить» throws the draft away. The bar sits where the tabs do. A palette
  is one level's. The points field shows this month's best score and last
  month's best and middle (`_month_scores`, each person's own month, counted
  again every ten minutes). A prize is a stack of codes, **one to a person**,
  for whoever has its points this month (0 is anyone), until they run out — a
  code is taken by one statement, so two taps never get the same one, and a
  prize taken down stays for whoever took a code. It is **a game of ours**
  (picked from the catalog: its name, cover and page) or **a code** for
  anything else — **a game the catalog lacks is added by hand** (owner,
  2026-10-30; the picker searches **our catalog**, and its field's «Добавить
  игру» opens the add-game page over the editor, which searches **Steam's and
  Xbox's** and hands the game it adds back to the prize — `GET /api/mini/pass/game-search`, `services/manual_games.py`, one row
  a game with its id in each store — **leaving out every game the catalog already
  has**, by a store id or by a name the matcher reads alike
  (`manual_games.existing_game`, `Repo.game_name_index`): a hand-added game must
  never be a duplicate, and `POST /api/mini/pass/games` returns the existing game
  even when asked to add it. A pick the catalog lacks → `Repo.add_manual_game`:
  one stand-in version of no store so a rebuild keeps it, the store pages' keys
  queued for the octopus; the linker joins it to the real game when the stores
  bring one and the old id resolves to that
  (the same search is the super-admin's «+» in Home's «Игры месяца» head,
  `screens/home/AddGame.tsx`: pick a game the catalog lacks, it is added and its
  page opens) —, with a picture of its own if sent (`PUT …/items/{id}/image`,
  saved again as a JPEG by `services/pass_pictures.py` under
  `data/covers/pass/`, served to anybody). Themes and prizes are **one
  vertical timeline, by points**: a rail with a node and the points of each,
  filled up to a «Ты здесь» row (what is next, and how far), a card each. Every
  screen showing the pass asks again each minute and on coming back to the
  app, so a publish shows with no reload. «Оповестить всех» in the publish
  dialog tells everybody of the new levels (`pass_reward`, the one notice kind
  **on until switched off** — `notifier.DEFAULT_ON`, a channel's
  `pass_reward:off`; Settings → Уведомления, «Призы сезонного пропуска»); a tap
  opens the pass (`t=pass`). **The season's start is told** (2026-10-31; `poller/season_start.py`, `season_start`,
  `pass_seen`, `season_notified`, migration 148): at 12:00 on the 1st in the person's own
  time zone, every ten minutes looked for, once a season, only to whoever has not opened
  the pass's own page since it began (`POST /api/mini/pass/seen`; Home and Settings read the pass too), and only
  when the month's pass has a live level; on until switched off (`season_start:off`;
  Settings → Уведомления, «Старт сезона»); a tap opens the pass.
  **A level reached is told** (owner, 2026-10-28;
  `pass_level`, `Notifier.tell_about_pass_levels`, migration 134
  `pass_reached`): after every publish the month's points are checked, and
  the levels newly reached are marked (each once a month) and told as one
  notice, of the highest — on until switched off, a channel choosing every
  level, prizes only (`pass_level:prizes`: a game or a code, not a theme) or
  none (Settings → Уведомления, «Уровни сезонного пропуска»).
  **TEMPORARY, to be deleted** (owner, 2026-10-30): once, as the second season
  (2026-11) begins, the first one's passes are wiped — every level and code,
  the themes claimed, the levels reached, the seasons' names, all of a month
  before 2026-11 (`services/season_reset.py`, `poller/season_reset.py`,
  `Repo.wipe_pass_before`, marker `season2_reset_done`); a pass built ahead
  for November stays. Remove the three and their wiring afterwards.
- **A skeleton shows a few items, each one plain block** (owner, 2026-10-30):
  a list, a rail, a row of days or faces stands in as two to four blocks of
  its items' own size and shape — no tiny lines or chips inside them; what is
  not a list (a title, a count) keeps its own shape. Every screen's skeleton
  follows it.
- **The month's games are listed newest first** wherever the Mini App shows
  them — Home, a profile, the Ranking, Search (owner, 2026-10-27;
  `users_games_achievements(order="recent")`); the bot's lists keep the count.
- **The ranking's year** is `/club/summary`'s `year`, from 1 January to the end
  of the month shown, in the same timezone (owner, 2026-10-07).

### Naming people and accounts (#51)

**One chain per question, reused — never a new one at the call site.** Four
hand-rolled versions of "who is this" once coexisted and disagreed. A screen that
seems to need a third chain is a question for the owner, not a decision at the
keyboard.

1. **Who is this person?** Their nickname in the app, as shown (`Name#1234`) →
   `id<person id>` (`users.id`) — nothing else (owner, 2026-10-07;
   `naming.person_name(person_id=, handle=)`). Not Telegram's username or names,
   not a platform nickname, not a Telegram id. One name everywhere — posts,
   digests, `/online`, summaries, `/stats`, notices, the Mini App, the admin's
   lists; the platform is the mark beside it. Everybody is given a nickname (see
   People: where a first nickname comes from), and the Mini App makes a person
   without one choose, so the id is a net. `User.handle` is the shown form, digits
   included (`_accounts._USER_COLUMNS` reads `HANDLE_SHOWN`).
2. **Which account is this?** That platform's own chain — used *only* where a line
   names one platform account: per-platform rows in `/stats`, `/panel` and the
   admin's user card, connect/disconnect notices, the account blocks of a digest
   mixing two PSN accounts, and the account blocks on a person's page in the Mini
   App.

| Platform | Chain | Notes |
|---|---|---|
| Xbox | `ModernGamertag` → `Gamertag` → XUID | the `#1234` suffix is never shown; the profile **link** uses the classic `Gamertag` |
| Steam | `personaname` → vanity → SteamID64 | no vanity: `profileurl` degrades to `/profiles/<id>/` |
| PSN | current `onlineId` → previous `onlineId` → `account_id` | the previous id comes from the legacy endpoint, addressed by nickname, and from the value a refresh replaces |

- **A game is never named by its id** (owner, 2026-10-12;
  `util.real_game_name`): Xbox presence answers some titles with their own id
  as the name, and a status said «играет 704208617». A name that is empty or
  only digits is no name: the title is resolved from the cache or titlehub,
  and failing that the line just says a game is on («играет»).
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
- **A step of the account flow never ends in a command to type** (owner,
  2026-09-30): connect, unlink, relogin, the Steam link prompt and the timezone
  picker edit the message they were opened from and end in buttons — "‹ Назад" /
  "‹ В панель" back, "⚙️ Панель" or the next step on. Only what arrives later (a
  backfill's live status, `handlers/backfill.py`) is a message of its own.
- **Time zones are places** (owner, 2026-10-30; `services/time_zones.py`,
  migrations 145, 147 on PostgreSQL): a person's and a chat's zone is an IANA name
  (`user_settings.tz_name`, `chat_settings.tz_name`), so a summer clock change
  follows by itself — Vilnius is UTC+2 in winter, UTC+3 in summer. Every time
  calculation goes through `time_zones` (`local_now`, `midnight_utc`), which
  takes a name or, where none is set, the old offset (`tz_offset_min`, a fixed
  zone; the models' `.tz` gives whichever). 145 turned every offset into a zone
  keeping the same clock: Russia's by city (no clock changes there), the rest
  the fixed `Etc/GMT±N`. The Mini App's picker (Settings → Общие) is a search
  over `time_zones.ZONES`, the phone's own zone offered first
  (`GET /api/mini/time-zones`); a chat's is the admin registry's `tz_name`. The
  bot's DM picker still sets an offset (eight common ones, "Другой ▸" for the
  −12…+14 grid, "✏️ Ввести вручную" for one typed, `+3`, `+5:30`), which
  clears the zone by place.
- **The stale-login reminder is the only DM the bot starts itself** (besides connect
  progress), and it says reconnecting will not replay history into chats.
- **`/panel`** is one self-editing message. Header: the person's identity and one line
  per connected platform, built by the same `platform_header_lines` as `/stats` (#5)
  with links off. Body: one login row per platform, connected or not (`Вход PSN1:`,
  `PSN2:` for several accounts) with only its status — 🔘 not connected, ✅, ⚠️,
  ❓ — no nickname and no check time (owner, 2026-09-30); where achievements
  publish; presence as **one row** (`presence_view.pick_presence`, the same rule
  `/online` uses — names the platform only while online). The rarity mode and the
  timezone are on their buttons, not in the text. Keyboard: timezone, My chats
  (subscribe / unsubscribe per chat — nothing else is per chat), the rarity mode as a
  carousel ("📣 Публиковать: Все" → Редкие → Никакие, one tap each) for
  every chat (#126), language (#48, DMs only), then one row per platform in the
  display order — `[🟢 XBOX ▸, 🔔 posting switch]` (#10), or one wide "🎮 Подключить X"
  (#33). The platform button opens that platform's screen: profile, the switch,
  unlink, and for PSN every account (up to three) plus adding one — by nickname
  or by the account's own token (#233) —, each with «🔑 Токен ✅/➕/⚠️»: that
  token's screen (what it gives, the safety note, how to get one, paste,
  replace, remove; agreed on a navigable mockup, 2026-10-29). A pasted token's
  message is deleted at once and the result replaces the prompt. The Mini App has the
  same (#233): Settings → Аккаунты → PlayStation → «Личный токен» opens its page
  (`screens/settings/PsnToken.tsx`; `PUT|DELETE /api/mini/psn/token`), «Или по
  токену» on the PSN connect page links one (`POST /api/mini/connect/psn-token`,
  `web/mini_psn_token.py`); `/me` says each account's `token` state, never the
  token; the admin's «Ключи» list the players' tokens beside the keys. The panel's switch
  covers the whole platform ("Частично" when only some PSN accounts post); a Steam or
  PSN button carries ❗ while its achievements are hidden (any one PSN account), and
  that platform's screen then says what it means and puts "🔓 Как открыть ачивки"
  (per hidden PSN account) as its top button — the steps, a link to the settings, and
  "🔄 Проверить снова", which re-reads the account with the live status (#95); a dead Xbox
  login puts "🔄 Подключить заново" in its place, and first on the XBOX screen. The
  publication row names what is switched off. Nothing on it is Xbox-gated. It never
  calls a platform API except the explicit sync button.

### Group chat

- Commands: `/subscribe`, `/unsubscribe`, `/stats [@user]`, `/who`, `/online`,
  `/recent [N]`, `/summary_day`, `/summary_month`, `/hltb`, `/delete_last`, `/help`,
  `/panel` (the group hub). The group slash menu shows four: `/panel`, `/subscribe`,
  `/hltb`, `/help` (`bot/main.py`).
- **`/stats`**: cached stats and games; header `👤` + the person (chain 1), each
  platform on its own line. **`/who`** picks a known member and opens their `/stats`;
  its buttons name the person (#40).
- **Profile links** on cards follow the admin's one switch (`app_settings
  ['show_profile_links']`, on by default, /admin → «⚙️ Настройки» → Правила; owner,
  2026-09-29) — no longer each person's own setting.
- **`chat_seen`** tracks anyone who wrote in the group; `/online` and `/who` use it,
  not just subscribers.
- **A capped leaderboard** gets one button that replaces the message with the same
  block uncapped, in a plain blockquote.
- **Bot replies to commands carry a "Закрыть" button** (`views/keyboards.py::
  with_close_button`); closing `/online` also stops its auto-refresh. Achievement
  notifications do not get one, nor do the day and month reports the bot posts on
  its schedule (owner, 2026-10-01) — paging one keeps it without
  (`keep_closability`); the same report asked for by command keeps its button.
- **`/delete_last`** removes the bot's latest message in the chat whatever it is —
  **except an achievement notification**, single or digest, which it never takes
  (#101; `bot_messages.is_achievement`, set under the publisher's
  `achievement_category()`). The admin panel's and the Mini App's "delete last" share
  the query. The chat's admin and the app's admins may use it (#232). It quotes the first lines of what it deleted, and that confirmation is a
  system message the cleanup job removes later.

### Admin

- **Four roles, one table** (owner, 2026-10-28/29; #232; `services/roles.py`):

  | | user | chat admin | app admin | super-admin |
  |---|---|---|---|---|
  | own things, feed, games, pass, invites, group commands, `/promo` | ✅ | ✅ | ✅ | ✅ |
  | a chat's settings, «Сообщения» (`/delete_last`, wipes), promo | — | own chat | all | all |
  | hand the chat admin role on (losing it) | — | ✅ | — | — |
  | appoint / remove a chat admin | — | — | ✅ | ✅ |
  | people: cards, exclude, avatar, refresh an account | — | — | ✅ | ✅ |
  | season pass editor, global settings | — | — | ✅ | ✅ |
  | keys, delete a person, reset an account, roles | — | — | — | ✅ |

  - **суперадмин** — one of `SUPERADMIN_TG_IDS` (the old name `ADMIN_TG_IDS`
    is still read) or one a super-admin made (`users.role`); only they give
    roles — one step up or down, confirmed, from a person's card in both
    panels (actions `make_admin`, `make_superadmin`, `unmake_admin`,
    `unmake_superadmin`; the lists mark ⭐ an admin, 👑 a super-admin), and
    «⋯» on a person's page in the Mini App (the role from `GET
    /api/mini/admin/users/p<id>/role`, the step by the same actions) — never
    to themselves nor to one the environment names; one the environment
    stops naming loses the role at the next start (`ensure_superadmins`) —
    and they open any person's page whatever its privacy
    (`repo.can_view_activity`).
  - **админ приложения** (app admin, `users.role = 'admin'`).
  - **админ чата** (chat admin): **one per chat, by Telegram id**
    (`chat_admins`, migration 141) — they may never have used the app.
    Whoever adds the bot to a group becomes it; removing the bot (or a 403)
    clears it (`repo.deactivate_chat`), and adding it again appoints the
    adder again, so a group fixes a stuck bot by itself. Existing chats took
    `chats.added_by`. They hand it on to a known member of the chat
    (subscribed or seen writing, `repo.chat_admin_candidates`) and lose it;
    an app admin appoints or removes; the new one is told in a DM when the
    bot may write to them. They reach their chat by `/admin` (their chats
    only) or the group hub's «🛠 Управление чатом» (`?start=chatadm<id>`).

  **Every action and screen says what it needs** (`roles.Need`: `chat`,
  `admin`, `superadmin`; an action's `needs`, a setting's by its scope) and
  `Access.allows` is the one answer: a button nobody may press is never
  drawn and a request for it is refused, in both panels. `/me` says `role`,
  `is_superadmin` (the app admin door, an admin's too) and `chat_admin`.
- **One source for both admin panels** (#176; owner, 2026-10-08: a new admin
  setting appears in the bot and the Mini App at once). Both only render what
  these services answer:
  - `services/admin_registry.py` — **every setting**, global and per chat, one
    row each: where it lives, its kind (number, decimal, on/off, one of a list,
    an hour, a time zone), bounds or choices, group, label, hint. `set_value` is
    the one way either panel changes one — parsed, bounded, stored; a bad value
    is refused the same from a typed message and from JSON. A time zone is a
    place, listed as Windows lists them («(UTC+02:00) Вильнюс, Киев, Рига…»,
    `time_zones.ZONES`, one row a clock; any valid IANA name taken),
    shown with its offset now in both panels; summaries go out on the hour.
  - `services/admin_status.py` — the home (`AdminStatus`: counts, API usage,
    sign-in emails against their caps, every credential's state). **The API
    load** (owner, 2026-10-12; `services/api_usage.py`, noted as each request
    is made, in memory for 24 hours — a restart starts it over): XBOX, Steam,
    PSN over 5 minutes, an hour and a day — Xbox per account, as «median /
    busiest» over the Xbox accounts polled, a quiet one counting as nought
    (Microsoft's budget is each person's, so a total says nothing); Steam's 100 000 a
    day beside its day; PSN with no limit claimed; Anthropic's requests and
    tokens over an hour and a day; the sign-in emails with their mail server.
    **The octopus** has a row of its own there (owner, 2026-10-25): on or
    off and its pace, the queue (and what waits to be retried), how many it
    assembled in the last hour and day, its failures, the last game.
    `views/admin_home.py::usage_rows` words them once: the bot's home prints
    them, the Mini App's «Ключи» lists them as the server sends them.
  - `services/admin_credentials.py` — the shared credentials (`set` raising
    `CredentialInvalid` / `CredentialSetupError`, `clear`).
  - `services/admin_actions.py` — **every action**, one class each: what it
    is about (a person, one game account, a chat, or the app as a whole —
    `global`, target `all`, drawn in the settings group its `section`
    names), its label, whether it is
    dangerous, how many confirmations it takes and their words, what it does.
    `available` lists a card's actions; `perform` takes one a step at a time —
    `Confirm` (the words, the "yes", the next step) until the last step, then
    `Done`. The bot draws a confirmation as a screen («Да / Отмена»,
    `a:x:<scope>:<target>:<action>:<step>`), the Mini App as a dialog
    (`GET|POST /api/mini/admin/actions`); the
    steps and the words are the server's. Today: exclude / restore, refresh and
    reset an account (reset asks once, naming it), take a chosen picture down,
    delete a person (asks twice); globally, the notification test (in
    Правила); on a chat, the promo (asks once), delete the
    last message, the three wipes (each asks once with the count). Under them,
    `services/admin_accounts.py` (refresh: presence, then the delta since the
    newest unlock; reset) and `services/admin_cleanup.py` (which messages a wipe
    takes, deleting them).

  A new setting is a registry row and its `admin-setting-*` label; a new
  action a class in `admin_actions.py` and its strings; a new credential a
  registry entry and its `admin-keys-<name>-*` strings; a new counter an
  `AdminStatus` field. The bot draws a setting as "Label: value ▸"
  (on/off flips, a pick opens its values, a number is typed); the Mini App as
  a row of the same kind. Neither panel parses, bounds or stores a value itself.

  **The rule for whatever comes next** (owner, 2026-10-08): a super-admin
  setting or action is added to its registry and nowhere else — never as a
  screen, a button or a field of one panel only. A new way to confirm or a new
  kind of input for an action is added once, for both panels, like a new kind
  of setting. A setting of a kind the registry does
  not know yet (a list of games, free text, a date, …) is not drawn ad hoc
  either: the kind is added **once, for both** — a `Kind` with its parsing in
  `admin_registry.py`, its drawing in `views/admin_settings.py` and in
  the Mini App's admin — and from then on every setting of
  that kind appears in both panels by itself.
- **`/admin`** (private, self-refreshing): credential health; "🔑 Ключи платформ" —
  one button per credential with its state as an icon (✅ / ⚠️ / ⚪️; #233, agreed
  on a mockup 2026-10-29), each opening its own screen: state, last check, load,
  where to get it, set / change / clear the Steam key, PSN NPSSO, Anthropic and
  YouTube keys and the mail login (#17); beside them «👥 Личные токены PSN»,
  whose own token reads which account and whether it works, and the user card's
  PSN block says which token reads each account — a key or token is
  **never shown back**, and entering one is a single-message state with only a way
  out; API usage; «⚙️ Настройки» — the registry's global groups (Правила: the
  rarity threshold, the digest size, profile links, the post picture, its card, scale and small-icon limit · Новые пользователи: the
  mode they start with · Списки · HLTB · Таймеры · Почта · Прочее), `0` worded
  by what it means; the user list; the chat list and
  per-chat cards; exclusion; bot-message cleanup.
- **The per-chat card** opens the registry's chat groups — Основное (publishing,
  language, time zone) · Итоги дня (on, the hour) · Антифлуд (limit, window) — and «Сообщения» (the wipes), each redrawing in place
  with the card's text above. There is no minimum gamerscore
  (owner, 2026-10-08: it held back every Steam and PSN achievement; the column
  `chat_settings.min_gamerscore` is left unread). **Publishing** (owner,
  2026-10-29; `chat_settings.publishing`, migration 141) is the chat admin's
  switch for posts there; `chats.is_active` is the bot's own (removed, added
  back) and no setting — a manual "off" was undone by the next `/subscribe`.
  The card names the chat admin, and «👤 Админ чата» appoints or hands it on.
- **The per-user card**: the person (chain 1) and their id, then **every way they
  sign in** (owner, 2026-10-07; `services/logins.py`, the same list the Mini App's
  admin card shows): Telegram (`@username`, its id passed to Fluent as a string,
  never `@N`), email — each linked or "— нет"; a new way in is one more entry
  there. Then one block per platform in the display order — nickname,
  lifetime count with completions (🌀/👾/💠) and level, today's count, diagnostics.
  Under them the chats subscribed to and the person's rarity mode («Публикация:
  все / редкие / никакие»; owner, 2026-10-25), on both panels' cards.
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
- **Game line**, italic: game, the version played (below), and the person's progress `47/50` when the
  total is known (#46). Totals: Xbox 360 from `title_history`; modern Xbox from
  titlehub or, when titlehub says 0, the size of the per-title response stored in
  `achievement_list_connectors.achievements_total` (Microsoft's count wins where it exists); Steam from the
  schema; PSN from `defined_trophies` for every listed title (#60), **DLC included**.
  A count, never Sony's tier-weighted percentage. No known total: no counter.
- **PSN group line** (#46), only when the game has more than one group: the group
  and progress inside it (`CTNS: The Heist · 3/7`). A name equal to the game's reads
  "Основная игра"; a name starting with the game's keeps only the rest; never a "DLC"
  prefix (a group is not always one) — `services/achievements.py::_group_label`.
- Then the badge and the name in quotes, gamerscore (if nonzero) and rarity as a
  bare percentage (if known — no word, owner 2026-09-25), then the description —
  behind a spoiler if secret.
- **Badges**: `rarity_badge()` — 💎 at or below the rarity threshold, 🏆
  otherwise (including unknown). PSN shows its tier instead (see PSN).

### Which platform a screen names (#114, owner, 2026-09-24)

Three questions, one function each in `services/platform_format.py`:

- **The version played** (`played_version`) — the card and digest (full name),
  `/recent` (short). The game's *original* platform, picked by the device it ran
  on: a 360 game is 360 even through backward compatibility, a One-only game on a
  Series is One, Smart Delivery is the console's own version, a Play Anywhere game
  on PC is PC. The cloud runs the console version and adds ☁ (a phone without a
  native version is the cloud). PSN the same: a PS4 game on PS5 is PS4, a
  cross-buy game is the version played. Play Anywhere is never a version played.
- **The release platforms** (`game_platforms_label`) — the games lists, short:
  here XPA exists.
- **The device** (`device_label`) — `/online`, short.

Unknown is never guessed: a game on several platforms with no device, or nothing
known at all, is its family — **XBOX**, **PSN**, **Steam**. A game whose platforms
could not be found (`'[]'`, see Data model) names the device's own version.

| | full | short |
|---|---|---|
| Xbox | `XBOX Series X\|S`, `XBOX One`, `XBOX 360`, `XBOX PC`, `XBOX Mobile`, `XBOX Play Anywhere`, `XBOX One \| Series` | `Series X\|S`, `One`, `360`, `PC`, `Mobile`, `XPA`, `One \| Series` |
| cloud | `XBOX Series X\|S ☁` | `Series X\|S ☁` |
| PSN | `PlayStation 5`, `PlayStation 4 \| 5`, `PlayStation 3 \| 4 \| Vita`, `PlayStation Vita` | `PS5`, `PS4 \| PS5`, `PS3 \| PS4 \| Vita`, `PS Vita` |

Short names drop "XBOX" because a platform logo will precede them (#105) and
complete the name; a PSN short name never has a bare digit. "XBOX" is always
upper-case. `/panel`'s "now" row names only the family, as its header lines do.

### Digests

- One header ("получает N достижений" / "N трофеев" for an all-PSN batch), one block
  per game with the game's own counter, every item in the card's line format, the
  descriptions in italics (owner, 2026-09-25) and the block's version named by
  whichever item knows its device. A
  `sendMediaGroup`, caption on the first image, images deduped — or, with the
  Mini App button, one photo of the game's cover (Publication rules).
- **The anti-flood digest is the same form**, named by the person like every post;
  two accounts of one platform name their blocks.
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
  by the rarity threshold, PSN tiers, zeros dropped (`views/parts.py::value_parts`).
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
| the admin's user list | listing (plain) **and** inline | `repo.admin_users()` | everybody, 🔘 with no game account (owner, 2026-10-10) | `is_excluded` ↑, `last_online_at` ↓, newest first | `PAGE_SIZE`, `◀️ N/M ▶️` |
| the admin's chat list | inline | `repo.admin_chats()` | every chat | `is_active` ↓, title ↑ | — |
| `/who`'s picker | inline | `repo.chat_member_presence()` | as `/online` | as `/online` | — (three per row) |
| `/panel`'s "Мои чаты" | inline | `repo.user_chats()` | active chats this person subscribed to or wrote in | title ↑ | — |
| the admin's settings | inline | `admin_registry.SETTINGS` | one group's settings | the registry's order | — |
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
- **Rarity is read from the catalog** (`title_achievements.rarity_percent`, #119),
  through `_sql.py`'s `rarity()` / `rarity_cache_join()`, with
  `seen_achievements.rarity_percent` as the fallback — rarity is a fact about the
  achievement, and the row is a never-updated snapshot. Xbox rarity comes only with
  contract 4, so the contract-2 history is filled by `poller/rarity_backfill.py` — one request per title covers every
  owner. Every platform's poll also writes it. Nothing expires: a year-old
  percentage is worth more than none. Xbox 360's rarity comes from contract 3
  (#121; live polls and `poller/rarity_backfill.py`), so 💎 and `rare` mode
  apply there as everywhere; in `rare` mode an achievement whose rarity is still
  unknown is held back.
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
  `account_latest_unlock` (it asks when data starts), and
  `psn_titles_missing_groups` (it only orders a queue).
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
  by HLTB id. An HLTB outage is an expected failure.
- **A cached entry is read again when stale** (owner, 2026-10-06;
  `services/hltb.py::is_stale`): every 3 days for a game of this year or last, or
  one with no main-story time yet — its players are still timing it —, else every
  90 days. On the next lookup, never by a walker; a failed re-read keeps what is
  stored, and an unchanged summary keeps its translation.
- **Game descriptions come from HLTB itself** (#2): no id-matching between services,
  and console exclusives are covered. Read from the page's `__NEXT_DATA__`
  (`profile_summary`, beside `genre`), never from rendered HTML whose class names
  change every deploy.
- **The HowLongToBeat mirror** (owner, 2026-10-15; migration 112, `hltb_entries`
  and its child tables, `stores/hltb_page.py`, `repo.save_hltb_page`): one row per
  entry — a game or its additional content (`game_type`; an additional content's
  `parent_hltb_id` is its main game) — with **every field the page gives**, named
  as HLTB names it where we had no name, hours as the seconds HLTB gives (0 is
  none, a count stays a count): identity and ids (Steam, itch, IGN), studio,
  genres, release dates by region, ratings, the score, the average / median /
  fastest / slowest / count of main, extra, 100% and all, speedruns, co-op and
  multiplayer hours, the modes it has, HLTB's own users' counts (stored; shown
  or not is the Mini App's decision). Beside it: `hltb_platform_times` (a row
  per platform), `hltb_platform_groups` (platforms sharing one set of hours),
  `hltb_entry_platforms`, `hltb_review_scores` (the users' scores), `hltb_related`
  (named entries that are not additional content). **Nothing is copied into our
  tables** — a game, a version and a DLC link to an entry (`version_hltb`,
  `dlc_hltb`) and read it. An entry's own page is the only one that sets its
  type, parent and hours (`page_read_at`); another page's row of it fills an
  entry no page was read for and overwrites nothing. The raw page stays in
  `source_payloads`, so every field is read again from it with no request
  (`scripts/reparse_store_payloads.py`).
- **What a game, a version and a DLC take from the mirror** (owner, 2026-10-15,
  `db/repo/_hltb_read.py`, `services/hltb_platforms.py`) — read through the
  links, never copied: a **game** takes the hours of its main game's entry
  (`repo.game_hltb`: the entries its versions are linked to that are not
  additional content; the operator's link first, then the surer score, then the
  entry most versions share); a **version** takes the row HLTB keeps for its
  platform (`repo.version_hltb_platform`: our console → HLTB's name,
  `hltb_platforms.HLTB_PLATFORM` — a PC of any store is "PC" —, its row in
  `hltb_platform_times`, else the group in `hltb_platform_groups` that names
  it); a **DLC** takes its entry's own hours and the row of its version's
  platform (`repo.dlc_hltb_platform`). The viewer shows all three.
- **`/hltb` and the Mini App read the mirror** (owner, 2026-10-15; the old cache
  `hltb_cache` is gone, migration 113): `services/hltb.resolve` gives the entry
  a person picked — its page read when it never was and again when stale
  (`is_stale`: 3 days for a game of this year or last, or one with no main-story
  time yet, else 90), a failed re-read keeping what is stored — as the
  `HltbResult` the cards and the Mini App take (`result_from_entry`); what the Mini
  App shows beyond the hours (rating, studio, alias, release dates, modes, each
  bucket's spread, speedruns: `details_of_entry`) is read from the columns when
  asked, kept nowhere. **HLTB's counts of its own users stay in the mirror and
  are not sent** (the Mini App's decision, 2026-09-29). The Mini App's game page
  shows the hours, the score and the age rating of the game's entry
  (`repo.game_hltb`), read from the mirror; the app no longer searches HLTB
  (owner, 2026-10-25).
- HLTB is English-only, so the Russian side is Haiku's (`hltb_entries.summary_ru`),
  **lazily** — once per summary, the first time someone looks it up; the same
  English text keeps its translation (`summary_ru_of`, a hash of the text it was
  made from; a changed summary is translated again). No Anthropic key: the
  English text is shown.
- The card shows it as a collapsed blockquote capped at `DESCRIPTION_LIMIT` — the card
  is usually a photo caption (1024 characters).
- **An entry's picture is kept on disk** (migration 115, owner, 2026-10-15):
  `hltb_entries.image_path`/`image_hash`/`image_checked_at`, files under
  `data/covers/hltb/`, fetched by `scripts/download_hltb_covers.py` (the site
  refuses a client with no browser headers); stamped found or not, so a missing
  picture is not asked for again.
- **Reading the pages that are missing** (`scripts/poll_hltb.py`, owner,
  2026-10-15: a full poll first, lazy reading later): every entry whose own page
  was never read and that something of ours reaches — one linked to a version
  or a DLC, or the DLC of a game we have —, one page at a time at the site's
  limit, the database copied first, the bot stopped.

### Automatic title matching

**Every game gets its HLTB entry matched for it, without a person ever searching**
(`bot/services/hltb_match.py`, a link of the list's versions, `repo.list_hltb_match`) — the Mini App's
game page shows HLTB's hours and description straight away. `/hltb` above is
unrelated: it stays a person picking from a candidate list.

- **A match is asked for lazily, never by a walker**: once from each platform's
  fetcher, right after it publishes a game's *first* new achievement
  (`services.hltb.ensure_title_match`, called from `poller/fetcher.py`,
  `poller/steam_fetcher.py`, `poller/psn_fetcher.py`), and again from the Mini App's
  game-details endpoint if a game still has no match when somebody opens its page —
  an old game nobody's played lately gets matched the first time anybody actually
  looks at it, not before. **Backfill never triggers it** (backfill never publishes),
  so a freshly connected account's whole library costs nothing up front; the requests
  land one at a time, spread across whenever people actually earn something or open a
  game page, never as a burst. Both call sites end up at the same check (no link
  yet, and `fetch_state` says it is due: a miss is retried an hour later, three in
  a row wait a month) — a
  matched (or three-times-failed) game is a no-op wherever it is asked from.
- **The matcher scores every HLTB search result against every name the game has** —
  its platform names, normalized (accents, apostrophes, `&`, roman numerals) and also
  *cored* (edition/platform tails like "- Definitive Edition", "(PC)", "Reloaded
  Edition" cut off) at a small discount, so an exact match for the full release name
  still outranks the cored one. A differing number is treated as a different game
  (Halo 2 ≠ Halo 3); a DLC/mod entry, one released nowhere near our platforms, or one
  that shipped *before* anybody here could have earned anything in it, all lose a
  little; popularity only breaks a near-tie. A Steam game is settled outright by the
  Steam appid HLTB's own page lists for a candidate, when it lists one.
- **Nothing is accepted below a tuned score, or when a runner-up is too close to
  call** — showing another game's hours is worse than showing none. Verified by hand
  against ~200 real games from this community's library: no wrong match, only
  occasional correct refusals (a placeholder platform name, an ambiguous subtitle).

## Steam guides and patches

What Steam knows about a game beyond its achievements, for the Mini App's game
page (owner, 2026-09-30): a tip for each achievement from the Steam community's
guides, and the developer's posts in the game page's «Новости». Nothing of it is
sent to a chat.

- **Which Steam app a game is** (a `steam_twin` id of its versions, see the data
  model): a Steam game's own `title_id`; otherwise found once, like its HLTB entry —
  the appid HLTB's page lists (exact), else Steam's store search by name
  (`steam_news.pick_appid`, a confident match only: store "apps" include a game's
  DLC and sets). Three failed attempts an hour apart, then none for a month.
  Console exclusives have none, so no tips and no tab.
- **Filled like HLTB** (`services/steam_extras.py`): right after a game's first new
  achievement is published — the fetchers call `SteamExtras.ensure_title` after
  `ensure_title_match`, since the appid comes from the HLTB page — in a background
  task, never on the publishing path. A game nobody earned anything in lately is
  filled when its page is first opened.
- **Guides and patches belong to the Steam app** (`steam_apps`, `game_patches`), shared
  by the Xbox, PlayStation and Steam versions of one game; tips belong to our
  achievement (`title_achievements.tip_*`).
- **Tips**: the most popular "achievement" guides (`IPublishedFileService/QueryFiles`,
  the Steam key), each page read as numbered lines. **Only a guide that names its
  achievements on lines of their own is used** (owner, 2026-10-01: every other
  layout came out crooked, and rules or word lists guessing at it broke on each new
  guide): such a guide is cut into blocks, one from each name to the next, and
  Haiku (`services/translate/guide_tips.py`) picks, inside each block, the lines that
  help to get that achievement — leaving out what the description already says and
  what the author says to the reader (greetings, thanks, credits, translation notes),
  in several pieces where those sit inside. It answers only with line numbers of the
  block; the tip is those lines copied from the guide, so nothing is invented and
  pictures, videos, lists and tables survive. The guides are taken most popular
  first, and **the first one that fills at least half of the game's achievements is the
  only one used** — the others are not even read from Steam (owner, 2026-10-01); until
  one does, what each gives is kept, the earlier guide's account of an achievement
  standing. A guide naming fewer than three achievements on lines of their own is
  passed over, and so is one the model finds to be in neither English nor Russian (it
  is asked, by the same call). **A guide is bought from the model once**
  (`title_guide_reads`): its fingerprint covers exactly what the prompt shows (the
  guide's lines, each achievement's shown name and description, both names for the
  name marks — a Russian side filled in later changes nothing), and the answer itself
  (the line ranges) is stored beside it, so a hit cuts the tips again whether they
  were kept or lost to a later guide. 8000 characters at most, cut at a line.
  PlayStation's platinum gets none. No Anthropic key: tips are not read and nothing is
  stamped as read; a model that could not be asked leaves the game to be read again.
  Guides mostly in Chinese/Japanese/Korean are passed over; a tip needs words
  (pictures, videos and bare links alone count as no tip). A visit reads tips only
  for a game whose tips were never worked out; a set a month old is re-read by
  `poller/patch_refresh.py`, one game a tick, only for games played in the last 30
  days — so a crowd opening a game, or thousands of games, never means a read each.
- **Links, videos, pictures** stay in the text: a link as `[label](url)`, a video (a
  guide's embedded player, a post's `[previewyoutube]`) and a picture (a guide's
  screenshot, a post's `[img]`) as their address alone on a line — the Mini App draws a link, a video card and a
  picture.
- **Steam's community site refuses bursts** (429): guide pages are read one at a
  time, 2.5 s apart, for the whole bot; a refusal pauses every read for 90 s. Pages
  are kept under `data/steam_guides/` for a week, so a re-read costs no request; the
  last few are also kept in memory, bounded and aged the same week. A read cut short
  keeps its tips but not its time stamp. **The guides endpoint never waits for a
  fill**: it starts one in the background and answers with what is stored and
  `complete: false`, and the Mini App asks again until it is true.
- **Patches and news**: every post of the developer's own (`GetNewsForApp`, `feeds=
  steam_community_announcements` — on a busy day the default feed is other sites'
  articles only), the last thirty, kept in `game_patches` with its `kind` and first
  picture (migration 084), its whole text (`steam_news.TEXT_CHARS` is only a
  net against a runaway post, 2026-10-12): a patch is a post tagged `patchnotes` or titled like one
  (update, patch, hotfix, a version number; not a demo or playtest), anything else
  is news. A post keeps its time, not only its day (migration 085: `published_at` is `…T14:32:00Z`, shown in the reader's own time). The game page shows the newest, all of them a tap away; the feed (owner,
  2026-10-26; `repo.favorite_games_news`, `GET /api/mini/club/news?scope=following&favorites=1&month=`)
  mixes in both for the viewer's favorite games, newest first, one
  card per post however many of our games are that Steam app. Without
  `favorites` the route still answers the games the viewer's circle earned
  something in within 60 days (`repo.games_news`). A post opens whole, its game
  a tap away. **A post is put into Russian as soon as it is read** (owner,
  2026-10-30; `services/news_translations.py`, `translate.client.translate_news`):
  as soon as `SteamExtras.refresh_patches` saves an app's posts, and the posts
  kept before by `poller/translations.py`, the newest first, in its batches, as the
  model answers (up to 50 s a tick); the
  links, pictures and the game's own names (maps, weapons, modes, items) kept
  as they are. **A long post goes in parts** of about `NEWS_PART_CHARS`, cut
  between paragraphs (else at a line's end, never inside one), each its own
  call, put back together with an empty line. A changed post loses its
  Russian and is translated again (`save_game_patches`). Every screen
  showing a post gives a Russian reader its Russian (`mini_chat.news_title`
  / `news_text`).
- **A post can be shared** (owner, 2026-10-30; the page's «Поделиться»): the
  link alone, no text — `/api/mini/share/news/{appid}/{gid}` (`web/mini_share.py`,
  public: a messenger's crawler carries no sign-in) answers a tiny page with
  the post's Open Graph tags (the game and the title, the start of the text,
  the post's picture or its game's art) that sends a person on to the post in
  the app. Inside Telegram the share opens its chat picker, elsewhere the
  system's share sheet, else the link is copied. It sits under `/api/mini/`,
  which nginx already proxies on each host. Outside Telegram the app asks to
  sign in first.
- **An achievement has a page of its own** (owner, 2026-10-05): opened from its
  row in a list (a secret one revealed first), a post in the Feed, Home's
  gallery and the Ranking's lists (owner, 2026-10-09;
  `core/game-open.tsx::useOpenAchievement`, as a game is opened) — its game
  (which opens the game), rarity and points or trophy, the picture whole, when
  it was earned, its name and description, then «Как получить»: the videos and
  the Steam guides' tip whole, when there is one.
- **A picture opens in the app, full screen** (owner, 2026-10-05): the pictures in
  a guide's tip, a post or a patch, the picture at the top
  of a post's or an achievement's page, and a face that zooms. Never on Steam. As
  large as the screen allows, all of it; two fingers zoom and move it, a double
  tap zooms in or back; a tap at its own size or the phone's back closes it —
  nothing is drawn over the picture. Opened with a list (`openImage(src, list)`: a
  game page's screenshots), a finger slides to the next one at its own size
  (owner, 2026-10-26). The feeds keep their taps (an achievement's post opens the achievement, a news post its page).
- **Re-reading**: console exclusives have no Steam app and so no news. Posts are re-read by
  `poller/patch_refresh.py` for games somebody earned something in over the
  last 30 days, every `patch_refresh_hours` (6, /admin), and the apps of
  somebody's favorite games every hour, first — three apps a tick.

### Video guides from YouTube

Guide videos for an achievement, shown on its page in «Как получить» (owner,
2026-10-06; **seven channels since 2026-10-12**, `services/youtube/guides.py::
CHANNELS`: TrophyTom, PowerPyx, PS5Trophies, HarryNinetyFour,
Maka91Productions, 100% Guides and Carrot Helper — the biggest that guide
achievements by name, by their subscribers then; adding one is a line there
and a look at how it words its titles).

- **Read by `poller/guide_videos.py`** with the YouTube Data API key: a channel's
  whole history, eight pages of 50 a tick, the place kept
  (`guide_channels.backfill_token`) so a failure resumes; then its newest page every
  6 hours, and the whole history again every week (`read_through_at`) — a timeline
  is often added to a video long after upload, and only a full pass sees it on an
  old one. A page is one unit of the key's 10 000 a day (~220 a week for the
  re-read). A refused call rests the channel an hour. A page lands in one
  transaction. Nothing is downloaded: a card links to YouTube at the moment.
- **What a video names** (`guide_videos`, `guide_marks`, migration 086): a title
  with 🏆 names one achievement right before it ("House Flipper Remastered - Beach
  please 🏆 Trophy / Achievement Guide"); **so does a guide phrase after the
  name, with no 🏆** ("Mortal Shell 2 - Bag Holder Trophy / Achievement
  Guide"; in parentheses, "… Locations (Bird's-Eye View Trophy Guide)"; the
  part before a bare "- Trophy Guide"), and a title with **no separator**
  ("Mortal Shell 2 Heavy Metal Trophy Guide") carries game and name as one
  run, so its mark is *joined* (`= mortal shell 2 heavy metal`, matched by
  trying each of the game's names before each achievement's) or, with the name
  in parentheses, *loose* (`~name`, the title starting with a game's name).
  A bare phrase or none ("Trophy Guide & Roadmap", "Full Game Walkthrough")
  is a whole game. A description's timeline names moments
  ("02:42 – ACHIEVEMENT – Chainsaw Go…", "– TROPHY – … – PART 2", or a bare name in a
  whole-game video). Every timeline line is kept; collectibles and chapters match
  nothing and never show.
- **Matched on reading, exactly** (`services/youtube/videos.py`): a video is a
  game's when its title's first part(s) — split at " - ", normalized as HLTB's
  matcher does — are one of the game's names or their edition-cut cores, so
  "Gears of War 2 - …" is never Gears of War's; a moment is an achievement's when
  its label equals the achievement's English name, normalized. Nothing is guessed:
  a near miss shows nothing. The newest three per achievement, parts in
  order, **one from each channel before a second from the same one**.
- `/guides` answers them as `videos` beside `tips`; a row with a tip carries the
  book mark, one with a video the video mark beside it.
- **The game's own guide** (`videos.py::game_guide`, `guide` in `/guides`): what is
  matched to one achievement rarely covers them all, so a game a channel has
  videos of gets a video button in the game page's head — a
  whole-game video of any channel when one is titled so ("Full Game", "All
  Achievements", "Trophy Guide & Roadmap"; never one that names an
  achievement), else the search of the channel with most videos of it. Never
  on the picture: that is the game's own (a gallery later).

## Versioning

**`A.B.C.D`** (#56) from `bot/version.py`, shown at the end of `/help` and the hub
and logged at startup (`… is up (v1.4.3.058)`). History: #112.

- **A** — `0` until the app's 1.0, which is far off (owner, 2026-10-31: the old
  major became the minor, so 2.2.1 reads 0.2.1, and the PostgreSQL release is 0.3.0).
- **B** — the minor, a big update: `TRUNK_LINE` on `main`, **one above it on every working
  branch**, so the test server reads the line its work will ship in and "which bot is
  this" is answerable from the version. Only a release that starts a new minor bumps
  `TRUNK_LINE` and tags `v0.Y.0` on `main`; one that does not leaves both.
- **C** — a hotfix or a small update on that minor: commits counted from git at startup, never stored in a file: on a working
  branch since the **merge base** with `main` (so others' merges do not renumber it);
  on `main` since the **newest release tag**, **first parents only** — one per release.
  **Commits that touch only documentation do not count** (`DOCS_PATHS`: any `*.md`
  and `changelog/`), because docs ship without a release. `?` without git; `0` on an
  untagged `main`. **Cutting a release is tagging one.**
- **D** — the newest migration this code ships, not what the database has. A database
  *ahead* of it refuses to start (Data model).

## Security and privacy

History: #112.

- Never commit `.env`, databases, logs, PID files or runtime data.
- Every stored credential is Fernet-encrypted: Xbox refresh tokens, the PSN NPSSO, the
  Steam key, the Anthropic key, the YouTube key. Losing `FERNET_KEY` means every user reconnects and
  every shared key is re-entered — back it up.
- Never log a token, key, NPSSO, authorization header, or a URL with a secret in its
  query — `httpx` logs full URLs at INFO, and Steam's `GetOwnedGames` carries the key.
  Mask first. A user-facing error never shows an upstream token error's payload.
- Revoking Microsoft's consent happens in the person's own Microsoft account; the bot
  only links there.
- **PSN profile links point at PSNProfiles** (#30) — Sony has had no public trophy
  page since 2021. A first visit to an unindexed profile shows "not tracked" and
  indexes it. The bot never checks the link (automated requests get 403).
- Profile links in `/stats`/`/who` follow the admin's global switch.

## Operations

History: #112.

### The move to PostgreSQL (#234)

Agreed with the owner on 2026-10-30, **the fast path**: no dual backend and no
week-long soak — the code moves in one step on `feature/postgres`, is checked on a
copy of production and on the dev server, then both servers switch; production
runs on SQLite until the switch, its downtime the data import alone. PostgreSQL 16
runs on the VPS (localhost). Until the switch, the servers and the deploy script
run as they do; what is left is in #234. The new bot (#238) and `unlocked.how` (#237)
switch after it.

**Scripts open PostgreSQL through `bot/db/tools.py`** (the bot's dialect and rows,
no bring-up): `--schema` in place of `--db`, default `DATABASE_SCHEMA`; an async
script starts with `tools.run`, since Windows' default event loop refuses psycopg.
A script's backup is a `pg_dump` file in `backups/`, so `pg_dump` must be on PATH
(`pg_restore` and `CREATEDB` for `reparse_store_payloads`' dry run). The catalog is
shared, so a script writing it writes the live one whichever schema it names.
**`scripts/sqlite_to_pg.py`** moves a server: `bring-up --out DIR` (copies, with
the SQLite migrations this code ships applied; the source is what a rollback goes
back to), `preflight`, `import --schema`, `verify` (exit 1 on a mismatch, 2 on a
refusal). A source behind the migrations is refused: one may fill a table no schema
file brings. A second server on the same catalog file skips the catalog; one that
differs needs `--merge-catalog`.
**A server moves in this order: stop the bot, bring up, import, verify, install
`scripts/xbox-deploy.sh` by hand, push.** The first deploy would otherwise run the
old script against the new code. The code comes last because **a bot refuses an
empty schema** (`EmptySchemaError`; `DATABASE_NEW_OK=true` for a new database), so
the push before the import leaves it down, never starting over with nobody in it.
While the bots are on different code, `xbox-deploy` installs a checkout's copy of
itself only forward (`DEPLOY_SCRIPT_EDITION`), and a bot whose schema has no tables
is backed up from SQLite.
**A rollback within 48 hours of the switch** (owner, 2026-10-31) is the previous tag on
SQLite and the untouched `bot.db`; what happened since the switch is lost, nothing carries
it back.
**On the day:** the test bot is stopped too while a server's import and linking run (one
catalog), and `--games` names the copy at every step, or they read the live file.
**The connection is one for the process's life**: when the server is gone the bot
exits (`postgres.on_connection_lost`) and systemd starts it again.

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

`manage.ps1` (the bot cannot start itself; it also starts the local PostgreSQL cluster
on port 5433, `stop` stops it once no bot is left on it, `restart` leaves it): `start` / `stop` / `restart` / `status` /
`logs [-Lines N]` / `dashboard` (live view with hotkeys; `manage.bat` opens it), with
`-Test` for the `.env.test` instance on 8081 and `-Web` to tunnel the Mini App.
`status` shows uptime, the port, stray bot processes (two bots on one `BOT_TOKEN`
fight over updates) and a database summary. The restart hooks live in `.git/hooks`,
so a fresh clone does not have them. Never run the dev server on prod's `BOT_TOKEN`.

**The dev server's PostgreSQL is a cluster of the project's own** (#234): port
5433, data in `%LOCALAPPDATA%\unlocked-pg`, trust authentication on localhost,
made with the binaries of the PostgreSQL 17 installed on the machine (its own
service on 5432 is the owner's and is left alone). It does not start with
Windows yet: `pg_ctl -D %LOCALAPPDATA%\unlocked-pg -o "-p 5433" start`.

### The VPS

A VPS at Contabo (owner, 2026-10-30; Cloud VPS 6: 6 cores, 12 GB, 200 GB,
EU, `80.241.212.183`), Ubuntu 24.04, nginx + systemd, dedicated user `botsvc`;
nginx terminates TLS and proxies to the bots, whose ports are never exposed
(`OAUTH_LISTEN_HOST=127.0.0.1`). **Everything it was set up with is in the
repository** — `deploy/` (the nginx sites, the units, prod's shared-folder
drop-in, the SSH socket) and `scripts/provision.sh`, which makes a fresh
Ubuntu 24.04 into this server and never starts a bot; a change made by hand on
the server is made in `deploy/` too. PostgreSQL 16 runs there, localhost
only, for #234.
**SSH is keys only, on port 22022**, as `ubuntu` with `sudo` (Contabo's
admin user); root cannot log in. CI's `deploy` user may run only
`xbox-deploy`; it connects on 22022 too, with `HostKeyAlias` so the pinned
`DEPLOY_KNOWN_HOSTS` entry still matches. Port 22 is closed: `ssh.socket`
listens on 22022 alone; ufw is off, nothing else is exposed.
**Two certificates**: Let's Encrypt for `xbox.sultanpharm.com` and
`test.xbox.sultanpharm.com` (certbot timer), and Cloudflare's origin
certificate for `unlocked.how` and `test.unlocked.how` (#237: behind
Cloudflare's proxy, Full (strict), until 2041; its key was made on the server
and never left it — only the CSR went to Cloudflare), whose sites take the
visitor's address from `CF-Connecting-IP`, trusted only from Cloudflare's
ranges (`deploy/nginx/cloudflare-realip.conf`). The old Spaceship server
(`209.74.85.21`) keeps its bots masked and proxies to this one until it is
deleted.

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

1. backs up **every** time (`data/backups/`, `pg_dump` of the bot's schema and
   `games`) and keeps only the newest of its own copies — **8 on prod, 5 on the
   test server** (owner, 2026-10-23: kept forever they filled the disk); a copy
   named by hand stays. `xbox-deploy backup` does the same for both bots daily
   (`deploy/systemd/unlocked-backup.timer`);
2. `git fetch --prune` and `git merge --ff-only` — never a robot's merge commit;
3. reinstalls dependencies only when `pyproject.toml` changed;
4. unpacks the Mini App CI built (built there, not on the 300 MB box);
5. stops the bot and brings in the catalog's labels and weights from `catalog/`
   (`scripts/catalog_files.py import`: it compares, so an unchanged folder writes
   nothing; a failure still starts the bot and turns the deploy red);
6. starts it, then **verifies** the bot's own `is up (v…)` line, bounded by a timestamp
   taken before the start.

**One run at a time** (`/run/xbox-deploy.lock`): a test deploy, a prod deploy and a
games-database move all stop and start bots on the one box. **A bot the script stopped
is started again on any failure.** The script reinstalls itself from the checkout,
but the run that installs it finishes as the old one: a change to it takes effect
from the next deploy.

**PostgreSQL on the VPS** (#234) is `scripts/provision-postgres.sh` and
`deploy/postgresql/`: database `unlocked`, listening on localhost only; roles
`unlocked_prod` and `unlocked_test`, each with its own schema and its password only
in that bot's env file; `games` owned by `unlocked_games`, a role both are members
of, and whatever is made there is handed to it by an event trigger, so either bot
can migrate what the other made.
**Prod's unit is `ProtectSystem=strict`**: it may write only the folders it
names, so the shared media folder is a drop-in,
`/etc/systemd/system/xbox-bot.service.d/shared.conf`; a new shared folder is added
there, or prod fails with a read-only error.

GitHub holds four secrets (SSH key, host, user, host fingerprint); `.env`, `FERNET_KEY`
and databases never go near it.

**Measure completeness after a release that touches syncing**:
`scripts/check_integrity.py` compares, per account, what each platform reports with
what is stored (#120) — read-only, safe beside a running bot.

**The deploy does not rehearse migrations.** That is a person's job, done on a copy of
production **before merging `prerelease` into `main`** — the last moment it is still a
decision. The test server migrates its own, smaller, differently shaped database and is
no substitute.

### Documentation-only changes

**Documentation travels `dev` → `prerelease` → `main` without a release** (owner,
2026-09-24). A change that touches only `*.md` files and `changelog/` gets:

- **no deploy** — CI's `changes` job diffs the push and the `deploy` job skips it
  (tests and the Mini App build still run, so the required checks report);
- **no version change** — such commits do not advance C (Versioning), and nothing
  restarts to announce anything;
- **no release notes and no minor bump**.

Promote it the usual way (`git push origin dev:prerelease`, then a PR into `main`
merged as a merge commit); the servers pick the files up on their next real deploy.
A change that mixes docs with anything else is a normal change.

**Never put GitHub's skip-CI marker in a commit message — not even quoted.** GitHub
honours it anywhere in the text, and `changes` diffs each push against the one
before it: a skipped push that carried code leaves the servers behind, and the next
push no longer sees that code. If it happens, deploy by hand with the script CI
uses: `ssh <vps> sudo /usr/local/bin/xbox-deploy test|prod`.

### Releases

- **Release notes are written before the merge into `main`** and committed to
  `prerelease`: `changelog/<v>.ru.md`, `.en.md`, `.contributors.md`, and
  `.summary.ru.txt` / `.summary.en.txt` (5–8 `•` bullets for the announcement), where
  `<v>` is `A.B.C`. `main` then always carries its own notes and the announcement
  links never 404. **A release without a new minor is a hotfix or a small update** (owner,
  2026-10-12, 2026-10-31): its notes say so in the title (`# 0.3.1 — хотфикс — …`) and
  the first line, and the announcement's header says so by itself
  (`release_notify.is_hotfix`: C above 0). Under each note's title, a line links its other language
  (owner, 2026-10-10): `**Русский** · [English](<v>.en.md)` in the Russian one,
  `[Русский](<v>.ru.md) · **English**` in the English one.
- **A release is: notes, a short review, then `prerelease` → `main`** (owner,
  2026-09-25). A contributor's pull request targets `prerelease`, never `main`: #129
  merged into `main` deployed at once, and production announced a version with no
  notes behind its link.
- **A release that starts a new minor** bumps `TRUNK_LINE` on `prerelease`, and the
  merge into `main` is made locally, tagged `v0.Y.0`, and pushed **tag first, then
  `main`**: the deploy starts on the push and counts C from the newest tag, so a tag
  added after a GitHub merge arrives too late (production would read `X.Y.N`).
- **On startup each bot announces a new version** (`services/release_notify.py`) once,
  tracked in `app_settings.last_announced_version`: to active group chats only, in each
  chat's locale. Prod sends the summary bullets and a button to the full notes on
  GitHub; the test and dev servers send no links. 0.05s between sends; a chat that
  forbids the bot (or no longer exists) is deactivated — except on the test bot,
  which usually runs on a copy of production's database and is simply not a
  member of those chats: it only logs (the publisher skips such a chat until the
  next start, the daily summary counts the day as done), so neither a version bump
  nor a publication can empty the copy's chat list and, with it, the Mini App.

### Backups

- **`backups/` and nowhere else** (on the servers, `data/backups/`) for database
  copies, dumps and the scripts that make them; `.gitignore` also blocks
  `*backup*.json`, `*dump*.json`, `*tokens*.json` anywhere.
- **A dump never holds a decrypted secret** — copy the database or the encrypted
  column. A decrypted value, when genuinely needed (re-encrypting after a `FERNET_KEY`
  change), stays in memory; if it must touch disk, it lives in `backups/` and is
  overwritten and deleted before the task ends.
- **Back up with the database's own tool, never `cp`**: `pg_dump` of the server's
  schema and of `games` on PostgreSQL; `sqlite3`'s `backup()` for an SQLite file
  (WAL mode). Name copies for what and when: `bot-pre042-20260915-084500.db`.

## Engineering rules

History: #112.

- Handlers are thin — services and repo methods, never raw SQL or platform logic.
- All SQL lives in `bot/db/repo/`, `bot/db/pg/` (the schema files and migrations).
- **Writes that must land together go in `async with self.transaction()`** (#167,
  `db/repo/_tx.py`). The bot has one connection, in autocommit (#234): a
  statement outside a block is its own transaction, so a failed one leaves
  nothing half done, and `commit()` outside a block has nothing to do. A block
  opens `BEGIN`; while it is open everybody else waits before their next
  statement, `commit()` inside it waits for its end, an exception rolls back
  only the block, and a block inside a block is a savepoint. Never call
  `rollback()` (inside a block it raises); keep network calls and file deletion
  out of a block — it holds the connection. A statement that fails inside a
  block poisons the block (PostgreSQL refuses the rest until the rollback):
  catch nothing there that you mean to go on after.
- **SQL is PostgreSQL's, through `bot/db/postgres.py`** (#234). Write `?` or
  `:name` placeholders as before (translated once per statement; a `%` anywhere
  is doubled for psycopg). Numbers, bools and dates go **untyped** (oid 0), as
  SQLite's loose typing took them: a bool is 1/0, a datetime ISO text with a
  space; the flags are integer columns and the dates text. What that leaves to
  write by hand:
  - a placeholder tested alone for NULL needs a type: `?::text IS NULL`;
  - `a IS NOT b` / `a IS b` (b not NULL) are `IS DISTINCT FROM` /
    `IS NOT DISTINCT FROM`;
  - no `INSERT OR IGNORE` / `OR REPLACE` / `UPDATE OR IGNORE`: `ON CONFLICT DO
    NOTHING`, `ON CONFLICT (key) DO UPDATE SET …`, an update `WHERE NOT EXISTS`
    the row it would collide with;
  - every column of a `GROUP BY` select is grouped or aggregated (a table's
    columns follow from its primary key); the row SQLite's `MIN`/`MAX` handed its
    bare columns from is `DISTINCT ON (…) … ORDER BY`;
  - an output name is read bare in `ORDER BY`, never inside an expression nor in
    `WHERE` / `HAVING`: wrap the select in a subquery;
  - `SUM`/`MAX` of a condition is of `CASE WHEN … THEN 1 ELSE 0 END`; the
    scalar `MAX(a, b)` is `GREATEST`; `GROUP_CONCAT` is `string_agg`; `IFNULL`
    is `COALESCE`; `LIMIT -1` is `LIMIT NULL`; JSON is `::jsonb` with `->>`
    and `jsonb_array_elements`; now in our text format is
    `to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS')`;
  - `LIKE` is case-sensitive (`ILIKE`, or `lower()` on both sides); there is no
    `rowid` (an insertion order is a `seq` identity column) and no `lastrowid`
    (`INSERT … RETURNING <id>`, read as a row: the adapter reads a statement's
    rows at once, so nothing stays open on the connection); the jsonb operator
    `?` cannot be written beside `?` placeholders (`jsonb_exists`).
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
- **Screens that lead into each other are one navigable mockup, not a pile of
  messages** (owner, 2026-09-25): a single message whose buttons move between the
  proposed screens (edit in place), with every action a stub that changes nothing
  real. Before it, one plain text message says that it is a mockup and what it is
  for, so nobody mistakes it for the working bot.

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

**The tests run on PostgreSQL** (#234): their own database, `TEST_DATABASE_URL`
(default the project's cluster on port 5433, database `unlocked_tests`, schema
`app`), made empty once a run from the schema files; before each test one call
(`public.reset_test_data()`) empties every table and resets every id counter.
CI runs a `postgres:16` service. On Windows psycopg's async mode needs the
selector event loop (`conftest.event_loop_policy`, `main.event_loop`). A test
that needs foreign keys off says `SET session_replication_role = replica`.

Real Xbox, Steam, PSN, HLTB or Telegram calls are forbidden in tests — mock at the
service boundary.
**`tests/conftest.py` enforces it** (2026-10-24): a host name that is not this
machine's is refused, and a test that reached for one fails at its end with the
hosts — code that swallows a failed request (a store name is best-effort) would
otherwise hide it. Side errands no test is about are stubbed there for all: the
Steam store's game name, and a fetcher's HLTB match and icon caching after it
publishes; their own tests stub them again or call them directly.

Required coverage: achievement/trophy dedup; first-connect backfill publishes nothing;
only earned items enter `seen_achievements` (`InProgress` never leaks in); rarity
filtering at different thresholds, and an unknown rarity under `rare`; Xbox
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
  `docs/*.md` / `*.ru.md`, `changelog/<v>.ru.md` / `.en.md` and their summaries,
  and `bot/locales/ru|en/`.
- **The operator's tools are in English** (owner, 2026-10-24): the catalog
  viewer (`scripts/catalog_viewer.py`, `scripts/trial_page.py`) and every
  script's output — page titles, buttons, questions, notes. Only the bot and
  the Mini App speak Russian, through the `.ftl` files.
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
  different mode per platform. One `rarity_mode` covers all (Xbox 360 too, since
  its rarity is known, #121). (#20 settled it differently:
  a posting on/off switch per *account*, not a rarity mode per platform.)
- **Live platform API calls from `/stats`, the summaries, `/online` or the panel** —
  every normal read is cache-only; the panel's own sync button is the exception.
- **Game descriptions from the Steam store** — HLTB supplies them for every platform
  with no id-matching, console exclusives included (#2). The storefront is used for
  one field only: Steam's Russian game title (#61).
