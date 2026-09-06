# Achievement Bot - Product and Architecture Specification

Achievement Bot is a Telegram bot for small gaming groups. It publishes newly
unlocked achievements and trophies from connected Xbox, Steam, and PlayStation
Network accounts, keeps local statistics, and gives group admins enough controls to
keep the chat readable.

The target deployment is a private, non-commercial community of about 20-30 people.
The product is intentionally optimized for one trusted operator, a single SQLite
database, explicit admin controls, and predictable behavior rather than public SaaS
scale.

## 1. Product scope

### 1.1 Goals

- Publish new achievements and trophies to Telegram group chats.
- Support Xbox, Xbox 360, Steam, and PSN accounts under one Telegram user.
- Avoid posting historical achievements when a user connects for the first time.
- Let every chat define its own rarity threshold, summary time, timezone, mutes, and
  minimum gamerscore filter.
- Let every user choose, per chat, whether all achievements, only rare achievements,
  or no achievements are published.
- Keep stats and panels fast by reading from the local database, not from live
  platform APIs.
- Keep secrets out of logs, exception text, git, and user-facing messages.

### 1.2 Non-goals

- No public web UI. The only web endpoint is the Microsoft OAuth callback.
- No `/compare` or `/top`; `/stats`, `/summary`, `/recent`, and `/online` cover the
  useful group views.
- No global per-platform visibility toggles. Visibility is per user and per chat,
  and applies to all platforms consistently.
- No real platform API calls from normal read-only commands or panels.
- No multi-tenant hosting model.

## 2. Technology stack

- Python 3.12+
- aiogram 3 for Telegram long polling
- aiohttp for the Microsoft OAuth callback server
- httpx for platform HTTP clients
- aiosqlite with a local SQLite database
- APScheduler with `AsyncIOScheduler`
- pydantic v2 and pydantic-settings
- cryptography Fernet for token encryption
- xbox-webapi-python for Microsoft/Xbox authentication support
- howlongtobeatpy for HowLongToBeat search
- psnawp for PSN access
- pytest, pytest-asyncio, and ruff for tests and style

## 3. Repository architecture

```text
bot/
  main.py              application assembly and startup
  config.py            settings loaded from environment
  util.py              shared helpers
  lock.py              local single-instance guard
  handlers/            aiogram UI layer only
  services/            business logic, platform clients, renderers
  poller/              scheduled background jobs
  web/                 Microsoft OAuth callback
  db/
    schema.sql         current schema for a fresh database
    migrations/        ordered schema migrations
    repo.py            the only data-access layer
tests/                 mocked pytest suite
scripts/               operational one-off helpers
data/                  runtime database, ignored by git
logs/                  runtime logs, ignored by git
```

Layering rules:

- Handlers may call services and repository methods, but must not contain raw SQL or
  platform API logic.
- SQL belongs in `bot/db/repo.py`, schema files, and migrations.
- Platform clients do not know about Telegram.
- Pollers isolate failures per user or per small API batch.
- Rendering shared by commands and background refresh jobs belongs in services.

## 4. Configuration

Required environment variables:

| Variable | Purpose |
| --- | --- |
| `BOT_TOKEN` | Telegram bot token from BotFather |
| `ADMIN_TG_IDS` | comma-separated Telegram user IDs allowed to use `/admin` |
| `AZURE_CLIENT_ID` | Microsoft app client ID |
| `AZURE_CLIENT_SECRET` | Microsoft app client secret |
| `OAUTH_REDIRECT_URL` | public HTTPS callback URL |
| `FERNET_KEY` | key used to encrypt stored secrets |

Optional variables:

| Variable | Purpose |
| --- | --- |
| `STEAM_API_KEY` | shared Steam Web API key |
| `OAUTH_LISTEN_HOST` / `OAUTH_LISTEN_PORT` | local callback bind address |
| `DB_PATH` | SQLite database path |
| `LOG_LEVEL` | application log level |
| poller interval variables | presence, achievement, token, and catch-up tuning |

Microsoft OAuth requires a real HTTPS redirect URI. Plain `http://` and `localhost`
redirects are not accepted for this flow.

## 5. Data model

The canonical schema is `bot/db/schema.sql`. This section describes the model, not
every column.

### 5.1 Identity

- `users` is keyed by Telegram `tg_id`.
- Xbox identity remains on `users.xuid` because it was the first platform and is still
  used by Xbox-specific paths.
- Additional platform accounts live in `platform_links` with `(tg_id, platform,
  external_id, display_name)`.
- `tg_id` is the cross-platform owner key. Do not aggregate cross-platform data by
  `xuid`.

### 5.2 Secrets and tokens

- `tokens` stores encrypted Xbox refresh tokens only.
- Access tokens and XSTS tokens live in memory.
- Shared service credentials, such as the PSN NPSSO, are encrypted in app settings.
- Token status values distinguish active, invalid, and intentionally revoked access.

