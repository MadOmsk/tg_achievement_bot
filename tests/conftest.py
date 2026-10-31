from __future__ import annotations

import asyncio
import os
import selectors
import socket
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import psycopg
import pytest
from aiogram_i18n import I18nContext
from aiogram_i18n.cores.fluent_runtime_core import FluentRuntimeCore
from aiogram_i18n.managers import ConstManager
from cryptography.fernet import Fernet

from bot.config import Settings
from bot.db.repo import Database, Repo
from bot.db.repo._games_db import GAMES
from bot.i18n import DEFAULT_LOCALE, LOCALES_DIR
from bot.poller import fetcher, psn_fetcher, steam_fetcher, steam_localization
from bot.services import game_art, title_catalog
from bot.services.crypto import TokenCipher
from bot.services.steam import achievements as steam_achievements
from bot.services.steam.auth import SteamAuth
from bot.services.stores import steam_store, xbox_catalog

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


async def _no_art(appids: list[str]) -> dict:
    return {}


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
    # A Steam collection also asks for the library art of now: the errand of
    # `test_steam_library_art`, which stubs it again.
    monkeypatch.setattr(steam_store, "library_art", _no_art)
    # A game's art kept on disk: `test_game_art`'s errand; signing stays off
    # (another test's app setup would otherwise leave it on for the rest).
    monkeypatch.setattr(game_art, "ensure", _nothing)
    monkeypatch.setattr(game_art, "_secret", None)
    yield
    if reached:
        pytest.fail(f"reached for the network: {sorted(set(reached))}", pytrace=False)


# The tests' own PostgreSQL database (#234): its schema is made once a run,
# and every table is emptied before each test. TEST_DATABASE_URL names it;
# on the dev machine that is the project's cluster on port 5433.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://localhost:5433/unlocked_tests?user=postgres"
)
TEST_SCHEMA = "app"


def _admin_url(url: str) -> str:
    """The same server, its maintenance database."""
    head, _, tail = url.rpartition("/")
    _name, sep, query = tail.partition("?")
    return f"{head}/postgres{sep}{query}"


def _event_loop() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    # psycopg's async mode needs a selector loop; Windows defaults to the
    # proactor one.
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


# Every table emptied and every id counter back at 1, in one call: a TRUNCATE
# of the eighty tables took most of a second a test.
_RESET_FUNCTION = f"""
CREATE OR REPLACE FUNCTION public.reset_test_data() RETURNS void LANGUAGE plpgsql AS $$
DECLARE r record;
BEGIN
  SET LOCAL session_replication_role = replica;
  FOR r IN SELECT schemaname, tablename FROM pg_tables
           WHERE schemaname IN ('{TEST_SCHEMA}', '{GAMES}') AND tablename <> 'schema_migrations'
  LOOP
    EXECUTE format('DELETE FROM %I.%I', r.schemaname, r.tablename);
  END LOOP;
  FOR r IN SELECT schemaname, sequencename FROM pg_sequences
           WHERE schemaname IN ('{TEST_SCHEMA}', '{GAMES}')
  LOOP
    EXECUTE format('ALTER SEQUENCE %I.%I RESTART', r.schemaname, r.sequencename);
  END LOOP;
END $$;
"""


@pytest.fixture(scope="session")
def _db_template() -> str:
    """The test database, made empty with today's schema, once a run."""

    async def _init() -> None:
        name = TEST_DATABASE_URL.rpartition("/")[2].partition("?")[0]
        admin = await psycopg.AsyncConnection.connect(
            _admin_url(TEST_DATABASE_URL), autocommit=True
        )
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            await admin.execute(f'CREATE DATABASE "{name}"')
        finally:
            await admin.close()
        db = await Database(TEST_DATABASE_URL, schema=TEST_SCHEMA).connect()
        await db.conn.executescript(_RESET_FUNCTION)
        await db.close()

    asyncio.run(_init(), loop_factory=_event_loop)
    return TEST_DATABASE_URL


@pytest.fixture
async def database(tmp_path: Path, _db_template: str) -> AsyncIterator[Database]:
    db = await Database(_db_template, schema=TEST_SCHEMA, data_dir=tmp_path).connect()
    await db.conn.executescript("BEGIN; SELECT public.reset_test_data(); COMMIT;")
    await db._seed_app_settings()
    try:
        yield db
    finally:
        # A background task a test left (a backfill, a notice) must not be
        # waiting on the connection as it closes: Windows' selector loop fails
        # on a socket closed under it.
        current = asyncio.current_task()
        leftover = [t for t in asyncio.all_tasks() if t is not current and not t.done()]
        for task in leftover:
            task.cancel()
        await asyncio.gather(*leftover, return_exceptions=True)
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
