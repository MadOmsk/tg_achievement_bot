# CLAUDE.md

## Project

Achievement Bot is a Telegram bot for a small, non-commercial gaming community
(roughly 20-30 people). It publishes newly unlocked achievements and trophies from
connected Xbox, Steam, and PlayStation Network accounts, with per-chat rarity
filters, personal stats, an admin panel, daily summaries, HowLongToBeat lookup,
and a Telegram Mini App.

**The app is called Unlocked** (owner, 2026-10-05): it is no longer only a bot.
The name and the logo (owner, 2026-10-07: the "U" of Unlocked as an open
shackle, in the platinum medal's colours, its tip glowing like the end of a
progress arc, on the app's own dark ground with a cool glow above and a lilac one below;
`webapp/public/logo.svg`, a rounded tile; `logo-192/512.png` are rendered from
it, and `apple-touch-icon.png` and `logo-maskable-512.png` from the same drawing
as a full-bleed square — iOS and Android round it themselves — with the mark
inside the safe zone; `badge-96.png` is the white U for a push's one-colour
badge; `logo-splash-512.png` is the bare U with no tile, the manifest's 512
`any` icon that Android draws on its launch splash. The sign-in screens write
the name as one word — the U, then "nlocked" in Nunito ExtraBold, its seven
letters kept in `public/fonts` — `shared/lib/wordmark/Wordmark`; its U alone,
`UMark`, is the install banner's mark) are what the Mini App,
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
product is optimized for one trusted operator, a single SQLite database, explicit
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
HTTP clients), Pillow (re-encoding uploaded avatars), aiosqlite, APScheduler (`AsyncIOScheduler`), pydantic v2 +
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
├── docs/                      guides for whoever runs a server, English and Russian
│                              (`mail-setup.md` / `.ru.md`: the mail server for email sign-in)
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
│   │   ├── admin_settings.py     the admin settings' keys, bounds, labels and defaults
│   │   ├── admin_registry.py     every admin setting, described once, for both panels (#176)
│   │   ├── admin_status.py       what the super-admin's home shows, for both panels (#176)
│   │   ├── admin_credentials.py  every shared credential, one registry for both panels (#176)
│   │   ├── admin_actions.py      every super-admin action, described once, for both panels (#176)
│   │   ├── admin_accounts.py     refresh / reset one person's game account (an action's work)
│   │   ├── admin_cleanup.py      wiping the bot's messages from a chat (an action's work)
│   │   ├── connect.py            one-time OAuth state, finishing a login
│   │   ├── relink.py             linking an account somebody else may already hold (#52)
│   │   ├── stats.py              aggregates for panels, /stats, summaries
│   │   ├── models.py, rows.py    ParsedAchievement and its AchievementRow, shared by all platforms
│   │   ├── naming.py             the naming chains (#51) — the only answer to "what is X called"
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
│   │   ├── hltb.py               howlongtobeatpy wrapper, cached in hltb_cache; ensure_title_match
│   │   │                         is the lazy trigger for hltb_match.py below
│   │   ├── hltb_match.py         which HLTB entry a game is, scored automatically (no DB access)
│   │   ├── steam_extras.py       a game's Steam side: its app, achievement tips, patches — stored
│   │   ├── steam_guides.py, steam_news.py   Steam community guides / announcements (no DB access)
│   │   ├── stores/               what each store says about a game (#147), network and parsing only:
│   │   │                         steam_store.py, xbox_catalog.py, psn_store.py, hltb_page.py
│   │   ├── store_collect.py      collecting one game from them: versions, DLC, HLTB, when due
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
│   │   ├── translate/            Anthropic API via raw httpx, descriptions and guide-tip pointers, never names:
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
│   │   ├── guide_videos.py       guide channels' YouTube videos: the newest page, the whole history weekly
│   │   ├── psn_trophy_groups.py  the group of PSN trophies stored before #46 (#115)
│   │   ├── description_backfill.py, rarity_backfill.py, steam_localization.py
│   │   │                         cache walkers for what polls never bring (#48, #61)
│   │   ├── reminders.py          reminders for a dead Xbox login
│   │   ├── message_cleanup.py    auto-deletes system messages
│   │   ├── online_refresh.py, admin_refresh.py   self-refreshing /online and /admin
│   │   └── service_health.py     liveness of the shared credentials
│   │
│   ├── web/                     oauth.py (OAuth callback + Mini API mount), mini_api.py (JSON,
│   │                            Init Data auth), mini_auth.py, mini_me.py, mini_chat.py,
│   │                            mini_admin.py (secrets never leave it), mini_hltb.py, mini_avatars.py,
│   │                            mini_session.py (the cookie), mini_logins.py (email, the logins kept),
│   │                            mini_notifications.py (the list, push subscriptions),
│                            mini_invites.py (signing up with an invite, a member's codes),
│                            mini_passkeys.py (adding, listing, signing in with passkeys)
│   │
│   └── db/
│       ├── schema.sql            full DDL for a brand-new database
│       ├── repo/                 all data access, the only place with SQL; one Repo from mixins
│       │                         (map in its __init__.py); `_sql.py` holds the shared joins (#52)
│       └── migrations/           one file per schema change, for existing databases only
│
├── scripts/                     one-off operational helpers, outside the running bot
│   ├── render_screen.py          draws any screen, prints it or sends it to the owner's DM (#63)
│   ├── check_integrity.py        stored achievements vs what each platform reports, read-only (#120)
│   ├── collect_game.py           collect one game from the stores now (#147), beside a running bot
│   ├── catalog_viewer.py         a bare local, read-only viewer of the games' store side (#147)
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

Required environment variables: `BOT_TOKEN`, `SUPERADMIN_TG_IDS` (comma-separated
super-admins), `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET`, `OAUTH_REDIRECT_URL`
(public HTTPS — Microsoft rejects `http://` and `localhost`), `FERNET_KEY`.

Optional: `STEAM_API_KEY`, `ANTHROPIC_API_KEY`, `YOUTUBE_API_KEY`, `OAUTH_LISTEN_HOST` /
`OAUTH_LISTEN_PORT`, `DB_PATH`, `LOG_LEVEL`, `MINI_APP_URL` (empty disables the Mini
App entry points), the poller interval settings, and the mail server for email sign-in
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

The canonical schema is `bot/db/schema.sql`; this section describes the model, not
every column. History: #106.

### Bring-up and migrations

- **`schema.sql` runs on every start; migrations bring an *existing* database up to
  it.** A brand-new database is **baselined** — its migrations are recorded as
  applied without running — so a migration only has to work against the schema it
  was written for. The test is "was the file empty before schema.sql ran", not
  "does `schema_migrations` exist".
- **A migration adding a column schema.sql already created is not an error**:
  `_apply_one` leaves that `ADD COLUMN` out of the script before it runs, and logs
  it (#167 — swallowing the error used to skip the rest of the migration). A
  database skipping versions meets both halves of the bring-up at once. Indexes on
  columns a migration added are `_database.py::INDEXES_AFTER_MIGRATIONS`, made after
  the migrations on every start, since a new database is baselined.
- **A failed bring-up stops the process.** `connect()` closes the connection before
  re-raising; an open aiosqlite connection keeps a non-daemon thread alive and the
  bot neither serves nor exits. The same holds for anything later in `run()`
  before polling starts: `main()` ends a run that raised with `os._exit(1)`, so
  systemd (`Restart=on-failure`) starts it again, and `bot.me()` at start-up is
  retried for ~2 minutes because Telegram is sometimes briefly unreachable.
- **A database ahead of the code refuses to start** (`SchemaTooNewError`, #56) —
  that is how an older build learns a newer one already migrated its file.
- **Rehearse a migration on a copy of production before the release that carries
  it** — copy with `sqlite3`'s `backup()`, run the real `Database.connect()`, count
  rows on both sides. Production's particular history breaks migrations no test can.

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
  **A super-admin stays an ordinary person named by `SUPERADMIN_TG_IDS`** (owner,
  2026-10-02): no role field. So a super-admin must always keep a Telegram id —
  nothing (removing Telegram, a merge) may leave them without one; both refuse
  with `admin`.
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
  spoiler. `trophy_type` is the PSN tier; `trophy_group_id` is the PSN group
  (`default`, `001`…), `NULL` elsewhere and on PSN rows stored before #46 — which is
  how the poller knows a game's DLC trophies were never fetched.
- **`device` — what an achievement was earned on — is a fact or `NULL`, never a
  guess** (#79; owner, 2026-09-24; migration 059). Its sources: Xbox presence while
  that game is being played (the exit poll uses the device presence last reported);
  PSN presence while the person is online, on a game released on several
  platforms; otherwise `NULL` — a single-platform game needs none, its version is
  known from the game (#114). Steam stays `NULL` (PC or Steam Deck cannot be told
  apart). Presence codenames (`Scarlett`, `Durango`, `Web`, `PS5`) —
  `services/platform_format.py` normalizes them.
- **A game's platforms (`titles.platforms`) are what it was released on** — from
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
- **Anti-flood state**: `notification_throttle (person_id, chat_id, window_started_at,
  count_in_window, throttled)`. No buffer table — a held-back achievement is exactly
  one missing from `publications` for that chat, which `unpublished_achievements()`
  finds.

### Games, caches and pictures

- **Presence**: `presence_state` (Xbox), `steam_presence_state`, `psn_presence_state`
  (#1, unrelated to the trophy scan). PSN scan progress: `psn_title_progress`,
  `psn_poll_state`. Xbox history: `title_history`. Steam: `steam_schema_cache`,
  `steam_rarity_cache`. HLTB: `hltb_cache`. Steam guides and patches: `steam_apps`,
  `game_patches`, `title_guide_reads` (see Steam guides and patches).
- **`titles`** — one row per version (one achievement list on one platform),
  **keyed by `(platform, title_id)`** like `seen_achievements` and
  `title_achievements` (#147, migration 090): Steam appids and Xbox title ids
  overlap. Join on both (`_sql.titles_on`). An Xbox id is one game, so a
  lookup by any Xbox value matches either generation (`_sql.platform_is`,
  which also takes `xbox` for a caller that only knows the family, as
  presence does); a game found to be the other generation moves, row,
  achievements and catalog together (`update_title_platform` /
  `_move_title_rows`), and a 360 game stays 360 (`stored_xbox_generation`).
  `title_guide_reads` is keyed the same way; `title_groups` stays by id (PSN
  only). No foreign keys point at `titles`. Its columns: names (`name`, `name_ru`, `name_en`),
  `achievements_total`, `platform`, `platforms` (#79), cover art (`icon_url` +
  `cover_path`/`cover_hash`/`cover_checked_at`), `achievements_checked_at`, and which
  HLTB entry it is (`hltb_id`/`hltb_match_score`/`hltb_attempts`/`hltb_checked_at`,
  see HowLongToBeat's own "Automatic title matching"), and which Steam app it is
  (`steam_appid`/`steam_appid_attempts`/`steam_appid_checked_at`, `tips_checked_at`).
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
    (`titles.achievements_checked_at`); those rows, and Steam's per-game response,
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
  - Icons are cached under `data/achievements/{platform}/{title_id}/`.
  - **Tips** (`tip_en`/`tip_ru`/`tip_source`/`tip_translation`): how to get it, from
    the Steam community's guides. The text sits in its own language's column; the
    other stays NULL until a translation fills it and says so (`tip_translation =
    'llm'`, like `description_source`). None are translated yet (owner, 2026-09-30).
- **What a message renders from**: `services/descriptions_view.py` swaps in the
  reader's language from the catalog per chat, falling back to the other language
  and then to `seen_achievements`' own snapshot. Rows are copied, never mutated —
  the publisher renders the same list once per chat.
- **Rarity**: see Lists and tables.
- **Pictures are downloaded, not linked** (#55): a Telegram `file_id` is useless
  without the bot token and a platform URL can break. Telegram photos
  (`users.photo_*`) and account avatars (`accounts.avatar_url/path/hash`) go to
  `data/avatars/`, covers to `data/covers/`, paths stored relative. Avatar URLs come
  from calls the bot already makes (Xbox `GameDisplayPicRaw`, Steam `avatarfull`, PSN
  `avatars`); `poller/avatars.py` re-checks each subject weekly and skips unchanged
  ones. Covers: Steam's is a fixed CDN path (`library_600x900`, portrait, else
  `header.jpg` for games older than the library view, #117), PSN's
  rides in the trophy listing, Xbox's costs a titlehub call — `poller/covers.py`
  rations three a minute and visits each title **once** (art does not change).

### The store side of a game (#147, stage 2; migration 091)

What the stores and HLTB say about a game, collected but not shown yet
(games and their links come in stage 3, the page in stage 5).

- **A version is a store product on one console** (owner, 2026-10-08):
  `versions (store, product_id, console)` — PS4 and PS5, One and Series are two
  versions even when they share one achievement list; Xbox Play Anywhere's PC is
  `also_on`, never a version. Consoles are `platform_format`'s names (+ `steam`).
  A version points at its achievement list (`platform`, `title_id`) once that is
  proved; `version_store_ids` holds every id naming it (regional CUSAs, the Xbox
  title id). `origin` is `played` or `store` (found, nobody here owns it).
- **Kinds of link** (owner, 2026-10-09, for stage 3): a port is just a version
  of another platform, however late; a remaster is a version with kind
  `remaster`; a remake is another game linked `remake_of`.
- **Sources**, one module each in `services/stores/`, network only:
  - Steam `appdetails` (no key; en + ru), each DLC named by its own request,
    `DLC_NAMES_PER_PASS` a pass, the rest in the next (due within the hour);
  - Xbox `displaycatalog`, public, found by our title id (`lookup?alternateId=
    XboxTitleId`) — no login is spent. A game does not list its add-ons: its
    editions do (`BundledSkus`); only Durables are kept. An add-on sold only
    on its own is not found this way. `9998-12-30` is "not on sale", no date;
  - PSN: the store is searched by name and a concept is accepted **only when
    Sony's trophy API says one of its title ids has our `NPWR…` list**, asked as
    an account that played it (`psn/client.trophy_lists_of`); never by name
    alone. PSN add-ons have no names without the store's GraphQL, so a PSN
    version's DLC are its trophy groups for now;
  - the HLTB page (`hltb_games`, with DLC entries and per-platform times),
    linked to every version of a matched list (`version_hltb`). `hltb_cache`
    stays for `/hltb`'s search until it is switched off.
- **When**: `StoreCollector.ensure` — after a game's first new achievement is
  published (beside the HLTB match) and when its page is opened — in the
  background, and only what is due (`fetch_state`), so many people in one game
  cost what one does. An answer is trusted 7 → 14 → 30 → 90 days while it does
  not change; a change, or a Steam patch in the last 30 days, sets it back to 7
  (a live-service game keeps being asked). A failure is retried in an hour, given
  up on for 30 days after three. **No whole-library walk** (owner, 2026-10-09).
- **Raw answers** are kept in `source_payloads`, zlib JSON, the latest only, not
  rewritten when the hash is the same — never as columns on `titles`.
- **Every achievement list is at least one version**: when no store describes it
  (a 360 game, an Xbox card the catalog dropped, a PSN list not proved) a
  stand-in (`store = 'list'`) is made from `titles`, and goes once a store
  product is found.
- **A game's year is the earliest of its versions', its developer and publisher
  the earliest version's** (owner, 2026-10-10; `game_match.game_facts`, migration
  096): a version's year is the earliest its name ("(Classic, 2005)"), its HLTB
  entry or its store gives; a version with no studio of its own (a stand-in)
  takes its HLTB entry's; demos and compilations say nothing. Refreshed after
  every linking, the matcher's or the operator's. Beside them the game keeps how
  far its versions spread (097: the latest year, other studios, other
  publishers), shown as «2006–2025», «Epic Games и другие»; companies compare
  by `game_match.company_key` ("CD PROJEKT S.A." is "CD Projekt").
- **Games** (stage 3, migration 092): `games`, `version_games (version, game,
  kind, state, source)`, `game_relations` (`remake_of`). After every collection
  `services/game_link.py` re-links the versions around that list
  (`services/game_match.py`, no DB access): **a weighted model** (owner,
  2026-10-10: every rule a weight, nothing certain) — each pair's signs (one
  achievement list, a store's own group, one HLTB entry, name similarity, a
  sequel's number, achievements' names shared, studio, years, a demo of it) add
  their `WEIGHTS` to the log-odds; the probability links at `LINK_P` (0.85) and
  sends to the **review list** from `REVIEW_P` (0.15; one row per version, on the
  side less is known about). The weights are to be fitted to the operator's
  decisions; the viewer's «rules» page shows them. The matcher rewrites only its
  own (`auto`) rows: a `manual` link stays and a `manual` rejection keeps a
  version out of that game. **Disputed pairs are the operator's** (owner,
  2026-10-09; Haiku may advise one day, not decide).
- By hand: `scripts/collect_game.py <platform> <title_id> [--force]`; to look and
  decide: `scripts/catalog_viewer.py` (bare HTML; games, the review list with
  its answers, merge / detach / rename, collect, re-link). **No authentication
  yet** (#186).

### Secrets

`tokens` stores encrypted Xbox refresh tokens only (access/XSTS tokens stay in
memory); status is active / invalid / revoked. Shared credentials (PSN NPSSO, Steam
key, Anthropic key, YouTube key) are encrypted in `app_settings`.

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
- **Xbox 360 history comes from the achievements service's own lists** (#91, #92):
  contract 1 `/achievements` with no titleId gives every 360 unlock page by page, and
  `/history/titles` every 360 game with its name and total. Titlehub forgets games not
  played for a while; these do not. Backfill uses them (game by game through titlehub
  only if refused), and linked accounts are topped up once at startup
  (`Fetcher.fill_x360_gaps_once`, marked in `app_settings`). A forgotten game's total
  on `titles.achievements_total` is what lets a finished one count as 🌀.
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
subscribed there; not admin-excluded; the account's posting switch is on (#20); the
person's `rarity_mode` isn't `hidden`; in
`rare` mode a
known rarity is at or below the rarity threshold (a platform with no rarity at all —
Xbox 360 — is exempt, not hidden); the game
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
    chosen picture first, with an ETag and `no-cache` so a change shows at once.
  - Endpoints: `PUT /api/mini/me/handle` (`error` is `invalid` or `too_soon`),
    `POST /api/mini/me/handle/confirm`; `/me` carries a `handle` object.
- **Follows, as on Xbox** (backend shipped, migration 073): following is one-way and
  needs no consent; following each other makes two people friends — friends are
  not stored, they are two rows in `follows`. A person can unfollow and block someone; a follower is never removed by the
  one followed (owner, 2026-10-02) — blocking is the way to end it (a block deletes the follows between the two and hides each from
  the other's search and lists; the blocked one cannot follow). Search is by
  nickname only: a prefix of 3+ characters, or an exact `Name#1234`, 20 results.
  People from a shared chat (subscribed or seen writing) are suggested, and friends of friends above them — «Вы можете знать», people followed by those you follow, the most shared first (`repo.people_you_may_know`, `/api/mini/people/may-know`). A new
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
- **The Mini App's dock** (shipped): Home · Feed · People · Settings. The statistics
  became "Рейтинг" beside the feed (a `Достижения | Новости | Рейтинг` switch in the page head — the feed is «Достижения», game news «Новости»; one
  dock tab; the `summary` screen name and `?t=summary` links still work).
  **Scope** (owner, 2026-10-02): there is no chat picker — the Feed, the Ranking, Home's
  strip of people and `/club/online` are always about oneself plus the followed people
  whose privacy lets the viewer see them (`?scope=following`, answered by the same
  queries through `_sql.member_source`, a list of people standing in for
  `subscriptions`, chat id 0). Chats only help to find people to follow. The dock's third tab is «Поиск» (owner, 2026-10-02): games (HowLongToBeat, from two letters) and people (by nickname, from three); with an empty query, following / followers / shared-chat suggestions. Home's empty friends block is a dashed circle with a plus, the size of a face, that opens it with the field focused (owner, 2026-10-08); no platform marks beside a nickname in Home's head or a profile's — the accounts are a tap away on the card. In the Feed, tapping an author opens their profile; a profile's nickname, and one's own avatar on Home, open the card (`PersonSheet`, `/api/mini/people/{id}`) — one's own without the follow button and counts. On a card the counts open that person's following / followers, and a profile shows whom they follow as Home does (`/api/mini/people/{id}/following|followers`, only to a viewer `can_view_activity` lets in). The digits of a nickname read quieter (`HandleName`). The Feed / Ranking switch is the page title as a dropdown, and every pick-one-of-a-list control is the shared `Dropdown` (`components/shared/lib/dropdown`), never a native select. A person with no linked account sees a «Подключи аккаунт» card; no chat is needed to use the app. The People tab (`webapp/src/screens/people`) has search by
  nickname, following, followers and shared-chat suggestions, a follow button on each
  row and a person sheet (remove follower, block).
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
    On the sign-in screen, once a code went out only the code is on the screen
    («Введи код из письма») — not the address step's text nor Telegram's widget;
    the forms are `noValidate`, so a bad address is worded by the app, never by
    the browser's bubble.
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
  - **In the Mini App** one form does both jobs: `components/me/logins/EmailCodeForm`
    (address, then the code, which sends itself on the sixth digit; a resend
    countdown; errors worded from the codes above) on the sign-in screen and in
    Settings → «Вход» (`LoginsPane`); the Login Widget is `shared/lib/telegram-login`.
    A person without Telegram sees Publishing's chats replaced by «привяжи Telegram».
    A first nickname for such a person comes from the part of the address before
    the @. `ApiError` keeps a refusal's `error` and body for the screens.
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
    read, and none from an app's first read (its history). **A tap opens the
    post itself** (owner, 2026-10-08): the notice keeps its `appid` and `gid`,
    the list hands them on as `news`, a push's link carries `n=appid:gid`, and
    `GET /api/mini/club/news/post?appid=&gid=[&title_id=]` gives the post (and
    the game's name and picture for its head); the post's page opens on its own
    (`NewsPostLoader`), its game a tap on its head — never the game page under
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
    any host, an internal one included. Push needs `MINI_APP_URL` (where a tap opens) and a
    contact for the push services (`SMTP_FROM`, else the app's https address).
  - Routes: `GET /api/mini/notifications`, `POST …/read`; `GET /api/mini/push/key`,
    `POST|DELETE /api/mini/push/subscription`; the switches through
    `PATCH /api/mini/settings`; `/me` carries `notifications_unread`.
  - **In the Mini App**: a bell on Home with the unread count opens the list. A
    notice is read once tapped (`POST …/read` with `ids`), or all at once by
    «Прочитать все» (no `ids`). A tap opens what it is about: a new post's game
    on the author's progress (`game` in the list, `g=` beside `p=` in a push's
    URL — `Kind.game`), else the person. A row is drawn as an activity feed's (owner, 2026-10-06;
    `listed()` gives `bold`, `lead`, `detail`, `image`): grouped by day; a face —
    the person's, or the game's cover for its news — with a coloured mark of
    what it is about (cup, people, a handshake for a friend, news); one line, «**Anastasiafil** получает
    «…» и ещё 2» or «**Gears of War: E-Day** — новый патч»; under it the game or the post; how long ago at the right. Unread rows are in full light with a small
    accent dot left of the face; read ones step back. The list scrolls inside the
    sheet. A friend's face carries no mark of its own (owner, 2026-10-08:
    marks on every face cluttered the lists); friends only come first in the
    strips and lists, and the handshake marks a «new friend» notice.
    Settings → «Уведомления» (owner, 2026-10-06): two blocks with the same rows,
    «Пуши» (this device's switch: subscribed or not) and «Telegram» (its switch;
    the block is there only with Telegram linked); under a switch that is on —
    «Новые посты» (off / friends / everyone followed), new followers, new
    friends, «Новости игр» (off / all / patches / news), and for push the Xbox
    sign-in (its Telegram message is `poller/reminders.py`'s, with the button).
    Stored as tokens, `new_post:friends`, `game_news:patch`
    (`notifier.carries`); 081's `notify_posts` is no longer read. A hint under a setting
    is its row's second line, never a note under the group, unless it is about a
    choice among the group's rows. `components/me/notifications/push.ts` says why a
    device cannot get pushes, each worded: inside Telegram (the bot's DMs are the
    notices there), an iPhone page not on the Home Screen (Safari pushes only
    then), a browser without push, push not set up on the server, or blocked in
    the browser.
  - **The app is installable** (a PWA): `webapp/public/manifest.webmanifest` and
    `sw.js`. The service worker only shows pushes and opens the app on a tap — **no
    offline cache**, so a deploy is never hidden behind an old copy. It is
    registered only outside Telegram. Paths are relative or `BASE_URL`, since
    production serves the app under `/app/`. A browser that can install it gets
    a banner above the dock (`shared/lib/install-prompt`): Chromium's own install
    dialog behind «Установить» (`beforeinstallprompt`, caught at start-up in
    `main.tsx`), on an iPhone the Share → Add to Home Screen steps. Never inside
    Telegram or once installed; closed, it rests 14 days (`localStorage`).
- **Settings, top to bottom** (owner, 2026-10-05): the home is rows that open
  screens and nothing else — a switch or a picker lives one screen in. Each row
  starts with its glyph (`RowGlyph`, bare, no tile; the profile row with the
  face) and says in its second line what is inside. The profile card opens
  «Профиль» — «Как видят другие», «Вход», «Приватность», the game accounts, then
  «Выйти» / «Удалить аккаунт»; then «Посты в чатах» (what of yours goes to the
  chats — named so, not «Публикация», to tell it from what is sent to you),
  «Уведомления», «Общие» (language, timezone, secret achievements); the admin's
  screens, the API load on «Ключи» beside the keys; «Пригласить друга» last. Inside a screen, a row
  shows its current choice on the right where there is one. Back from a
  profile screen is the profile; back from connecting an account opens it too
  (its notes are there). The follows page also lists the people one blocked.
- **The phone's "back" steps back inside the app** (owner, 2026-10-05;
  `shared/lib/back-stack`): Android's back in the installed app, and Telegram's
  header button (`BackButton`) inside Telegram, close the topmost open layer —
  a screen with a back arrow (`BackHead`), a sheet, the game page, a person's
  page, then any tab back to Home — and only then leave. Each layer calls
  `useBackHandler`; a new layer that reuses a component (one arrow, another
  title) passes `layer` so it counts as new. The history holds **one entry per open
  layer, pushed when it opens** — never after a back: Chrome lets back skip an
  entry added without the user's gesture, and a re-armed one closed the app on
  the second back. Changes are reconciled once a moment's layers settle (a
  layer closing as another opens is no step at all), and nothing is pushed
  while a step back of our own is on its way. A new screen with its own way out registers too.
- **A reload comes back where it was** (owner, 2026-10-06; `App.tsx::PLACE_KEY`):
  the screen, the person and the game open are kept in `sessionStorage` for the
  tab's session, and a reload with no link of its own (`c`, `p`, `u`, `t`, `g`,
  a start parameter) opens them again instead of Home. A link always wins;
  connecting an account starts over at Home.
- **Settings and admin screens share one vocabulary** (owner, 2026-10-02):
  `webapp/src/components/shared/lib/form-rows` — `Group` (title, rows, hint), `NavRow`,
  `InfoRow`, `ToggleRow`, `ChoiceRow` (2–3 short options), `SelectRow` (many),
  `NumberRow`, `CheckRow`, `RowLink`, and `SettingsSkel` while loading. A screen
  composes these and never styles a row of its own; destructive actions are red rows in
  a last group of their own. The Mini App's admin draws its settings from the
  server (`/api/mini/admin/settings`, `/api/mini/admin/chats/{id}/settings`;
  `components/admin/admin-settings-form`): a number with its bounds, a switch,
  a pick from a list — never a list of settings of its own.
- **Actions look one way each** (owner, 2026-10-02; `components/shared/styles/base.css`):
  `.btn` is a pill without an outline — the action ("Подписаться", "Подключить");
  `.btn.is-quiet` is the paler pill of a state that opens choices ("Друзья ⌄");
  `.btn.is-wide` is a form's own action, the whole width under its field;
  `.see-all` is blue text with → for going somewhere ("Все →", "Искать →");
  `DropdownArrow` ⌄ marks anything picked from a list (dropdowns, the month), and the
  row `Chevron` → a row that opens a screen. The follow control is one component,
  `FollowButton`: follow at once, and behind "Друзья ⌄" unfollow and block.
- **One text field** (owner, 2026-10-05; `base.css`): every place one types —
  sign-in and email, the nickname (`.is-big`), a sign-in code (`.is-code`), a
  Steam/PSN link, an admin key — is `<label className="field"><input/></label>`,
  with `.field-note` under it (`.is-error` for what went wrong, and the field
  takes `.is-error` too) and a `.btn.is-wide`, stacked by `.form-stack`. Focus
  is the same everywhere: a brighter surface and an accent edge and ring — the
  search bar shares it in its pill shape, and a settings row's number
  (`.fr-number`) in miniature. A new form never styles an input of its own.
- **A finished game** (owner, 2026-10-06: beautiful but laconic, a real joy;
  `game/game-hero/GameHero`): a platinum medal on the picture's lower edge — a
  metal disc, an iridescent rim turning slowly, a breathing glow, stars twinkling round it, «Пройдено на
  100%» and the day the last achievement came — at rest and open alike, no rays.
  The first time one opens one's own finished game, the medal pops in with a ring
  of sparks and a tap of the phone, once per game on the device
  (`localStorage` `celebrated-games`).
  A game not finished wears the same medal, quieter (owner, 2026-10-06): a dark
  disc, its rim filled clockwise as far as the person got — white, as the
  progress bars in the lists —, and
  the percentage and the day of the last achievement under it (how many is in the tab's title) — the bar plate it replaced is gone. Its own effects, not
  the platinum's: the rim fills from nothing as the page opens (`@property --p`),
  a bright point pulses at the arc's end, and the picture dims round it.
- **The ranking** (owner, 2026-10-07): one table, no frames, a column each — the last day, the month shown
  and its year (`/club/summary`'s `year`, from 1 January to the month's end, in
  the same timezone), and the leaders by day / month / year from a dropdown.
  «Охотятся вместе» lists each achievement once, with the faces of everybody
  who earned it (as the game page's compare), the most shared first; its page is
  titled «Охотятся вместе», the game under the head.
- **No drawers: pages** (owner, 2026-10-07; `shared/lib/sheet/Sheet`): what rose
  from the bottom as a drawer — notifications, a person's card, follows, the
  month's games, a ranking's lists, an achievement, an HLTB game, the merge — is
  a page over everything, sliding in from the side, with its own scroll and a
  head with the way back (the arrow, the phone's back); `title` (or `head`) and
  `aside` name it in the head. A person's page has the person in its head — face,
  nickname, where they are — and the follow control at its right; a lone
  game account is open, several start closed. The follows page names its list in the head and picks it at the
  right (following / friends / followers / blocked, each with its count), and
  searches the list shown by nickname under the head. A pick from a short list is the `Dropdown`, never a page: the
  month, the ranking's day / month. The day to jump to in a feed is the month's
  calendar unfolding under the day's label, the screen's width
  (`person/day-jump/DayCalendar`: days with posts enabled, with their counts).
  The feed's posts are built as the reader nears the end (`FeedPosts`, eight
  at a time, 2000px ahead), never a whole month at once — a phone's browser
  dropped the page; a jump to a day builds up to it first. An HLTB game from
  search is laid out as a post's page (`hltb/game-sheet/GameSheet`): the
  picture edge to edge, year and platform, the name, the three times as one
  table, the story, «Открыть на HowLongToBeat».
- **Design**: every new screen follows the Mini App as it is — its tokens, glass
  surfaces and spacing, no extra outlines.

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
- **Timezones**: the eight offsets this community lives in, "Другой ▸" for the full
  −12…+14 grid, "✏️ Ввести вручную" for one typed offset (`+3`, `+5:30`). Offsets,
  never zone names.
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
  unlink, and for PSN every account (up to three) plus adding one. The panel's switch
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
  the query. It quotes the first lines of what it deleted, and that confirmation is a
  system message the cleanup job removes later.

### Admin

- **Two roles, named distinctly** (owner, 2026-10-07): the **суперадмин**
  (super-admin) is the global operator — `SUPERADMIN_TG_IDS`, any number of them,
  `Settings.is_superadmin`; the old name `ADMIN_TG_IDS` is still read. **«Админ»
  is reserved for a narrower role to come** (the per-chat one #15 proposes), so
  code, text and docs never call the super-admin an admin. `/admin`, the
  `/api/mini/admin` routes and `handlers/admin.py` name the panel, not the role.
- **One source for both admin panels** (#176; owner, 2026-10-08: a new admin
  setting appears in the bot and the Mini App at once). Both only render what
  these services answer:
  - `services/admin_registry.py` — **every setting**, global and per chat, one
    row each: where it lives, its kind (number, decimal, on/off, one of a list,
    an hour, a UTC offset), bounds or choices, group, label, hint. `set_value` is
    the one way either panel changes one — parsed, bounded, stored; a bad value
    is refused the same from a typed message and from JSON. Time zones are the
    38 real UTC offsets (`REAL_UTC_OFFSETS_MIN`), summaries go out on the hour;
    the Mini App names a city beside an offset where one is known («Москва ·
    UTC+3», `value_label(place=True)`), the bot shows the offset alone.
  - `services/admin_status.py` — the home (`AdminStatus`: counts, API usage,
    sign-in emails against their caps, every credential's state).
  - `services/admin_credentials.py` — the shared credentials (`set` raising
    `CredentialInvalid` / `CredentialSetupError`, `clear`).
  - `services/admin_actions.py` — **every action**, one class each: what it
    is about (a person, one game account, a chat), its label, whether it is
    dangerous, how many confirmations it takes and their words, what it does.
    `available` lists a card's actions; `perform` takes one a step at a time —
    `Confirm` (the words, the "yes", the next step) until the last step, then
    `Done`. The bot draws a confirmation as a screen («Да / Отмена»,
    `a:x:<scope>:<target>:<action>:<step>`), the Mini App as a dialog
    (`GET|POST /api/mini/admin/actions`, `components/admin/admin-actions`); the
    steps and the words are the server's. Today: exclude / restore, refresh and
    reset an account (reset asks once, naming it), take a chosen picture down,
    delete a person (asks twice); on a chat, the promo (asks once), delete the
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
  `components/admin/admin-settings-form` — and from then on every setting of
  that kind appears in both panels by itself.
- **`/admin`** (private, self-refreshing): credential health; "🔑 Ключи платформ" to
  set / change / clear the Steam key, PSN NPSSO, Anthropic and YouTube keys and the
  mail login (#17) — a key is
  **never shown back**, and entering one is a single-message state with only a way
  out; API usage; «⚙️ Настройки» — the registry's global groups (Правила: the
  rarity threshold, the digest size, profile links · Новые пользователи: the
  mode they start with · Списки · HLTB · Таймеры · Почта · Прочее), `0` worded
  by what it means; the user list; the chat list and
  per-chat cards; exclusion; bot-message cleanup.
- **The per-chat card** opens the registry's chat groups — Основное (on, language,
  time zone) · Итоги дня (on, the hour) · Антифлуд (limit, window) — and «Сообщения» (the wipes), each redrawing in place
  with the card's text above. There is no minimum gamerscore
  (owner, 2026-10-08: it held back every Steam and PSN achievement; the column
  `chat_settings.min_gamerscore` is left unread).
- **The per-user card**: the person (chain 1) and their id, then **every way they
  sign in** (owner, 2026-10-07; `services/logins.py`, the same list the Mini App's
  admin card shows): Telegram (`@username`, its id passed to Fluent as a string,
  never `@N`), email — each linked or "— нет"; a new way in is one more entry
  there. Then one block per platform in the display order — nickname,
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
- **Game line**, italic: game, the version played (below), and the person's progress `47/50` when the
  total is known (#46). Totals: Xbox 360 from `title_history`; modern Xbox from
  titlehub or, when titlehub says 0, the size of the per-title response stored in
  `titles.achievements_total` (Microsoft's count wins where it exists); Steam from the
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
  `sendMediaGroup`, caption on the first image, images deduped.
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
| the admin's user list | listing (plain) **and** inline | `repo.admin_users()` | anyone with a platform linked | `is_excluded` ↑, `last_online_at` ↓ | `PAGE_SIZE`, `◀️ N/M ▶️` |
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
  contract 4, so the contract-2 history is filled by `poller/rarity_backfill.py` (and
  `scripts/backfill_rarity.py`, bot stopped) — one request per title covers every
  owner. Every platform's poll also writes it. Nothing expires: a year-old
  percentage is worth more than none. Xbox 360 has no rarity: no 💎 there, and `rare` mode
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
- **The same page read also keeps the rest of it** (`hltb_cache.details`, one
  JSON object, migration 064): rating, developer/publisher, alias, release dates,
  play modes, co-op/multiplayer hours, each time bucket's median/fastest/slowest,
  speedrun records. The "Об игре" tab shows a table of genre, release, publisher,
  developer, modes, score and the average hours; the alias, the spreads and the
  speedruns are kept in `details` but not shown (owner, 2026-09-29). **HLTB's counts
  of its own users** (completed, playing, backlog, retired) **are left out on
  purpose** (owner, 2026-09-29): they describe HLTB's audience, not the game. A
  row cached before 064 reads the page once more on its next lookup.
- HLTB is English-only, so the Russian side is always Haiku's
  (`hltb_cache.description_ru`), **lazily** — once per game, the first time someone
  looks it up. No Anthropic key: the English text is shown.
- The card shows it as a collapsed blockquote capped at `DESCRIPTION_LIMIT` — the card
  is usually a photo caption (1024 characters).

### Automatic title matching

**Every game gets its HLTB entry matched for it, without a person ever searching**
(`bot/services/hltb_match.py`, `titles.hltb_id`/`hltb_match_score`) — the Mini App's
game page shows HLTB's hours and description straight away. `/hltb` above is
unrelated: it stays a person picking from a candidate list, cached by the id they
picked.

- **A match is asked for lazily, never by a walker**: once from each platform's
  fetcher, right after it publishes a game's *first* new achievement
  (`services.hltb.ensure_title_match`, called from `poller/fetcher.py`,
  `poller/steam_fetcher.py`, `poller/psn_fetcher.py`), and again from the Mini App's
  game-details endpoint if a game still has no match when somebody opens its page —
  an old game nobody's played lately gets matched the first time anybody actually
  looks at it, not before. **Backfill never triggers it** (backfill never publishes),
  so a freshly connected account's whole library costs nothing up front; the requests
  land one at a time, spread across whenever people actually earn something or open a
  game page, never as a burst. Both call sites end up at the same one-row check
  (`titles.hltb_id IS NULL AND hltb_attempts < 3`, re-askable an hour apart) — a
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
guides, and the developer's patch notes in an "Обновления" tab. Nothing of it is
sent to a chat.

- **Which Steam app a game is** (`titles.steam_appid`): a Steam game's own `title_id`;
  otherwise found once, like its HLTB entry — the appid HLTB's page lists (exact),
  else Steam's store search by name (`steam_news.pick_appid`, a confident match only:
  store "apps" include a game's DLC and sets). Three failed attempts an hour apart,
  then known to have none. Console exclusives have none, so no tips and no tab.
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
  picture (`webapp/src/components/game/rich-text/RichText.tsx`).
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
  picture (migration 084): a patch is a post tagged `patchnotes` or titled like one
  (update, patch, hotfix, a version number; not a demo or playtest), anything else
  is news. A post keeps its time, not only its day (migration 085: `published_at` is `…T14:32:00Z`, shown in the reader's own time). The game page's «Обновления» shows both, with a filter at the tab's right (all / news / patches); **«Новости»** (owner,
  2026-10-05; `repo.games_news`, `GET /api/mini/club/news?scope=following&month=`)
  shows both, untranslated, for the games the viewer and the people they follow
  earned something in within 60 days before the month's end, newest first, one
  card per post however many of our games are that Steam app, laid out as the
  achievements' posts are (days; the game's face and name where a post has its
  author; the picture edge to edge, all of it seen; the text on frosted glass).
  A post opens whole on a page of its own over everything, the game page too
  (`components/game/news-page/NewsPage`: its own scroll and back; the picture,
  the game, the day, the title, the full text with its pictures, videos and
  links, then «Открыть в Steam»); a patch in a game's «Обновления» opens on the
  same page. Its game opens the game.
- **An achievement has a page of its own** (owner, 2026-10-05;
  `components/game/achievement-page/AchievementPage`, on the same layout as a
  post's page, `components/game/post-page/PostPage.css`): a row on the game page
  opens it (a secret one is revealed first). The game in the head, its rarity and
  points (or trophy) at the head's right, as the game page shows its score; the
  picture whole; when it was earned; its name and description; then «Как
  получить», the Steam guides' tip whole, when there is one — a row with a tip
  carries the book mark. A post's page keeps the head for the game alone: its kind
  («Патч», «Новость») sits at the right of the date line, as in the list of
  updates (owner, 2026-10-06).
- **A picture opens in the app, full screen** (owner, 2026-10-05;
  `shared/lib/image-viewer`: `openImage(src)`, one `ImageViewerHost` in the app
  shell): the pictures in a guide's tip, a post or a patch, the picture at the top
  of a post's or an achievement's page, and a face that zooms. Never on Steam. As
  large as the screen allows, all of it; two fingers zoom and move it, a double
  tap zooms in or back; a tap at its own size or the phone's back closes it —
  nothing is drawn over the picture. The feeds keep their taps (a post opens its game or its page).
- **A post's frame is its picture's shape** (owner, 2026-10-05; both feeds,
  `shared/lib/img-ratio`): proportions read when the picture loads and
  remembered (`localStorage`), kept between 4:5 and 1.91:1; beyond that the
  picture is whole over its blurred copy. A picture wider than a square
  (`isWide`) is its own height, edge to edge, and the text comes under it
  instead of over it; a square or a tall one keeps the text over its foot. A
  feed's frame is never wider than 1.15:1 (`FEED_RATIO_MAX`): a wider picture
  keeps its whole height and loses a little of its sides. A post of several
  achievements takes the first one's shape for every slide. Console exclusives have no Steam
  app and so no news. Re-read by `poller/patch_refresh.py` for games somebody
  earned something in over the last 30 days, every `patch_refresh_hours` (6,
  /admin), three apps a tick.

### Video guides from YouTube

Guide videos for an achievement, shown on its page in «Как получить» (owner,
2026-10-06). Today one channel, TrophyTom (`services/youtube/guides.py::CHANNELS`).

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
  please 🏆 Trophy / Achievement Guide"); a description's timeline names moments
  ("02:42 – ACHIEVEMENT – Chainsaw Go…", "– TROPHY – … – PART 2", or a bare name in a
  whole-game video). Every timeline line is kept; collectibles and chapters match
  nothing and never show.
- **Matched on reading, exactly** (`services/youtube/videos.py`): a video is a
  game's when its title's first part(s) — split at " - ", normalized as HLTB's
  matcher does — are one of the game's names or their edition-cut cores, so
  "Gears of War 2 - …" is never Gears of War's; a moment is an achievement's when
  its label equals the achievement's English name, normalized. Nothing is guessed:
  a near miss shows nothing. The newest three per achievement, parts in order.
- `/guides` answers them as `videos` beside `tips`; a row with a tip carries the
  book mark, one with a video the video mark beside it.
- **The game's own guide** (`videos.py::game_guide`, `guide` in `/guides`): what is
  matched to one achievement rarely covers them all, so a game the channel has
  videos of gets a video button in the game page's head — its whole-game video
  when one is titled so ("Full Game", "All Achievements"), else the channel's
  search for the game. Never on the picture: that is the game's own (a gallery
  later).

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
  links never 404.
- **A release is: notes, a short review, then `prerelease` → `main`** (owner,
  2026-09-25). A contributor's pull request targets `prerelease`, never `main`: #129
  merged into `main` deployed at once, and production announced a version with no
  notes behind its link.
- **A release that starts a new minor** bumps `TRUNK_LINE` on `prerelease`, and the
  merge into `main` is made locally, tagged `vX.Y.0`, and pushed **tag first, then
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
- **Back up with `sqlite3`'s `backup()`, never `cp`** — the databases run in WAL mode.
  Name copies for what and when: `bot-pre042-20260915-084500.db`.

## Engineering rules

History: #112.

- Handlers are thin — services and repo methods, never raw SQL or platform logic.
- All SQL lives in `bot/db/repo/`, `schema.sql` and the migrations.
- **Writes that must land together go in `async with self.transaction()`** (#167,
  `db/repo/_tx.py`). The bot has one connection: a transaction is the
  connection's, so one coroutine's `commit()` used to commit another's half-written
  work and a `rollback()` threw it away. While a block is open everybody else
  waits before their next statement, `commit()` inside it waits for its end, an
  exception rolls back only the block, and a block inside a block is a savepoint.
  Never call `rollback()` (inside a block it raises); keep network calls and file
  deletion out of a block — it holds the connection. Single statements stay as
  they were: execute, then commit.
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
  `docs/*.md` / `*.ru.md`, `changelog/<v>.ru.md` / `.en.md` and their summaries,
  and `bot/locales/ru|en/`.
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
  (Xbox 360) is exempt from `rare` instead of getting a toggle. (#20 settled it differently:
  a posting on/off switch per *account*, not a rarity mode per platform.)
- **Live platform API calls from `/stats`, the summaries, `/online` or the panel** —
  every normal read is cache-only; the panel's own sync button is the exception.
- **Game descriptions from the Steam store** — HLTB supplies them for every platform
  with no id-matching, console exclusives included (#2). The storefront is used for
  one field only: Steam's Russian game title (#61).