### 5.3 Achievements and publications

- `seen_achievements` is the deduplication table.
- The primary key is `(tg_id, platform, title_id, achievement_id)`.
- `platform` includes at least `modern`, `x360`, `steam`, and `psn`.
- `xuid` is retained as a generic external account ID column for publication paths.
- `is_backfill` marks history imported only for deduplication.
- `is_secret` marks achievements that must be rendered with Telegram spoilers.
- `trophy_type` stores PSN trophy tier when present.
- `publications` records what was actually posted to each chat.

### 5.4 Chats and settings

- `chats` stores Telegram group metadata and activity state.
- `subscriptions` stores who publishes into which chat.
- `subscriptions.rarity_mode` is per user per chat: `all`, `rare`, or `hidden`.
- `subscriptions.digest_threshold` is per user per chat.
- `chat_settings` stores per-chat rarity threshold, summary time, timezone offset,
  muted games, minimum gamerscore, and daily summary switch.
- `user_settings` stores personal settings that are not chat-specific, including
  timezone offset, muted games, and profile-link privacy.

### 5.5 State and caches

- Xbox presence: `presence_state`.
- Steam presence: `steam_presence_state`.
- PSN polling progress: `psn_title_progress` and `psn_poll_state`.
- Xbox title history and gamerscore cache: `title_history` and `titles`.
- Steam achievement schema and rarity cache: `steam_schema_cache` and
  `steam_rarity_cache`.
- HowLongToBeat result cache: `hltb_cache`.
- Telegram message bookkeeping: `bot_messages`, `tracked_messages`,
  `online_auto_refresh`, and `admin_panel_refresh`.

## 6. Platform integrations

### 6.1 Xbox

Xbox uses Microsoft OAuth and Xbox Live APIs.

Rules:

- Store only encrypted refresh tokens.
- Refresh lazily before a request when the token is close to expiry.
- Serialize refresh attempts per user. Microsoft invalidates the previous refresh
  token when a new one is issued, so concurrent refreshes can log a user out.
- Persist a newly issued refresh token before making the API request that needed it.
- Treat `invalid_grant` as dead access: mark the token invalid and notify the user.
- Do not log tokens or unmasked token-bearing payloads.

Achievement data:

- Modern Xbox achievements are fetched per title through Xbox Live achievement
  contract version 4 because rarity is available only there.
- Only `progressState == "Achieved"` may be inserted into `seen_achievements`.
- Xbox 360 uses a different contract and has no rarity percentage.
- Xbox 360 achievement icons are replaced with the cached title cover when no proper
  achievement icon URL exists.

### 6.2 Steam

Steam uses the official Steam Web API with one shared API key.

Rules:

- Users connect by Steam profile URL, vanity URL, or SteamID64.
- No per-user OAuth or token refresh exists.
- Profiles and game details must be public enough for the API to expose stats.
- Presence is fetched in batches with `GetPlayerSummaries`.
- Achievement schema and global rarity are cached per app.
- Backfill scans owned games with playtime and inserts unlocked achievements as
  backfill rows.

### 6.3 PlayStation Network

PSN uses a shared NPSSO credential through `psnawp`.

Rules:

- PSN has no documented public API for this use case.
- `psnawp` is synchronous, so calls must be wrapped with `asyncio.to_thread`.
- NPSSO setup must be verified with a real API call before it is saved.
- Service health checks notify admins when the shared credential stops working.
- Trophy polling is not presence-driven. PSN trophies may sync only when a player
  opens trophy data on the console, so the poller scans trophy titles and fetches
  full details only when cached progress changes.

Open work:

- PSN trophies are published, but PSN is not fully integrated into `/stats`,
  `/summary`, `/online`, and `/panel` yet.
- PSN presence design still needs finalization.

## 7. Polling model

The scheduler ticks every minute. Each poller decides whether a target is due.

### 7.1 Presence cadence

Presence intervals are shared by Xbox and Steam:

| State | Default intent |
| --- | --- |
| in game | fastest polling |
| online but not in game | moderate polling |
| offline | slower polling |
| long idle | slowest polling |

The goal is not quota optimization only. Sparse polling for absent users keeps logs
clean and avoids unnecessary calls to external services.

### 7.2 Achievement polling

- While a user is in a game, poll that game with the achievement debounce interval.
- On game change or transition to offline, perform a final poll for the previous game.
- Pollers must not crash the whole tick because one user, account, title, or small API
  batch failed.
- Expected external states include private profiles, empty responses, HTTP 429,
  timeouts, dead credentials, and upstream outages.

### 7.3 Backfill

Backfill is mandatory on first connection and safe on reconnection.

