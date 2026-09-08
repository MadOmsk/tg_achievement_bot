# CLAUDE.md

## Project

Achievement Bot is a Telegram bot for a small, non-commercial gaming community
(roughly 20-30 people). It publishes newly unlocked achievements and trophies from
connected Xbox, Steam, and PlayStation Network accounts, with per-chat rarity
filters, personal stats, an admin panel, daily summaries, and HowLongToBeat lookup.

This file is the single source of truth for current behavior, invariants, and open
work — read it in full before making product or architecture changes, and **keep it
current**: when a change alters something this file states (a rule, an invariant, the
file tree, a data model detail), update the relevant section in the same change, not
as a follow-up. A stale source of truth is worse than none — it gets trusted anyway.

Open work lives in the repository's [Issues](../../issues), not in a separate TODO
file. This is also where change history goes now, not just open proposals: once a
non-trivial change ships, if its own reasoning isn't already obvious from the diff,
commit messages, and this file's updated rules, archive it as a closed issue (see
#6-#13 for the shape — one per logical unit of work, closed immediately, `state_reason:
completed`). A closed issue tagged as a design log or archive is history, not
something to act on, but it's where "why did we do it this way" should be findable
five features from now. Keep the project working after every change — no step should
leave it broken.

Every rule below carries a short *why* next to the *what*, inline, not in a separate
section — the same "comment why, not what" habit this file asks of code (see Style)
applies to itself. The rejected-ideas appendix at the end is a different, narrower
thing: alternatives that were tried or considered and specifically rejected, not a
general home for design rationale.

The product is intentionally optimized for one trusted operator, a single SQLite
database, explicit admin controls, and predictable behavior, not public SaaS scale.

### Non-goals

- No public web UI. The only web endpoint is the Microsoft OAuth callback.
- No `/compare` or `/top`; `/stats`, `/summary`, `/recent`, and `/online` cover the
  useful group views.
- No global per-platform visibility toggles. Visibility is per user and per chat, and
  applies to every platform consistently — one `rarity_mode`, not one switch per
  platform.
- No live platform API calls from normal read-only commands or panels.
- No multi-tenant hosting model.

## Stack

Python 3.12+, aiogram 3, aiohttp (Microsoft OAuth callback server), httpx (platform
HTTP clients), aiosqlite, APScheduler (`AsyncIOScheduler`), pydantic v2 +
pydantic-settings, cryptography Fernet, xbox-webapi-python, the official Steam Web
API, psnawp (PSN), howlongtobeatpy, pytest + pytest-asyncio + ruff.

## Repository layout

Full tracked tree (`git ls-files`), with what each piece is for and why:

```text
.
├── .env.example                 template for environment variables; .env itself is gitignored
├── README.md                    English overview (this repo's front door)
├── README.ru.md                 the same overview, in Russian
├── CLAUDE.md                    this file
├── pyproject.toml               dependencies, ruff, pytest config
├── manage.ps1                   local Windows process manager (the bot cannot start itself)
├── manage.bat                   double-click -> manage.ps1 dashboard
│
├── bot/                         the application
│   ├── main.py                   entry point, application assembly, router registration
│   ├── config.py                 settings loaded from the environment (pydantic-settings)
│   ├── lock.py                   "one process per .env" guard (single instance)
│   ├── util.py                   small shared helpers (UTC time, secret masking)
│   ├── i18n.py                   Fluent/aiogram_i18n wiring; Russian locale is the default
│   ├── locales/                  user-facing translations, currently ru/*.ftl only
│   │
│   ├── handlers/                 aiogram routers — UI layer only, no SQL, no platform API calls
│   │   ├── connect.py             /start, /connect_xbox, /disconnect_xbox
│   │   ├── panel.py               the personal panel, "My chats"
│   │   ├── admin.py               the admin panel (/admin, self-refreshing), bulk message wipe
│   │   ├── chat.py                group commands: /subscribe, /stats, /online, /who, /recent,
│   │   │                          /summary, /delete_last, the group hub
│   │   ├── hltb.py                /hltb, HowLongToBeat lookup
│   │   ├── steam.py               /connect_steam, /disconnect_steam
│   │   ├── psn.py                 /connect_psn, /disconnect_psn
│   │   └── keyboards.py           inline keyboards + small shared helpers (format_*, safe_edit)
│   │
│   ├── services/                  business logic; knows nothing about Telegram/aiogram
│   │   ├── achievements.py         achievement filtering, message formatting, platform_tag
│   │   ├── connect.py              one-time OAuth state, finishing a login
│   │   ├── stats.py                aggregates for the panels, /stats, the daily summary
│   │   ├── models.py               ParsedAchievement/Platform, shared by Xbox/Steam/PSN
│   │   ├── tables.py               shared blockquote-list table renderer
│   │   ├── profile_links.py        one profile-URL builder per platform, gated by
│   │   │                           user_settings.show_profile_links
│   │   ├── hltb.py                 wrapper over howlongtobeatpy, cached in hltb_cache
│   │   ├── message_log.py          request middleware: logs outgoing group messages
│   │   ├── online_view.py          renders the /online table, shared by the command and auto-refresh
│   │   ├── admin_view.py           renders /admin, shared by the command and auto-refresh
│   │   ├── single_message.py       delete-then-send for /panel, /summary, /recent, a person's /stats
│   │   ├── notify.py               notifications to the admin
│   │   ├── crypto.py               refresh-token encryption (Fernet)
│   │   ├── rate_limiter.py         shared sliding-window limiter (Xbox and Steam clients)
│   │   ├── xbox/                   everything about Xbox Live; nothing about Telegram
│   │   │   ├── auth.py              wrapper over xbox-webapi-python: token storage, refresh
│   │   │   ├── client.py            Xbox Live requests, rate limiting, retry, backoff
│   │   │   └── models.py            pydantic response models (incl. rarity from contract 4)
│   │   ├── rows.py                 ParsedAchievement -> AchievementRow, shared by both pollers and psn/achievements.py
│   │   ├── steam/                  the official Steam Web API, no OAuth (one shared key)
│   │   │   ├── client.py            profile resolve, visibility, presence, achievements, rarity
│   │   │   ├── auth.py              SteamAuth: the admin-settable API key (encrypted in app_settings), health check (#17)
│   │   │   └── achievements.py      fetch_unlocked() + schema/rarity cache
│   │   └── psn/                    psnawp, one shared service-wide NPSSO for the whole bot
│   │       ├── client.py            async wrapper (asyncio.to_thread), resolve, trophies
│   │       ├── auth.py              NPSSO storage/refresh, health check, PsnAuth
│   │       ├── achievements.py      sync_account(): scan + persist trophies + progress cache, one game at a time (#26)
│   │       └── view.py              a standalone PSN trophy table, ahead of merging into /stats
│   │
│   ├── poller/                    scheduled background jobs (APScheduler)
│   │   ├── scheduler.py            ticks, job assembly
│   │   ├── cadence.py              shared interval/debounce math for both presence pollers
│   │   ├── presence.py             step 1: Xbox presence, interval by state
│   │   ├── steam_presence.py       Steam presence, same step 1, its own batch request
│   │   ├── fetcher.py              step 2: Xbox achievements per game, title history, backfill
│   │   ├── steam_fetcher.py        step 2: Steam achievements per game, backfill on link
│   │   ├── psn_fetcher.py          PSN trophies: no presence hook, its own debounce, backfill, admin resync (#27)
│   │   ├── publisher.py            step 3: publication, digest, the Telegram send queue
│   │   ├── daily.py                the scheduled daily summary + /summary on demand
│   │   ├── reminders.py            reminders for a dead Xbox login
│   │   ├── message_cleanup.py      auto-deletes system messages in groups
│   │   ├── online_refresh.py       auto-refreshes the /online table
│   │   ├── service_health.py       liveness of the shared Steam/PSN keys, notifies the admin
│   │   └── admin_refresh.py        auto-refreshes /admin, same cadence as service_health
│   │
│   ├── web/
│   │   └── oauth.py                 Microsoft's aiohttp OAuth callback
│   │
│   └── db/
│       ├── schema.sql               full DDL for a brand-new database
│       ├── repo.py                  every piece of data access; the only place with SQL
│       └── migrations/              one file per schema change, applied in order
│
├── scripts/                     operational one-off helpers, outside the running application
│   ├── db_status.py               summary for `manage.ps1 status` (no dependencies)
│   ├── reconcile_achievements.py  one-off full achievement-history backfill
│   ├── backfill_hltb_platforms.py one-off: fill in `platforms` on already-cached games
│   └── backfill_steam_titles.py   one-off: fill in `titles` for already-stored Steam achievements
│
├── tests/                       pytest + pytest-asyncio; real platform/Telegram calls forbidden
│   └── ...                        one file per module/behavior area; see the test files
│                                   themselves for what each one covers
│
├── data/                        bot.db; gitignored
└── logs/                        bot.log, bot.err.log; gitignored
```

`db/migrations/` and `tests/` are not enumerated file-by-file above — the file names
are already descriptive (`test_psn_fetcher.py`, `017_steam_presence_grace.sql`, ...);
keeping a parallel manual list here would just be one more place to forget to update.
Update the sections above whenever a file's *purpose* isn't obvious from its name, or
when this tree itself goes stale — a map nobody trusts is worse than no map.

## Localization

All user-facing text is stored in `bot/locales/<locale>/LC_MESSAGES/*.ftl` and
resolved through `aiogram_i18n` in handlers or `bot.i18n.gettext` in pollers,
services, and other code without handler dependency injection. Only `ru` ships
today, and `ConstManager("ru")` deliberately preserves the bot's Russian-only
behavior while keeping the second-language seam explicit.

**New user-facing strings go only into `.ftl` files** — never hardcoded Russian (or
any other language) in Python. Handlers/services/pollers reference keys via
`i18n.get(...)` or `gettext(module, ...)`; buttons, alerts, cards, and published
messages are the same rule. Code comments and log lines stay English and stay in
the source.

## Configuration

Required environment variables: `BOT_TOKEN` (BotFather), `ADMIN_TG_IDS`
(comma-separated Telegram user IDs allowed to use `/admin`), `AZURE_CLIENT_ID` /
`AZURE_CLIENT_SECRET` (Microsoft app), `OAUTH_REDIRECT_URL` (public HTTPS callback
URL — Microsoft rejects plain `http://` and `localhost`), `FERNET_KEY` (encrypts
stored secrets).

Optional: `STEAM_API_KEY`, `OAUTH_LISTEN_HOST` / `OAUTH_LISTEN_PORT`, `DB_PATH`,
`LOG_LEVEL`, and the poller interval settings (presence, achievement, token,
catch-up tuning).

`STEAM_API_KEY` is only a **first-run seed** (#17): on first access `SteamAuth`
imports it once into `app_settings` (encrypted), and from then on the admin
panel's "🔑 Ключи платформ" screen owns it — set / change / clear, no restart,
no `.env` edit. Without a key anywhere, `/connect_steam` answers "not configured"
and nothing else is affected. Clearing the key in the panel disables the seed
(the panel action is the newer, explicit decision), so a stale env var can't
resurrect it.

## Data model

The canonical schema is `bot/db/schema.sql`. This section describes the model, not
every column.

- **Identity.** `users` is keyed by Telegram `tg_id`. Xbox identity stays on
  `users.xuid` (it was the first platform, and Xbox-specific paths still use it
  directly). Steam and PSN accounts live in `platform_links (tg_id, platform,
  external_id, display_name, ...)`. `tg_id` is the cross-platform owner key — never
  aggregate cross-platform data by `xuid`.
- **Secrets and tokens.** `tokens` stores encrypted Xbox refresh tokens only; access
  and XSTS tokens stay in memory. Shared service credentials (the PSN NPSSO) are
  encrypted in `app_settings`. Token status distinguishes active, invalid, and
  intentionally revoked.
- **Achievements and publications.** `seen_achievements` is the dedup table, primary
  key `(tg_id, platform, title_id, achievement_id)`; `platform` is `modern`, `x360`,
  `steam`, or `psn`. `xuid` is kept as a generic external-account-id column used by
  publication paths (holding a SteamID64 or PSN account_id on non-Xbox rows).
  `is_backfill` marks history that must never publish. `is_secret` marks
  spoiler-rendered achievements. `trophy_type` holds the PSN trophy tier, `NULL`
  everywhere else. `publications` records what was actually posted to each chat.
- **Chats and settings.** `chats` + `subscriptions` (who publishes where;
  `subscriptions.rarity_mode` and `subscriptions.digest_threshold` are per
  person-per-chat, not per person). `chat_settings` holds each chat's own rarity
  threshold, summary time, timezone offset, muted games, minimum gamerscore, and
  daily-summary switch. `user_settings` holds personal, chat-independent settings:
  timezone offset, muted games, and `show_profile_links` (off by default; a new
  user's starting value comes from `app_settings['default_show_profile_links']`).
- **State and caches.** Xbox presence: `presence_state`. Steam presence:
  `steam_presence_state`. PSN polling progress: `psn_title_progress` /
  `psn_poll_state`. Xbox title history/gamerscore cache: `title_history`, `titles`.
  Steam achievement schema/rarity cache: `steam_schema_cache`, `steam_rarity_cache`.
  PSN's own cached account level: `platform_links.psn_trophy_level` (refreshed by
  the poller after backfill and after any tick that finds new trophies — the level
  only changes when a trophy is earned, so there's no reason to touch it every
  tick). HowLongToBeat cache: `hltb_cache`. Telegram message bookkeeping:
  `bot_messages`, `tracked_messages`, `online_auto_refresh`, `admin_panel_refresh`.

## Platform integrations

### Xbox

Microsoft OAuth + Xbox Live APIs, one refresh token per user.

- Store only encrypted refresh tokens.
- Refresh lazily, right before a request, when the token is close to expiry.
- Serialize refresh attempts per user — Microsoft invalidates the previous refresh
  token when a new one is issued, so a concurrent refresh can log the user out.
- Persist a newly issued refresh token *before* making the request that needed it.
- Treat `invalid_grant` as dead access: mark the token invalid, notify the user.
- Never log tokens or unmasked token-bearing payloads, in output or exception text.
- Modern Xbox achievements come from achievement contract version 4 (the only
  contract that carries rarity). Only `progressState == "Achieved"` may be inserted
  into `seen_achievements` — `InProgress` rows must never enter that table at all,
  or the achievement is hidden from publication forever once it's actually earned.
- Xbox 360 uses contract 1 instead, has no rarity percentage at all, and its
  achievement icon is replaced with the cached title's own cover art (contract 1
  carries only a bare `imageId` int, with no documented way to turn it into a URL).
- Resolve/match an **Xbox account** by its **XUID**, never by gamertag — a
  gamertag can change, XUID can't. `users.gamertag` is a display cache only, never
  a lookup key. (This is Xbox-internal, the same role SteamID64 and PSN's
  account_id play for their own platforms below — it doesn't change `tg_id` being
  the one cross-platform, top-level key a *person* is identified by.)

### Steam

The official Steam Web API, one shared API key for the whole bot, no per-user OAuth.

- The key lives encrypted in `app_settings` and is read lazily by `SteamAuth`
  (`services/steam/auth.py`) — admin-settable from the panel without a restart,
  `STEAM_API_KEY` in `.env` is only the first-run seed (#17, see Configuration).
  Every consumer (`SteamFetcher`, `SteamPresencePoller`, `/connect_steam`,
  `service_health`) fetches it through `SteamAuth`, never a constructor copy, so
  a set/change/clear takes effect on the next call.
- Users connect by Steam profile URL, vanity URL, or bare SteamID64.
- Profiles and game stats must be public enough for the API to expose them — not
  fixable on our end, only by the person changing their own Steam privacy settings.
- Presence is fetched in batches of up to 100 SteamIDs via `GetPlayerSummaries`.
- Achievement schema is cached forever per app; global rarity is cached with an
  expiry (it drifts over time, unlike the schema).
- Backfill scans owned games with nonzero playtime and inserts unlocked achievements
  as backfill rows — expensive by nature (one call per played game, not one call for
  the whole library like Xbox), so it runs with a two-level concurrency limit
  (people at once, games per person at once).

### PlayStation Network

One shared NPSSO credential for the whole bot, via `psnawp` — a real dependency
(`pyproject.toml`), the same class of dependency `xbox-webapi-python` is for Xbox,
not a thin httpx client. `psnawp` is synchronous (built on `requests`); every call
in `services/psn/client.py` must go through `asyncio.to_thread`.

- PSN has no documented public API for this use case at all — only reverse-engineered
  access to the same private API the PlayStation App itself uses.
- **The whole design rests on one verified bet**: a single admin-supplied NPSSO can
  read the trophies of *any* account whose trophy privacy is set to "Everyone" — so
  nobody else needs to log in, only make their own trophies visible and send the bot
  their Online ID. Confirmed live against three real accounts; do not weaken this
  design without re-verifying it.
- NPSSO setup must be verified with a real API call (`check_alive()`) before it's
  saved — constructing the client alone proves nothing, `psnawp`'s own token exchange
  is lazy and only fires on the first real request.
- Service health checks (`poller/service_health.py`) notify the admin when the
  shared PSN token or the Steam key stops working — exactly once per "alive → dead"
  transition, not every tick. Unlike Xbox, where one dead token affects only one
  person, a dead PSN token silently stops polling *everyone* linked to PSN.
- Trophy polling has no presence hook at all, unlike Xbox/Steam. PSN trophies may
  only sync to Sony's servers when a player opens trophy data on the console, not at
  the moment of unlock — so the poller scans every linked account's trophy titles on
  every tick and only fetches full detail for a title whose progress grew.
- The scan (`services/psn/achievements.py::sync_account`) persists **one game at a
  time, trophies before the progress cache** (#26). Advancing `psn_title_progress`
  before a game's trophies are actually written — the old shape — meant any
  exception partway through the scan left already-visited games marked "seen,
  nothing new" while their trophies were never stored, hiding them from every future
  poll and backfill (found live: a real account silently lost 43 trophies this way).
  An unmapped error on one game is logged and skipped, never aborts the scan.
- A freshly-linked PSN account is gated out of the regular poller by
  `psn_poll_state.backfill_done` until its first backfill finishes (#21): without
  the gate, a scheduler tick landing while the fire-and-forget backfill is still
  running fetches trophies backfill hasn't inserted yet and publishes the account's
  whole history at once. A stuck account (backfill crashed, flag never set) is
  recovered by an admin resync, not by the poller.
- `Trophy.trophy_earn_rate` is typed `float | None` by `psnawp_api`, but the library
  hands it back as a numeric *string* with no cast — coerce it explicitly
  (`services/psn/client.py::_as_float`) rather than trusting the type annotation.
  Found live: this silently dropped every PSN notification carrying rarity data,
  with no visible error anywhere, until it was hit by an actual test send.
- PSN achievements are called "trophies" in every user-facing message, not
  "achievements" — the header reads "gets a trophy", and PSN's badge is its own
  tier icon (🥉🥈🥇🏆) in place of the usual rarity diamond/cup, since the tier
  already answers the same "how rare" question on Sony's own scale (showing both
  used to be possible to collide visually: a platinum trophy and an "ordinary"
  rarity badge are the same emoji).
- PS3, PS4, PS5, and PS Vita share the same trophy service and fields — no separate
  parsing branch, unlike Xbox 360.

Open work (see the linked issues, not this file, for scope/status):

- PSN presence, and full integration into `/stats`, `/summary`, `/online`, and the
  panel the way Steam already has it — issue #1. `/stats` already shows a PSN
  person's achievement count and cached account level; `/summary`'s combined total
  already includes PSN rows for free (it has grouped by `tg_id`, not by a
  platform-specific id, since before PSN existed) — presence for `/online` and full
  panel parity are what's still missing.
- Linking more than one PSN account per person — issue #10. `platform_links`
  currently allows exactly one row per `(tg_id, platform)`.

## Polling model

The scheduler ticks every minute; each poller decides for itself whether a target is
due.

- **Presence cadence** (Xbox, Steam) is state-based: fastest while in a game,
  slower online-but-idle, slower still offline, slowest for someone long absent.
  The goal is politeness, not quota optimization — sparse polling of an absent user
  keeps logs clean and avoids pointless calls, on both platforms, even though
  neither is actually quota-constrained at this scale.
- **Achievement polling**: while in a game, poll that game on the achievement
  debounce interval; on a game change or going offline, do one final poll of the
  *previous* game first (to catch a last-second unlock before leaving). A poller
  must never crash a whole tick because one user, account, title, or small API
  batch failed — isolate and log, then continue. Expected external states (not
  exceptions): private profiles, empty responses, HTTP 429, timeouts, dead
  credentials, upstream outages.
- **Backfill** is mandatory on first connection and safe on reconnection: insert
  history with `is_backfill = 1`, never publish it. Source differs per platform —
  Xbox modern uses a broad history endpoint, Xbox 360 is a title-by-title pass,
  Steam scans owned games with playtime, PSN scans trophy titles directly (cheaper
  than Steam's: one unlimited paginated call already lists every title with
  progress). Backfill inserts must be idempotent (`INSERT OR IGNORE`). PSN backfill
  additionally flips `psn_poll_state.backfill_done` as its last step — the regular
  poller ignores the account until then (#21, see the PSN section above).
- **Catch-up after downtime** may publish missed achievements only inside the
  configured recent window — older rows are stored for stats/dedup but never
  flooded into chat.

## Publication rules

Publishable to a chat only if every check passes: the person is subscribed there;
not admin-excluded; `subscriptions.rarity_mode` isn't `hidden`; in `rare` mode, a
known rarity is at or below that chat's threshold (a platform reporting no rarity
data at all — currently only Xbox 360 — is exempt from this check, not silently
hidden by it); the achievement's gamerscore meets the chat's minimum; the title
isn't muted there; the exact item wasn't already published to that chat.

The rarity threshold itself is always `chat_settings.rare_threshold_percent` — an
admin sets it per chat through the bot. Never hardcode a percentage (10% or
otherwise) as the threshold; the person only ever picks a *mode* (`all`/`rare`/
`hidden`), never a number.

`subscriptions.digest_threshold` decides when a batch becomes one grouped message
instead of several — grouped by platform and title. Every achievement in a digest is
listed, never truncated with "and N more". A media gallery dedupes by image URL, so
several achievements sharing one icon (all of Xbox 360's own achievements share the
game's box art) don't repeat the same picture.

Delivery goes through a send queue to stay under Telegram's group rate limit. A
Telegram 403 means the bot was removed from that chat — deactivate it, don't keep
trying. Every send records its message id for cleanup/admin-deletion features.

## User interface

All user-facing bot text is Russian. Code identifiers, comments, and this
documentation are English.

**Private commands**: `/start`, `/connect_xbox`, `/disconnect_xbox`,
`/connect_steam`, `/disconnect_steam`, `/connect_psn`, `/disconnect_psn`, `/panel`.
A private flow started from a group must redirect the person to a DM, never fail
silently in the group.

**The personal panel** (`/panel`, one self-editing message): the header is the
person's own Telegram identity (same priority as `/stats`' header) followed by one
line per connected platform with its lifetime achievement/trophy count, gamerscore,
and PSN level — the shape `/stats`' header has, built by `/panel`'s own plain-text
helper, not the shared one (#18). The body below carries only login status per
platform, publication destinations, current presence, and the timezone; the 24h/30d
counters and "recent achievements" list it used to show are gone (the header covers
achievements). The keyboard is one row per platform (Xbox → Steam → PSN) in a fixed
position — `[Profile, Disconnect]` when connected, one wide "🎮 Подключить X" when
not (#33) — plus timezone / My chats / sync / `show_profile_links` toggle, and the
per-chat subscription cards (rarity mode, digest threshold). Own profile links here
are always visible regardless of the privacy toggle — this screen is never rendered
to anyone but its owner. The panel must never call a platform API except the one
explicit manual-sync button.

**Group commands**: `/subscribe`, `/unsubscribe`, `/stats [@user]` (cached stats +
recent games; the card's header shows the person's Telegram identity — `@username`,
else first+last name, else a connected platform's own name as a last resort — not a
platform gamertag, since every connected platform already gets its own line below),
`/who` (pick a known member, opens their `/stats`; the picker buttons identify the
person the same way `/stats`' header does — `@username` > name > gamertag > platform
name, never a bare id — #40), `/online` (cached presence,
optionally auto-refreshing), `/recent [N]`, `/summary`, `/hltb`, `/delete_last`
(deletes the chat's own latest non-system bot message). `chat_seen` tracks anyone
known who has written in the group, even without a publish subscription — `/online`
and `/who` use that broader set, not just subscribers.

A nickname in `/stats`/`/who` becomes a clickable profile link only when the person
*the card is about* has `show_profile_links` on — there is no exception for viewing
your own card: the rendered message is identical regardless of who asked for it.

**The admin panel** (`/admin`, private, restricted to `ADMIN_TG_IDS`, also
self-refreshing) provides: Steam/PSN shared-credential health; a "🔑 Ключи
платформ" screen to set / change / clear both shared credentials (the Steam key
and the PSN NPSSO) from inside the bot, no `.env` edit (#17); API usage
snapshots; global display/cleanup limits; defaults for new users (including
`default_show_profile_links`); the user list and per-user cards; the chat list and
per-chat cards; exclusion/restore; a manual per-user refresh per linked platform
(Xbox/Steam/PSN); per-chat settings (rarity threshold, summary time, timezone,
mutes, minimum gamerscore, daily-summary switch); bot-message cleanup actions. The
separate "🏆 Трофеи PSN (тест)" screen is now only the live trophy-lookup test —
NPSSO management moved to the keys screen.
Admin-triggered manual refresh is the only normal UI path allowed to call a
platform API outside a background job. The PSN refresh doubles as the recovery
path for an account stuck "linked but the first backfill never finished" (#27):
it wipes the partial `psn_title_progress` checkpoints and re-runs backfill,
instead of that needing a manual DB script on the server.

## Message formats

A single achievement/trophy post: bold name + "gets an achievement" (or, for PSN,
"gets a trophy"), a blank line, the game name and platform in italics, a badge
before the achievement's name in quotes, then gamerscore (if nonzero) and rarity
percent (if known) separated by a period, then the description if present (behind a
spoiler if secret/hidden).

The badge is `rarity_badge()` (💎 at or below the rare threshold, 🏆 otherwise,
including when rarity is simply unknown) for every platform except PSN, which shows
its own tier icon instead (🥉🥈🥇🏆) — see the PSN section above for why.

A digest groups several achievements under one header ("gets N achievements" / "gets
N trophies" for an all-PSN batch), one block per game, same per-line format as a
single post, every item listed. `plural_achievements()` itself is never
platform-specific — it also serves combined cross-platform totals (e.g. `/stats`'
"Today: N achievements"), which are correctly "achievements" regardless of how many
of them came from PSN.

Lists (`/stats`, `/recent`, `/summary`, the daily summary) render as sentence-lines
inside a collapsible `<blockquote expandable>`, never a monospace `<pre>` table
(which renders as a code block — wrong register for a leaderboard or game list).
Summary windows are sliding (last 24 hours, last 30 days), not calendar-aligned.

## Statistics rules

Normal stats read only from `seen_achievements`, `title_history`, platform links,
and cached presence/level tables — never a live platform call. `/stats`' lifetime
achievement count (`repo.xbox_achievement_count`/`platform_achievement_count`)
always counts `seen_achievements` rows directly, never sums `title_history` —
modern Xbox's broad history-endpoint backfill and Steam's full-library backfill
both make that count trustworthy; x360's own title-by-title backfill is the one
remaining soft spot (driven by `title_history`'s own game list, so a title it
never learned about is a silent gap there specifically). Xbox gamerscore always
comes from the Xbox profile cache, never from summing title history. A 100%-completed
game (Xbox/Steam) and a PSN platinum trophy answer the same question — Sony only
awards a platinum once every other trophy in that game is earned — so both render as
the same 🏆 symbol + count next to the platform's achievement/trophy count, never a
word, and only when nonzero. Cross-platform 24h/30d counters aggregate by `tg_id`.
Platform breakdowns (e.g. "(🟢 3 · ⚫ 5)") show only where they clarify genuinely
mixed-platform activity. Excluded users are never polled, published, or
included in any summary.

## HowLongToBeat

`/hltb` works in both DMs and groups: prompts for a game name, accepts a reply to
that prompt in groups, offers recent-game suggestions from known chat members,
cleans noisy platform title strings before searching, shows candidates rather than
trusting the first search result, and caches the chosen result by HLTB id forever.
Treat HLTB outages as an expected external failure, not an exception.

Open work: optional game descriptions once a reliable source is picked — issue #2.
Steam Store API was checked and rejected (marketing copy or unparsed HTML); IGDB,
an LLM-generated summary, and Wikipedia are candidates, none chosen yet. Do not add
recurring paid LLM usage without explicit rate limits and cost controls.

## Security and privacy

- Never commit `.env`, database files, logs, PID files, or runtime data.
- Encrypt every stored credential with Fernet: Xbox refresh tokens, the shared PSN
  NPSSO, and (as of #17) the shared Steam API key — all live encrypted in
  `app_settings` / `tokens`, never plaintext.
- Losing `FERNET_KEY` now also means re-entering the Steam key and PSN NPSSO in the
  admin panel, on top of every user reconnecting.
- Never log a raw token, API key, NPSSO value, authorization header, or a URL
  carrying a secret in a query parameter (found live: `httpx` logs full request
  URLs at INFO, and Steam's `GetOwnedGames` carries the API key in one) — mask
  before logging any structure that might carry one.
- A user-facing error must never expose an upstream token error's raw payload.
- Losing `FERNET_KEY` forces every user to reconnect — back it up securely.
- A person can disconnect locally at any time, but revoking Microsoft's own consent
  has to happen in the user's own Microsoft account settings — the bot can only link
  to that page, not do it for them.
- Profile links in `/stats`/`/who` are gated by the profile's own owner's
  `user_settings.show_profile_links` (off by default) — see "User interface" above.

## Operations

**Local development** (Windows) is driven by `manage.ps1` (the bot cannot start
itself): `start` / `stop` / `restart` / `status` / `logs [-Lines N]`. `status` shows
uptime, whether port 8080 is taken, any stray bot process (two bots sharing one
`BOT_TOKEN` fight over Telegram's updates), and a database summary.

`.\manage.ps1 dashboard` (or double-clicking `manage.bat`) opens a live console
view — the same block as `status`, plus a `bot.log` tail, redrawing every 5 seconds
(`-RefreshSeconds N` to change it), with `[2] Start [3] Stop [4] Restart [Q] Quit`
hotkeys live the whole time. The separate `start`/`stop`/`restart`/`status`/`logs`
commands still work too, for a one-line terminal call when the dashboard isn't
needed.

Never run the local bot and the production bot with the same `BOT_TOKEN` at the same
time — the home PC is for development only, its `.env` should point at `localhost`
or a temporary tunnel, not the production domain.

**Production** is a VPS (DigitalOcean, Amsterdam), Ubuntu 24.04, behind nginx and
systemd. App directory `/opt/xbox_achievement_bot`, service `xbox-bot.service`
(dedicated unprivileged user `botsvc`, autostart on):

```bash
systemctl {start|stop|restart|status} xbox-bot
journalctl -u xbox-bot -f
```

nginx on 443 (Let's Encrypt, auto-renewed via the certbot timer) proxies to
`127.0.0.1:8080`, where the bot's own OAuth callback listens — port 8080 itself is
never exposed externally (`OAUTH_LISTEN_HOST=127.0.0.1` in the server's `.env`). Git
on the server uses a read-only deploy key (GitHub → Settings → Deploy keys), not an
account token.

Deploy is currently manual: `git pull --ff-only`, reinstall dependencies if they
changed, `systemctl restart xbox-bot`. Back up `bot.db` first whenever the deploy
includes a new migration — migrations here are forward-only, and a destructive one
(a rebuild-and-swap that drops a column) can't be undone without a kept backup and a
matching code rollback together.

Open work: GitHub Actions CI (pytest + ruff on every PR/push) and automated deploy
from a protected production branch, secrets via GitHub Actions secrets, never in the
repository — issue #4.

## Engineering rules

- Keep handlers thin — they call services and repository methods, never raw SQL or
  platform API logic directly.
- All SQL lives in `bot/db/repo.py`, `schema.sql`, and the migrations. Nowhere else.
- Platform clients (`services/xbox`, `services/steam`, `services/psn`) must not know
  about Telegram.
- Everything is async; never block the event loop. Wrap a synchronous library
  (`psnawp`, built on `requests`) with `asyncio.to_thread`.
- Do not add a dependency unless it's clearly needed.
- Do not leave a stub or a TODO placeholder instead of a real implementation. If a
  step is too large to do properly, say so and split it — don't half-do it.
- Before finalizing a new or changed bot-facing message format (a panel, a card, a
  notification, any new UI text shape), preview it as a real DM to the admin before
  treating it as final — a style decision made only from a description, not a real
  rendered Telegram message, gets redone many times once it's actually visible.
  Render against real data (production data read-only, or a constructed example when
  no real case exists yet — e.g. a feature nothing in production has data for) and
  send **only that rendered message text**, exactly as the real bot would send it —
  no wrapping explanation, no bullet list of what changed, no meta commentary in the
  same message. Caveats, open questions, and "confirm before I finalize this" notes
  go in the chat reply that accompanies the preview, never inside the previewed
  message itself, since anything inside it reads back as leftover clutter once the
  format ships for real.

## Tests

```powershell
.\.venv\Scripts\pytest
.\.venv\Scripts\ruff check .
.\.venv\Scripts\ruff format --check .
```

Real Xbox, Steam, PSN, HLTB, or Telegram API calls are forbidden in tests — mock at
the service boundary, the way every existing test file already does.

Required coverage areas: achievement/trophy deduplication; first-connect backfill
publishes nothing; only `Achieved`/earned items enter `seen_achievements`
(`InProgress` must never leak in); rarity filtering at different thresholds; a
platform with no rarity data at all under `rare` mode; Xbox token refresh
ordering and serialization, `invalid_grant` handling; admin-excluded users are
never polled or published; a dead-token reminder is rate-limited (no more than once
every few days, capped in total); a missing rarity block in a real API response
doesn't crash parsing; a token or secret never appears in a log line or exception
text; Steam/PSN account linking, presence, achievement/trophy parsing, rarity/
progress caching, and backfill in isolation.

## Style

- Code identifiers and comments: English. Bot messages shown to users: Russian.
- Comment *why*, not *what* — especially in the pollers and around token refresh,
  where the reasoning isn't obvious from the code alone.
- Prefer small, precise changes that preserve existing behavior unless the task is
  specifically to change it.

## Appendix: rejected ideas — do not reintroduce without a new decision

- **OpenXBL** as an Xbox data source — a third-party proxy with a 150-request/hour
  ceiling that required storing an all-access key to other people's accounts.
  Dropped in favor of direct Microsoft OAuth per user (each person gets their own
  300-requests-per-5-minutes budget — nothing left to ration for).
  - Everything that only existed to manage that shared 150/hour budget went with
    it: two credential types (`oauth`/`own`) and a `credentials` table, a
    `/connect_key` command that had people paste secrets into chat, batched
    presence purely as a cost-saving move, and a dedicated `api_budget` table
    splitting poll vs. command quota.
  - The old ban on one person linking multiple accounts existed only because of
    OpenXBL's shared budget too, and lost its reason along with it.
  - A first edition also implicitly required the bot to be friends with every
    player on Xbox Live (to see their presence) — polling with each person's own
    token means everyone always sees themselves, friendship isn't needed at all.
- **A `filters` table with a `scope` column** — replaced by separate
  `user_settings`/`chat_settings` with an explicit combination rule (AND).
- **`/compare` and `/top`** — the useful group views are `/stats`, `/summary`,
  `/recent`, `/online`; a leaderboard-shaped command was judged not worth the
  UI surface.
- **A separate visibility toggle per platform** (e.g. one for Xbox 360, a second
  one drafted for Steam) — tried twice, rejected twice, for the same reason: with
  no real reason for someone to want a *different* mode on different platforms,
  a switch per platform is accumulation, not architecture. One shared
  `rarity_mode` covers every platform; one without rarity data (Xbox 360 today) is
  simply exempt from the `rare` check rather than getting a toggle of its own.
- **Global rarity settings that apply to every chat at once** — replaced by an
  explicit per-chat threshold; a shared knob that moved every chat on every edit
  turned out not to be what real multi-chat use wanted.
- **Live platform API calls from `/stats`, `/summary`, `/online`, or the panel** —
  every normal read is cache-only; the one deliberate exception is the panel's own
  explicit manual-sync button.
