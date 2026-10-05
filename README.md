🇬🇧 English (this file) · 🇷🇺 [Русский](README.ru.md)

# Achievement Bot

A Telegram bot for a gaming chat: it posts the achievements and trophies members
earn on **Xbox, Steam and PlayStation Network**, keeps everyone's stats, and comes
with a Telegram Mini App. A non-commercial project for a community of 20-30 people,
run by one operator.

The rules, the architecture, current behavior and the full file tree are in
[CLAUDE.md](CLAUDE.md) — read it before changing the product or its architecture.
Open work lives in [Issues](https://github.com/MadOmsk/tg_achievement_bot/issues);
what changed in each release is in [changelog/](changelog/).

## What it does

**In a group chat**
- A card for every new achievement — icon, game, version played, progress in the
  game (`47/50`), rarity, description (secret ones behind a spoiler). Several at once
  become one digest; an anti-flood filter holds back a burst and sends it later as
  one message.
- Each member picks what gets posted — all, rare only, or nothing; "rare" means at or
  below the bot's rarity threshold (10% by default, set in `/admin`).
- Day and month reports on a schedule, plus `/stats`, `/online`, `/recent`, `/who`,
  `/hltb` (HowLongToBeat completion times) and a settings hub.

**In a private chat**
- A personal panel: connect and unlink accounts (up to three PSN accounts), switch
  posting per account, timezone, language, and which chats to post to — all with
  buttons, in one message.
- A live status while an account's history is read.

**Mini App** (`webapp/`) — a feed, profiles, the club, and a page per game:
achievements with progress, HowLongToBeat hours and description.

**For the operator** — `/admin`: health of the shared keys, the keys themselves,
limits, chats and their settings, users, exclusions, message cleanup.

The bot speaks Russian and English: a group follows its own setting, a private chat
the person's.

## Platforms

| | How a player connects | What has to be public |
|---|---|---|
| **Xbox** (One, Series, PC, 360) | signs in with Microsoft | nothing — the bot uses their own login |
| **Steam** | sends a profile link | the profile and "Game details" |
| **PSN** | sends an Online ID | trophies visible to "Everyone" |

Steam and PSN use one shared credential for the whole bot: a Steam Web API key
and the NPSSO of one PlayStation account. The operator sets both in `/admin`.

## Before you start

1. **A Telegram bot token** from [@BotFather](https://t.me/BotFather) → `BOT_TOKEN`.
2. **An app registration at [portal.azure.com](https://portal.azure.com)** — Xbox
   login does not work without it. Scopes `XboxLive.signin XboxLive.offline_access`
   and a redirect URI equal to `OAUTH_REDIRECT_URL`; it gives `AZURE_CLIENT_ID` and
   `AZURE_CLIENT_SECRET`.
3. **A domain with HTTPS** for `OAUTH_REDIRECT_URL` (e.g.
   `https://your-domain/auth/callback`). Microsoft accepts neither `localhost` nor
   `http://`. For local work a tunnel (Cloudflare Tunnel) gives `https://` at once;
   in production, nginx + Let's Encrypt.

## Configuration

`.env` (template: [.env.example](.env.example)).

| Variable | |
|---|---|
| `BOT_TOKEN`, `ADMIN_TG_IDS` | required; `ADMIN_TG_IDS` — Telegram ids of the operators, comma-separated |
| `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `OAUTH_REDIRECT_URL` | required, for Xbox login |
| `FERNET_KEY` | required; encrypts every stored token and key — back it up |
| `STEAM_API_KEY`, `ANTHROPIC_API_KEY` | optional, a first-run seed: after that the key lives in the database and is changed in `/admin` |
| `MINI_APP_URL` | optional; empty turns the Mini App buttons off |
| `DB_PATH`, `LOG_LEVEL`, poll intervals | optional |

Generate `FERNET_KEY`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

The PSN NPSSO is never in `.env`: it is entered in `/admin` and checked with a real
call before it is saved. Without a Steam key or an NPSSO those platforms are simply
unavailable; the rest of the bot works.

## Anthropic and its cost

The bot uses Claude Haiku (Anthropic API) to translate achievement descriptions a
platform only has in one language, and HowLongToBeat's game descriptions. Each text
is translated once and cached. Without a key nothing breaks: the text is shown in
the language it came in.

Anthropic only offers a **monthly** spend limit, set per workspace. Give each
environment — production, the test server, every developer — its own workspace with
its own key and limit, so one runaway test cannot spend everybody's budget, and the
Usage page shows who spent what.

## Local development

```bash
git clone https://github.com/MadOmsk/tg_achievement_bot
cd tg_achievement_bot
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
copy .env.example .env
```

`manage.ps1` runs the bot on your machine (on a server, systemd does):

```powershell
.\manage.ps1 start | stop | restart | status | logs [-Lines N]
.\manage.ps1 dashboard           # live status with hotkeys; manage.bat opens it too
.\manage.ps1 start -Test         # the second instance, from .env.test
.\manage.ps1 start -Test -Web    # plus the Mini App: Vite and a tunnel, MINI_APP_URL set for you
```

**Never give your local bot the production `BOT_TOKEN`:** two processes on one
token fight over Telegram's updates.

The Mini App on its own:

```bash
cd webapp
npm install
npm run dev      # vite
npm run build    # type check + production build
```

Tests and lint — no test may call a real platform or Telegram:

```bash
pytest
ruff check . && ruff format --check .
```

## Branches, servers and releases

| Branch | Server | Updated |
|---|---|---|
| `dev` | the developer's own machine | on every commit (local git hooks) |
| `prerelease` | the test server | by CI on every push |
| `main` | production | by CI when `prerelease` is merged into it |

CI runs the tests, both ruff checks and a Mini App build, and only then deploys:
`scripts/xbox-deploy.sh` backs up the database, fast-forwards, restarts and waits
for the bot to report itself up. GitHub holds only the deploy SSH key and host —
never `.env`, `FERNET_KEY`, a database or a platform credential.

**A release** is: release notes in `changelog/` (Russian, English, a short summary
for the announcement, notes for contributors), a short review, a rehearsal of new
migrations on a copy of production, then `prerelease` → `main` as a merge commit.
On start, production announces the new version in its chats with a link to the notes.

The version reads `A.B.C.D` — architecture, minor line, release number, newest
migration — and is shown at the end of `/help`.

## Contributing

1. **Work in a branch of your own.** It is yours: run your own bot from it with
   your own `.env` and your own keys (Anthropic included), and try whatever you
   like.
2. **Propose the result as a pull request into `prerelease`** — never into `main`.
3. Once merged, it is built and deployed to the test server. The repository's
   admin tests it and releases it to production (`prerelease` → `main`).

What a pull request should bring:
- what changed for players, in the notes of the **next** version
  (`changelog/<A.B.C>.*`) — a version already released is never edited;
- user-facing text only in `bot/locales/` (Russian and English, kept in parity by
  a test); code, comments, commits and issues in English;
- green tests and ruff; a new screen agreed first (`scripts/render_screen.py` draws
  any screen from real data and can send it to the admin's DM);
- new migrations, which the admin rehearses on a copy of production before the
  release.

Everything else — data model, platform quirks, publication rules — is in
[CLAUDE.md](CLAUDE.md).