- Insert historical achievements with `is_backfill = 1`.
- Never publish backfill rows.
- Use platform-specific history sources:
  - Xbox modern: broad achievement history endpoint.
  - Xbox 360: title-by-title pass through Xbox 360 titles.
  - Steam: owned games with playtime.
  - PSN: trophy title scan.
- Backfill inserts must be idempotent.

### 7.4 Catch-up after downtime

Manual or startup catch-up may publish missed achievements only inside the configured
recent window. Older rows should be stored for deduplication and stats if useful, but
not pushed into chat as a flood.

## 8. Publication rules

An achievement is publishable to a chat only if all checks pass:

| Check | Rule |
| --- | --- |
| subscription | user is subscribed to that chat |
| exclusion | user is not admin-excluded |
| visibility | `subscriptions.rarity_mode` is not `hidden` |
| rarity | in `rare` mode, known rarity must be at or below the chat threshold |
| no rarity data | platform-wide missing rarity, such as Xbox 360, does not fail `rare` mode |
| gamerscore | achievement gamerscore is at least the chat minimum |
| muted title | title is not muted by the chat |
| dedup | the same item was not already published to that chat |

Digest behavior:

- `subscriptions.digest_threshold` controls when one grouped message is used instead
  of individual messages.
- Digest grouping is by platform and title.
- All achievements in a digest are listed; do not truncate with "and N more".
- Media galleries use unique image URLs to avoid repeating the same Xbox 360 cover.

Telegram delivery:

- Use a send queue to stay below Telegram group rate limits.
- A Telegram 403 means the bot was removed from the chat; mark the chat inactive.
- Record message IDs for cleanup and admin deletion features.

## 9. User interface

All user-facing bot text is Russian. Code identifiers, comments, and documentation are
English.

### 9.1 Private commands

- `/start` - explains the bot and shows connection actions.
- `/connect_xbox` - starts Microsoft OAuth.
- `/disconnect_xbox` - removes the local token and subscriptions, with confirmation.
- `/connect_steam` - starts the Steam profile-link flow.
- `/disconnect_steam` - disconnects Steam, with confirmation.
- `/connect_psn` - starts the PSN account-link flow.
- `/disconnect_psn` - disconnects PSN, with confirmation.
- `/panel` - opens the personal panel.

Private flows must redirect users out of group chats instead of failing silently.

### 9.2 Personal panel

The panel is a single editable message. It shows:

- connected platform identities;
- Xbox token status when applicable;
- publication destinations;
- current presence from cache;
- 24-hour and 30-day counters;
- recent achievements;
- timezone and profile-link privacy controls;
- per-chat subscription cards with rarity mode and digest threshold.

The panel must not call platform APIs except for the explicit manual sync action.

### 9.3 Group commands

- `/subscribe` - publish my achievements in this chat.
- `/unsubscribe` - stop publishing in this chat, with confirmation.
- `/stats [@user]` - show player stats and recent games from cache.
- `/who` - pick a known chat member and open stats.
- `/online` - show cached online status for known chat members; the message can
  auto-refresh.
- `/recent [N]` - show recent chat achievements.
- `/summary` - show the same report as the scheduled daily summary.
- `/hltb` - search HowLongToBeat completion times.
- `/delete_last` - bot admin command to delete the latest non-system bot message in
  that chat.

`chat_seen` tracks connected users who wrote in a group even if they are not
subscribed. `/online` and `/who` use this broader membership set.

### 9.4 Admin panel

`/admin` is private and restricted to `ADMIN_TG_IDS`. It is also a single editable
message and can auto-refresh.

It provides:

- global service health for Steam and PSN credentials;
- API usage snapshots;
- global display limits and cleanup settings;
- defaults for new users/subscriptions;
- user list and user cards;
- chat list and chat cards;
- exclusion/restore controls;
- manual refresh for a user;
- chat settings for rarity threshold, summary time, timezone, mutes, minimum
  gamerscore, and daily summary;
- bot message cleanup actions.

Admin-triggered live refresh is the only normal UI path allowed to call platform APIs
outside background jobs.

## 10. Message formats

### 10.1 Single achievement

Single achievement posts use one shared format across platforms:

```text
Player receives an achievement

Game Name (Platform)
Badge "Achievement Name" · optional score · optional rarity

Description
```

Actual bot text is Russian and uses Telegram HTML.

Rules:

- Show gamerscore only when it is non-zero.
- Show rarity only when `rarity_percent` is known.
- Rarity badge has two states:
  - rare: rarity percentage at or below the rare badge threshold;
  - common: all other cases, including unknown rarity.
- Secret names, descriptions, and images use Telegram spoilers.
- If media upload fails or no image is available, send text.

### 10.2 Digest

Digest posts use the same achievement-line format under one header. They group by game
and platform, not just by player.

### 10.3 Summaries and tables

