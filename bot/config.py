"""Application settings, read once from the environment (SPEC section 10)."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # `.env` unless BOT_ENV_FILE says otherwise (#52, 2026-09-12) — a
        # second instance for testing account takeover and relinking needs
        # its own token, its own database and its own chat, and must never
        # share a BOT_TOKEN with the live bot (two pollers on one token steal
        # each other's updates; see bot/lock.py). The lock itself already
        # follows `db_path`, so distinct env files are enough to run both.
        env_file=os.getenv("BOT_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # Telegram
    bot_token: SecretStr
    # The super-admins — the global operators (an "admin" is a narrower role
    # to come). NoDecode: without it pydantic-settings reads the env value as
    # JSON, and "1,2" is not JSON — a single id would arrive as a bare int
    # instead. `ADMIN_TG_IDS`, the variable's old name, is still read.
    superadmin_tg_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list,
        validation_alias=AliasChoices("superadmin_tg_ids", "admin_tg_ids"),
    )

    # Microsoft / Azure
    azure_client_id: str
    azure_client_secret: SecretStr
    oauth_redirect_url: str
    oauth_listen_host: str = "0.0.0.0"
    oauth_listen_port: int = 8080

    # Token encryption at rest
    fernet_key: SecretStr

    # Steam (optional — /connect_steam answers "not configured" without it;
    # unlike Xbox this needs no per-user OAuth, just one key for the whole
    # bot). Get one at https://steamcommunity.com/dev/apikey.
    #
    # As of #17 this is only a first-run *seed*: on first access SteamAuth
    # imports it once into app_settings (encrypted), and from then on the
    # admin panel owns it (set / change / clear, no restart). Leaving it set
    # here is harmless; clearing the key in the panel disables the seed.
    steam_api_key: SecretStr | None = None

    # Anthropic (optional — achievement-description translation only; nothing
    # else in the bot calls an LLM). Get one at console.anthropic.com. Never
    # logged, never surfaced in any bot-facing message — same handling as
    # every other secret here.
    anthropic_api_key: SecretStr | None = None

    # YouTube Data API v3 (optional — video guides for achievements from the
    # channels in services/youtube/guides.py). Only a first-run seed, as the
    # two keys above: the admin panel owns it afterwards. Google Cloud →
    # "YouTube Data API v3" → Credentials → API key.
    youtube_api_key: SecretStr | None = None

    # Email sign-in (#162) — optional: without a mail server the Mini App
    # simply does not offer it. `smtp_security` is "starttls" (port 587),
    # "ssl" (port 465) or "none" (a relay on the same machine).
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_security: str = "starttls"
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None
    # Development only: write sign-in codes to the log instead of sending mail.
    # Never on a server — a log is not a mailbox.
    email_log_codes: bool = False
    # Development only: an address typed in is taken as proved, no code at all —
    # anybody could sign in as anybody. Ignored whenever SMTP_HOST is set, so a
    # server that sends mail can never run this way by mistake.
    email_skip_code: bool = False

    # Poller intervals, seconds (SPEC 5.2, 5.3)
    presence_interval_in_game: int = 60
    presence_interval_online: int = 120
    presence_interval_offline: int = 300
    presence_interval_idle: int = 900
    achievement_poll_interval: int = 120
    psn_offline_poll_interval: int = 1800  # 30m when user is offline (issue #90)
    psn_dormant_poll_interval: int = 86400  # 24h when user is offline > 14 days
    token_refresh_margin: int = 300

    backfill_concurrency: int = 2

    # Catch-up after downtime (SPEC 5.8)
    catchup_publish_window_hours: int = 24
    catchup_max_titles: int = 20
    # …and on a slow loop while the bot is up (#82): a console uploads what
    # was earned offline when it next reaches the network, long after the
    # presence poller took its last look at that game. Hourly for active
    # accounts; dormant accounts (>14d inactive) are polled daily (1440m).
    catchup_interval_minutes: int = 60
    catchup_idle_threshold_days: int = 14
    catchup_idle_interval_minutes: int = 1440  # 24 hours

    db_path: Path = Path("data/bot.db")
    log_level: str = "INFO"
    tz: str = "Europe/Moscow"

    # Public HTTPS URL of the Mini App SPA (BotFather Main Mini App / menu
    # button / tunnel during local dev). Empty = Mini App entry disabled;
    # classic slash commands and chat posts keep working either way.
    mini_app_url: str | None = None

    @field_validator("superadmin_tg_ids", mode="before")
    @classmethod
    def _split_superadmin_ids(cls, value: object) -> object:
        """SUPERADMIN_TG_IDS is a comma-separated string in .env."""
        if isinstance(value, str):
            return [int(part) for part in value.split(",") if part.strip()]
        return value

    def is_superadmin(self, tg_id: int | None) -> bool:
        return tg_id is not None and tg_id in self.superadmin_tg_ids


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from .env
