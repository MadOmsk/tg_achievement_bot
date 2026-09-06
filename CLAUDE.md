# CLAUDE.md

## Project

Achievement Bot is a Telegram bot for a small gaming community. It publishes
achievements and trophies from Xbox, Steam, and PlayStation Network accounts, with
rarity filters, cached stats, admin controls, daily summaries, and HowLongToBeat lookup.

Read `SPEC.md` before making product or architecture changes. It is the source of truth
for current behavior, invariants, and open work. Keep the project working after every
change.

## Stack

- Python 3.12+
- aiogram 3
- aiohttp, httpx, aiosqlite
- APScheduler
- pydantic v2 and pydantic-settings
- cryptography Fernet
- xbox-webapi-python, Steam Web API, psnawp, howlongtobeatpy
- pytest, pytest-asyncio, ruff

## Layout

```text
bot/
  main.py          application assembly
  config.py        environment settings
  util.py          shared helpers
  handlers/        aiogram UI layer only
  services/        business logic, clients, renderers
  poller/          scheduled background jobs
  web/             Microsoft OAuth callback
  db/
    schema.sql     fresh database schema
    migrations/    ordered schema migrations
    repo.py        data-access layer; no SQL elsewhere
tests/             mocked pytest suite
scripts/           operational helpers
data/              ignored runtime database
logs/              ignored runtime logs
manage.ps1         local Windows process manager
```

See `STRUCTURE.md` for the full tracked tree.

## Local run

Use `manage.ps1` locally:

```powershell
.\manage.ps1 start
.\manage.ps1 stop
.\manage.ps1 restart
.\manage.ps1 status
.\manage.ps1 logs -Lines 100
.\manage.ps1 dashboard
```

Production runs under systemd (`xbox-bot.service`) behind nginx. Do not run local and
production bots with the same `BOT_TOKEN` at the same time.

## Engineering rules

- Keep handlers thin. They call services and repository methods; they do not contain
  raw SQL or platform API logic.
- Keep all SQL in `bot/db/repo.py`, schema files, and migrations.
- Platform clients must not know about Telegram.
- Normal UI reads (`/stats`, `/recent`, `/online`, `/summary`, `/panel`, `/admin`) use
  cached database state, not live platform calls. Explicit manual refresh actions are
  the exception.
- Everything async must stay non-blocking. Wrap synchronous libraries with
  `asyncio.to_thread`.
- Handle expected external failures as states: private profiles, dead tokens, 429s,
  timeouts, empty responses, and upstream outages must not crash a poller tick.
- Pollers isolate failures per user/account or per small API batch.
- Do not add dependencies unless they are clearly needed.
- Do not leave stubs or TODO placeholders instead of implementation.

## Identity and publication invariants

- `tg_id` is the cross-platform owner key.
- Xbox XUID is stable for Xbox, but cross-platform aggregation must not use XUID.
- Insert only unlocked achievements/trophies into `seen_achievements`.
- First-connect backfill never publishes historical achievements.
- Rarity thresholds are per chat.
- Visibility mode is per user per chat: `all`, `rare`, or `hidden`.
- Platforms without rarity data, currently Xbox 360, are not filtered out only because
  rarity is missing.
- Admin-excluded users are not polled, published, or included in summaries.

## Secrets

- Never commit `.env`, databases, logs, tokens, API keys, NPSSO values, or backups.
- Store Xbox refresh tokens encrypted with Fernet.
- Store shared PSN secrets encrypted.
- Never log raw token-bearing payloads, authorization headers, or URLs with API keys.
- Mask secrets before logging structured data.
- Save a new Xbox refresh token before making the request that required the refresh.
- Serialize Xbox refresh attempts per user.

## Tests

Run the smallest relevant checks:

```powershell
.\.venv\Scripts\pytest
.\.venv\Scripts\ruff check .
.\.venv\Scripts\ruff format --check .
```

Real Xbox, Steam, PSN, HLTB, and Telegram calls are forbidden in tests. Mock at service
boundaries.

Core coverage should include deduplication, backfill behavior, rarity filtering, token
refresh ordering, dead-token handling, excluded users, missing rarity fields, secret
masking, platform linking, pollers, publication, table rendering, and message cleanup.

## Style

- Code names and comments: English.
- Bot messages: Russian.
- Comment why, not what.
- Prefer precise, small changes that preserve existing behavior.
