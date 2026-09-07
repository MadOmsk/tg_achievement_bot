from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from aiogram_i18n import I18nContext
from aiogram_i18n.cores.fluent_runtime_core import FluentRuntimeCore
from aiogram_i18n.managers import ConstManager
from cryptography.fernet import Fernet

from bot.config import Settings
from bot.db.repo import Database, Repo
from bot.i18n import DEFAULT_LOCALE, LOCALES_DIR
from bot.services.crypto import TokenCipher

FERNET_KEY = Fernet.generate_key().decode()


@pytest.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    db = await Database(tmp_path / "test.db").connect()
    try:
        yield db
    finally:
        await db.close()


@pytest.fixture
async def repo(database: Database) -> Repo:
    return Repo(database)


@pytest.fixture
def cipher() -> TokenCipher:
    return TokenCipher(FERNET_KEY)


@pytest.fixture
async def i18n() -> I18nContext:
    """A real Fluent core over bot/locales/ru, not a stub — this exercises
    the actual .ftl files (a typo or missing key fails the test the same
    way it would fail in production), same principle as using the real repo
    fixture above instead of mocking the database."""
    core = FluentRuntimeCore(path=LOCALES_DIR / "{locale}" / "LC_MESSAGES")
    await core.startup()
    return I18nContext(
        locale=DEFAULT_LOCALE,
        core=core,
        manager=ConstManager(DEFAULT_LOCALE),
        data={},
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        bot_token="123:test",  # type: ignore[arg-type]
        admin_tg_ids=[1],
        azure_client_id="client-id",
        azure_client_secret="client-secret",  # type: ignore[arg-type]
        oauth_redirect_url="http://localhost:8080/auth/callback",
        fernet_key=FERNET_KEY,  # type: ignore[arg-type]
        db_path=tmp_path / "test.db",
        token_refresh_margin=300,
    )
