🇬🇧 English (this file) · 🇷🇺 [Русский](README.ru.md)

# Achievement Bot

A Telegram bot that publishes chat members' achievements — Xbox, Steam, and
PlayStation Network — with rarity filters, personal stats, a daily summary, an
admin panel, and HowLongToBeat completion-time lookup. A non-commercial project
for a group of 20-30 people.

Engineering rules, architecture, current behavior, and the full file tree are all
in [CLAUDE.md](CLAUDE.md) — read it before making product or architecture changes.
Open work and proposals live in this repository's
[Issues](https://github.com/MadOmsk/xbox_achievement_bot/issues).

## Stack

Python 3.12+, aiogram 3, xbox-webapi-python, httpx, aiohttp, aiosqlite,
APScheduler, pydantic v2, cryptography (Fernet), howlongtobeatpy, psnawp.

## Before you start

The bot won't start, or won't be able to sign people in through Xbox, without
these three things — set up once, before the first run:

1. **A Telegram bot token** — create one with [@BotFather](https://t.me/BotFather)
   to get `BOT_TOKEN`.
2. **An app registration at [portal.azure.com](https://portal.azure.com) —
   mandatory**, Xbox login doesn't work at all without it. You need the
   `XboxLive.signin XboxLive.offline_access` scopes and a redirect URI matching
   `OAUTH_REDIRECT_URL` (see below); the registration gives you
   `AZURE_CLIENT_ID` and `AZURE_CLIENT_SECRET`.
3. **A domain with HTTPS** for `OAUTH_REDIRECT_URL` (e.g.
   `https://your-domain/auth/callback`). Microsoft only accepts an `https://`
   redirect URI — neither `localhost` nor plain `http://` work. For local
   development, a tunnel domain (Cloudflare Tunnel gives you `https://`
   immediately) works well; in production, a regular domain with a certificate
   (nginx + Let's Encrypt/certbot, as on this project's own server).

## Local development

```bash
git clone <repository>
cd xbox_achievement_bot
python -m venv .venv
.venv\Scripts\pip install -e .[dev]

copy .env.example .env
# fill in BOT_TOKEN, AZURE_CLIENT_ID/SECRET, OAUTH_REDIRECT_URL, FERNET_KEY
```

Generate `FERNET_KEY`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

`manage.ps1` manages the process on your own machine (the bot can't start
itself):

```powershell
.\manage.ps1 start | stop | restart | status | logs [-Lines N]
.\manage.ps1 dashboard   # a live-refreshing status view with hotkeys
```

Double-clicking `manage.bat` opens the same dashboard. Details in
[CLAUDE.md](CLAUDE.md)'s "Operations" section.

Tests and lint:

```bash
pytest
ruff check . && ruff format --check .
```

## Production

The bot runs on a VPS under systemd (`xbox-bot.service`, a dedicated
unprivileged user), behind nginx with Let's Encrypt. `manage.ps1` isn't used
there — systemd owns that role:

```bash
systemctl {start|stop|restart|status} xbox-bot
journalctl -u xbox-bot -f
```

Deploy is `git pull` in `/opt/xbox_achievement_bot` as the service user, then
`systemctl restart xbox-bot`. Infrastructure details are in
[CLAUDE.md](CLAUDE.md)'s "Operations" section.

**Never run `manage.ps1` on a home PC at the same time as the production
server** — two processes sharing one `BOT_TOKEN` fight over Telegram's updates.
`manage.ps1` is a local-development tool, not a leftover — it's still exactly
as needed as it always was.