List-like outputs use the shared table/blockquote renderer instead of monospace
`<pre>` tables. This applies to `/stats`, `/recent`, `/summary`, and daily summaries.

Summary windows are sliding windows:

- last 24 hours;
- last 30 days.

They are not calendar-day or calendar-month windows.

## 11. Statistics rules

- Normal stats read from `seen_achievements`, `title_history`, platform links, and
  cached presence tables.
- Lifetime achievement count is intentionally not a general UI metric for Xbox because
  Xbox history coverage can be incomplete.
- Xbox gamerscore comes from the Xbox profile cache, not from summing title history.
- Cross-platform 24-hour and 30-day counters aggregate by `tg_id`.
- Platform breakdowns are shown where they clarify mixed-platform activity.
- Excluded users must not be polled, published, or included in summaries.

## 12. HowLongToBeat

`/hltb` works in private chats and groups.

Rules:

- Prompt for a game name and accept replies to the prompt in groups.
- Offer recent-game suggestions in groups from known chat members.
- Clean noisy platform title strings before searching.
- Show candidates instead of immediately trusting the first search result.
- Cache selected results by HLTB ID.
- Treat HLTB outages as expected external failures.

Open work:

- Add optional game descriptions once a reliable source is chosen.

## 13. Security and privacy

- `.env`, database files, logs, PID files, and runtime data are not committed.
- Encrypt stored refresh tokens and shared PSN secrets with Fernet.
- Never log raw tokens, API keys, NPSSO values, authorization headers, or URLs carrying
  secrets.
- Mask token-bearing structures before logging.
- User-facing errors must not expose upstream token error payloads.
- `FERNET_KEY` must be backed up securely. Losing it forces users to reconnect.
- Users can disconnect locally, but Microsoft consent revocation must be done by the
  user in Microsoft account settings.
- Profile links in public stats are controlled by user privacy settings.

## 14. Operations

### 14.1 Local development

Local Windows development uses `manage.ps1`:

```powershell
.\manage.ps1 start
.\manage.ps1 stop
.\manage.ps1 restart
.\manage.ps1 status
.\manage.ps1 logs -Lines 100
.\manage.ps1 dashboard
```

Do not run the local bot and production bot with the same `BOT_TOKEN` at the same time.

### 14.2 Production

Production runs on a VPS behind nginx and systemd:

- app directory: `/opt/xbox_achievement_bot`;
- service: `xbox-bot.service`;
- OAuth callback bound to `127.0.0.1:8080`;
- nginx terminates HTTPS and proxies the callback path.

Manual deploy is currently:

```bash
cd /opt/xbox_achievement_bot
git pull --ff-only
python -m pip install -e .
systemctl restart xbox-bot
```

### 14.3 Planned auto-deploy

Add GitHub Actions for CI and deployment:

- run pytest and ruff on pull requests and pushes;
- deploy only from the protected production branch after checks pass;
- connect to the VPS through SSH using GitHub Actions secrets;
- run a fast-forward pull, update dependencies, and restart systemd;
- never store runtime secrets in the repository.

## 15. Testing requirements

Tests use pytest and pytest-asyncio. Real platform and Telegram API calls are forbidden.

Required coverage areas:

- achievement deduplication;
- first-connect backfill does not publish history;
- only achieved/unlocked items enter `seen_achievements`;
- rarity filters and per-chat thresholds;
- platforms with no rarity data in `rare` mode;
- Xbox token refresh ordering and serialization;
- `invalid_grant` handling and user/admin notifications;
- excluded users are not polled or published;
- dead-token reminders are rate-limited;
- missing Xbox rarity blocks do not crash parsing;
- tokens and keys do not appear in logs or exception text;
- Steam account linking, presence, achievement parsing, rarity cache, and backfill;
- PSN credential health, linking, trophy parsing, progress cache, and publication;
- shared table rendering and Telegram message cleanup behavior.

## 16. Implementation status

Completed:

- core Xbox connection, polling, backfill, publishing, and stats;
- Steam linking, presence, achievement polling, backfill, and UI integration;
- PSN linking, credential health, trophy polling, backfill, and publication;
- user panel, admin panel, group commands, `/hltb`, daily summaries, auto-refreshing
  `/online`, auto-refreshing `/admin`, and system-message cleanup.

Open:

- integrate PSN into `/stats`, `/summary`, `/online`, and `/panel`;
- decide and implement optional game descriptions for `/hltb`;
- add an Xbox Live service status command or admin view;
- add GitHub Actions CI and production auto-deploy.

## Appendix A. Removed ideas

The following ideas were intentionally removed and should not be reintroduced without a
new design decision:

- OpenXBL as a data source.
- Storing broad third-party account keys per user.
- `/compare` and `/top`.
- Global rarity settings that apply to every chat.
- Separate visibility toggles for every platform.
- Live platform API calls from normal stats and panels.
