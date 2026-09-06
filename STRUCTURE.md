# Project structure

This is a concise map of the repository. `SPEC.md` explains product and architecture
decisions; `CLAUDE.md` keeps the development rules.

```text
.
├── .env.example              environment template; real .env is ignored
├── .gitattributes
├── .gitignore
├── CLAUDE.md                 development rules for agents and maintainers
├── README.md                 public project overview
├── SPEC.md                   product and architecture specification
├── STRUCTURE.md              this file
├── pyproject.toml            package metadata, dependencies, ruff, pytest
├── manage.ps1                local Windows process manager
├── manage.bat                double-click launcher for manage.ps1 dashboard
├── assets/
│   └── logo.svg              README logo
│
├── bot/                      application package
│   ├── __init__.py
│   ├── main.py               application assembly and startup
│   ├── config.py             pydantic-settings configuration
│   ├── lock.py               local single-instance guard
│   ├── util.py               shared helpers: UTC time, masking, formatting
│   │
│   ├── handlers/             aiogram UI layer; no SQL or platform API logic
│   │   ├── __init__.py
│   │   ├── admin.py           private admin panel
│   │   ├── chat.py            group commands: subscribe, stats, online, recent, summary
│   │   ├── connect.py         start, Xbox connect/disconnect, timezone flow
│   │   ├── hltb.py            HowLongToBeat search command
│   │   ├── keyboards.py       shared inline keyboards and edit helpers
│   │   ├── panel.py           private user panel
│   │   ├── psn.py             PSN connect/disconnect flow
│   │   └── steam.py           Steam connect/disconnect flow
│   │
│   ├── services/             business logic, clients, renderers
│   │   ├── __init__.py
│   │   ├── achievements.py     publication filters and message formatting
│   │   ├── admin_view.py       shared /admin renderer
│   │   ├── connect.py          Microsoft OAuth state and completion service
│   │   ├── crypto.py           Fernet encryption helpers
│   │   ├── hltb.py             HowLongToBeat wrapper and cache mapping
│   │   ├── message_log.py      Telegram request middleware for outgoing group messages
│   │   ├── models.py           shared achievement/trophy models
│   │   ├── notify.py           admin notifications
│   │   ├── online_view.py      shared /online renderer
│   │   ├── profile_links.py    platform profile URL builders
│   │   ├── rate_limiter.py     shared sliding-window limiter
│   │   ├── single_message.py   delete-then-send helper for singleton UI messages
│   │   ├── stats.py            cached stats aggregates
│   │   ├── tables.py           shared blockquote/list renderer
│   │   │
│   │   ├── psn/
│   │   │   ├── __init__.py
│   │   │   ├── achievements.py  PSN trophy fetch/cache logic
│   │   │   ├── auth.py          encrypted NPSSO storage and health checks
│   │   │   ├── client.py        async wrapper around psnawp
│   │   │   └── view.py          PSN trophy table renderer
│   │   ├── steam/
│   │   │   ├── __init__.py
│   │   │   ├── achievements.py  Steam unlocked achievements with schema/rarity cache
│   │   │   └── client.py        Steam Web API client
│   │   └── xbox/
│   │       ├── __init__.py
│   │       ├── auth.py          Microsoft/Xbox token handling
│   │       ├── client.py        Xbox Live client, retry, backoff, rate limits
│   │       └── models.py        Xbox Live response models
│   │
│   ├── poller/               scheduled background jobs
│   │   ├── __init__.py
│   │   ├── admin_refresh.py     self-refreshing admin panel
│   │   ├── cadence.py           shared presence debounce/interval math
│   │   ├── daily.py             scheduled and on-demand summaries
│   │   ├── fetcher.py           Xbox achievement polling and backfill
│   │   ├── message_cleanup.py   system-message cleanup
│   │   ├── online_refresh.py    self-refreshing /online messages
│   │   ├── presence.py          Xbox presence polling
│   │   ├── psn_fetcher.py       PSN trophy polling and backfill
│   │   ├── publisher.py         Telegram publication queue and digests
│   │   ├── reminders.py         dead-token reminders
│   │   ├── rows.py              ParsedAchievement to DB row conversion
│   │   ├── scheduler.py         APScheduler job assembly
│   │   ├── service_health.py    Steam/PSN shared credential checks
│   │   ├── steam_fetcher.py     Steam achievement polling and backfill
│   │   └── steam_presence.py    Steam presence polling
│   │
│   ├── web/
│   │   ├── __init__.py
│   │   └── oauth.py             Microsoft OAuth callback
│   │
│   └── db/
│       ├── __init__.py
│       ├── repo.py              data-access layer; SQL belongs here
│       ├── schema.sql           fresh database schema
│       └── migrations/          ordered schema migrations
│           ├── 001_daily_reports.sql
│           ├── 002_rarity_hidden.sql
│           ├── 003_chat_seen.sql
│           ├── 004_hltb_cache.sql
│           ├── 005_bot_messages.sql
│           ├── 006_hltb_platforms.sql
│           ├── 007_platform_links.sql
│           ├── 008_chat_overrides.sql
│           ├── 009_chat_settings_mandatory.sql
│           ├── 010_secret_achievements.sql
│           ├── 011_seen_achievements_tg_id.sql
│           ├── 012_hltb_url_and_image.sql
│           ├── 013_steam_achievement_cache.sql
│           ├── 014_steam_presence_state.sql
│           ├── 015_drop_show_x360.sql
│           ├── 016_rarity_mode_per_chat.sql
│           ├── 017_steam_presence_grace.sql
│           ├── 018_titles_icon_url.sql
│           ├── 019_digest_threshold_per_chat.sql
│           ├── 020_bot_messages_is_system.sql
│           ├── 021_online_auto_refresh.sql
│           ├── 022_message_dedup.sql
│           ├── 023_psn_trophies.sql
│           └── 024_show_profile_links.sql
│
├── scripts/                  one-off operational helpers
│   ├── backfill_hltb_platforms.py
│   ├── backfill_steam_titles.py
│   ├── db_status.py
│   └── reconcile_achievements.py
│
├── tests/                    pytest suite; no real external API calls
│   ├── conftest.py
│   ├── test_admin*.py
│   ├── test_auth.py
│   ├── test_chat_online.py
│   ├── test_client.py
│   ├── test_crypto.py
│   ├── test_daily.py
│   ├── test_filters.py
│   ├── test_hltb.py
│   ├── test_message*.py
│   ├── test_models.py
│   ├── test_online*.py
│   ├── test_panel.py
│   ├── test_poller.py
│   ├── test_profile_links.py
│   ├── test_psn*.py
│   ├── test_publisher.py
│   ├── test_rate_limiter.py
│   ├── test_recent.py
│   ├── test_service_health.py
│   ├── test_stats*.py
│   ├── test_steam*.py
│   ├── test_tables.py
│   └── test_util.py
│
├── data/                     runtime SQLite database, ignored by git
└── logs/                     runtime logs, ignored by git
```
