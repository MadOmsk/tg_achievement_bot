from __future__ import annotations

import asyncio
import shutil
import socket
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import aiosqlite
import pytest
from aiogram_i18n import I18nContext
from aiogram_i18n.cores.fluent_runtime_core import FluentRuntimeCore
from aiogram_i18n.managers import ConstManager
from cryptography.fernet import Fernet

from bot.config import Settings
from bot.db.repo import Database, Repo
from bot.i18n import DEFAULT_LOCALE, LOCALES_DIR
from bot.poller import fetcher, psn_fetcher, steam_fetcher, steam_localization
from bot.services import title_catalog
from bot.services.crypto import TokenCipher
from bot.services.steam import achievements as steam_achievements
from bot.services.steam.auth import SteamAuth
from bot.services.stores import xbox_catalog

FERNET_KEY = Fernet.generate_key().decode()

# Tests never reach a real platform (CLAUDE.md, Tests): a name that is not
# this machine's is refused at once, and a test that reached for one fails at
# its end with the hosts — code that swallows a failed request (a store name
# is best-effort) would otherwise hide the call it should never have made.
_LOCAL = {"localhost", "127.0.0.1", "::1", "", None}
_getaddrinfo = socket.getaddrinfo


async def _no_store_name(appid: str, language: str) -> None:
    return None


async def _nothing(*args, **kwargs) -> None:
    return None


async def _no_addons(name: str) -> list[str]:
    return []


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    reached: list[str] = []

    def no_network(host, *args, **kwargs):
        name = host.decode() if isinstance(host, bytes) else host
        if name not in _LOCAL:
            reached.append(str(name))
            raise ConnectionRefusedError(f"a test reached for the network: {name}")
        return _getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    # A game's name as the Steam store spells it is a best-effort side
    # lookup no test is about but those that say so (they stub it again).
    for module in (steam_achievements, steam_localization, title_catalog):
        monkeypatch.setattr(module, "store_name", _no_store_name)
    # After publishing, a fetcher matches the game on HowLongToBeat and caches
    # its icons: errands of their own tests (`test_hltb_match`,
    # `test_achievement_icons`), which call them directly.
    for module in (fetcher, steam_fetcher, psn_fetcher):
        monkeypatch.setattr(module, "ensure_title_match", _nothing)
    monkeypatch.setattr(fetcher.achievement_icons, "pre_cache_icon", _nothing)
    # An Xbox collection also searches the add-ons sold alone: the errand of
    # `test_xbox_addons_alone`, which stubs it again.
    monkeypatch.setattr(xbox_catalog, "search_addons", _no_addons)
    yield
    if reached:
        pytest.fail(f"reached for the network: {sorted(set(reached))}", pytrace=False)


@pytest.fixture(scope="session")
def _db_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    template_dir = tmp_path_factory.mktemp("db_template")
    template_path = template_dir / "template.db"

    async def _init() -> None:
        db = await Database(template_path).connect()
        await db.close()

    asyncio.run(_init())
    return template_path


@pytest.fixture
async def database(tmp_path: Path, _db_template: Path) -> AsyncIterator[Database]:
    db_path = tmp_path / "test.db"
    shutil.copyfile(_db_template, db_path)
    db = Database(db_path)
    db._conn = await aiosqlite.connect(db_path)
    db._conn.row_factory = aiosqlite.Row
    await db._conn.execute("PRAGMA journal_mode = WAL")
    await db._conn.execute("PRAGMA foreign_keys = ON")
    await db._conn.execute("PRAGMA synchronous = OFF")
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
async def steam_auth(repo: Repo, cipher: TokenCipher) -> SteamAuth:
    """A configured SteamAuth, seeded from a fake env key — get_key()
    returns it with no network (check_alive is only in set_key/health)."""
    return SteamAuth(repo, cipher, env_key="fake-steam-key")


@pytest.fixture(scope="session")
def _shared_fluent_core() -> FluentRuntimeCore:
    core = FluentRuntimeCore(path=LOCALES_DIR / "{locale}" / "LC_MESSAGES")
    asyncio.run(core.startup())
    return core


@pytest.fixture
def i18n(_shared_fluent_core: FluentRuntimeCore) -> I18nContext:
    """A real Fluent core over bot/locales/ru, not a stub — this exercises
    the actual .ftl files (a typo or missing key fails the test the same
    way it would fail in production), same principle as using the real repo
    fixture above instead of mocking the database."""
    return I18nContext(
        locale=DEFAULT_LOCALE,
        core=_shared_fluent_core,
        manager=ConstManager(DEFAULT_LOCALE),
        data={},
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        bot_token="123:test",  # type: ignore[arg-type]
        superadmin_tg_ids=[1],
        azure_client_id="client-id",
        azure_client_secret="client-secret",  # type: ignore[arg-type]
        oauth_redirect_url="http://localhost:8080/auth/callback",
        fernet_key=FERNET_KEY,  # type: ignore[arg-type]
        db_path=tmp_path / "test.db",
        token_refresh_margin=300,
    )
