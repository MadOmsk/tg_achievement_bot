# Achievement Bot

<p align="left">
  <img src="assets/logo.svg" alt="Achievement Bot logo" width="760">
</p>

Achievement Bot is a small-group Telegram bot that publishes game achievements and
trophies from chat members across Xbox, Steam, and PlayStation Network, with rarity
filters, personal stats, group summaries, admin controls, and HowLongToBeat lookup.

The project is built for a private, non-commercial gaming chat of roughly 20-30 people.
It favors predictable behavior, local caching, and explicit admin controls over broad
multi-tenant SaaS features.

## Features

- Publishes new achievements and trophies to subscribed Telegram chats.
- Supports Xbox, Xbox 360, Steam, and PSN data sources.
- Filters publication by per-chat rarity threshold, per-user-per-chat visibility mode,
  minimum gamerscore, and muted games.
- Sends digest messages when many achievements arrive at once.
- Keeps `/stats`, `/recent`, `/online`, `/summary`, `/panel`, and `/admin` backed by the
  local SQLite cache instead of live platform API calls.
- Provides daily group summaries, live-refreshing `/online`, and self-refreshing
  `/admin`.
- Offers `/hltb` search with cached HowLongToBeat completion times.
- Encrypts Xbox refresh tokens and shared PSN NPSSO secrets with Fernet.

## Architecture

The bot is an async Python application:

- **Telegram UI:** aiogram 3 handlers in `bot/handlers/`.
- **Business logic:** platform clients, stats, formatting, and publishing in
  `bot/services/` and `bot/poller/`.
- **Storage:** SQLite through `bot/db/repo.py`; SQL should not be written outside this
  layer.
- **OAuth callback:** aiohttp endpoint in `bot/web/oauth.py` for Microsoft login.
- **Scheduler:** APScheduler ticks for presence polling, achievement fetching, service
  health checks, cleanup jobs, and daily summaries.

Platform notes:

- Xbox login uses Microsoft OAuth and stores only an encrypted refresh token.
- Xbox rarity comes from Xbox Live achievement contract version 4 and requires polling a
  concrete title.
- Steam uses the official Steam Web API and a shared API key; users connect by profile
  link or SteamID64.
- PSN uses a shared NPSSO token through `psnawp`; this is reverse-engineered and may
  break if Sony changes private endpoints.

## Repository layout

```text
bot/
  main.py              application assembly and startup
  config.py            environment-based settings
  db/                  schema, migrations, and repository layer
  handlers/            aiogram UI layer
  services/            platform clients and business logic
  poller/              scheduled background jobs
  web/                 Microsoft OAuth callback
tests/                 pytest test suite with mocked platform responses
scripts/               one-off operational helpers
data/                  local SQLite database, ignored by git
logs/                  runtime logs, ignored by git
manage.ps1             local Windows process manager
```

See `STRUCTURE.md` for the full tracked tree and `SPEC.md` for the detailed design.

## Requirements

- Python 3.12+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A Microsoft Azure app registration for Xbox login:
  - scopes: `XboxLive.signin XboxLive.offline_access`
  - redirect URI: the same HTTPS URL used as `OAUTH_REDIRECT_URL`
- A public HTTPS callback URL for Microsoft OAuth
- Optional: Steam Web API key from `steamcommunity.com/dev/apikey`
- Optional: PSN NPSSO token configured from the admin panel

Microsoft does not accept plain `http://` or `localhost` redirect URLs for this flow.
Use a real HTTPS domain in production or an HTTPS tunnel for local development.

## Local development

```powershell
git clone https://github.com/MadOmsk/xbox_achievement_bot.git
cd xbox_achievement_bot
python -m venv .venv
.\.venv\Scripts\pip install -e .[dev]
copy .env.example .env
```

Generate a Fernet key:

```powershell
.\.venv\Scripts\python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Fill `.env` with at least:

```text
BOT_TOKEN=
ADMIN_TG_IDS=
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=
OAUTH_REDIRECT_URL=
FERNET_KEY=
```

Optional platform keys:

```text
STEAM_API_KEY=
```

Run the bot locally with the Windows process manager:

```powershell
.\manage.ps1 start
.\manage.ps1 status
.\manage.ps1 logs -Lines 100
.\manage.ps1 stop
```

For an interactive local status screen:

```powershell
.\manage.ps1 dashboard
```

Do not run the local bot and the production bot with the same Telegram token at the same
time. Telegram long polling will make both processes fight for updates.

## Checks

```powershell
.\.venv\Scripts\pytest
.\.venv\Scripts\ruff check .
.\.venv\Scripts\ruff format --check .
```

Tests must not call real Xbox, Steam, PSN, or Telegram APIs.

## Production deployment

The current production shape is a single VPS running:

- Ubuntu 24.04
- a dedicated unprivileged service user
- systemd service `xbox-bot.service`
- nginx with Let's Encrypt TLS
- the bot listening only on `127.0.0.1:8080` for the OAuth callback

Manual deployment is currently:

```bash
cd /opt/xbox_achievement_bot
git pull --ff-only
python -m pip install -e .
systemctl restart xbox-bot
journalctl -u xbox-bot -f
```

### Planned: GitHub Actions auto-deploy

Auto-deploy is intentionally not implemented yet. The next deployment step should be a
GitHub Actions workflow that:

1. runs tests and Ruff checks on every pull request and push;
2. deploys only from the protected production branch after checks pass;
3. connects to the VPS through SSH using a GitHub Actions secret deploy key;
4. runs `git pull --ff-only`, installs updated dependencies, applies migrations through
   normal application startup, and restarts `xbox-bot.service`;
5. never stores `.env`, `FERNET_KEY`, Telegram tokens, Azure secrets, Steam keys, or PSN
   NPSSO in the repository.

## Documentation

- `SPEC.md` - full product and architecture specification.
- `CLAUDE.md` - development rules and operational notes.
- `STRUCTURE.md` - current tracked file tree.

## Security notes

- `.env`, `data/`, logs, and database files are ignored by git.
- Xbox refresh tokens and the PSN NPSSO are encrypted before storage.
- Tokens and API keys must never be logged or included in exception text.
- `FERNET_KEY` must be backed up securely; losing it means connected users must reconnect.
- The Xbox and PSN integrations rely on undocumented or reverse-engineered platform
  behavior and may require maintenance if upstream services change.
