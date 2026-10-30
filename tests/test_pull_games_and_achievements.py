"""Tests for scripts/pull_games_and_achievements.py."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from bot.config import Settings
from bot.constants import Platform
from bot.db.repo import Database, Repo
from scripts.pull_games_and_achievements import (
    NoopPublisher,
    SyncConfig,
    clone_user_tables,
    prepare_sync_config,
    run_sync,
)

CLONE_SOURCE = "pull_clone_source"


@pytest.fixture
async def clone_source(database: Database, _db_template: str) -> AsyncIterator[Database]:
    """A second server's schema beside the test one, as a bot's start makes it."""
    await database.conn.execute(f"DROP SCHEMA IF EXISTS {CLONE_SOURCE} CASCADE")
    source = await Database(_db_template, schema=CLONE_SOURCE).connect()
    yield source
    await source.close()
    await database.conn.execute(f"DROP SCHEMA {CLONE_SOURCE} CASCADE")


@pytest.mark.asyncio
async def test_noop_publisher() -> None:
    pub = NoopPublisher()
    await pub.start()
    await pub.publish(1, "xuid", "gt", [])
    await pub.publish_flood_digest(1, 2, [])
    await pub.stop()


def test_prepare_sync_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "pull_games_and_achievements.py",
            "--schema",
            "target",
            "--clone-users-from",
            "source",
            "--platforms",
            "xbox,steam",
            "--users",
            "123,456",
            "--skip-achievements",
            "--skip-catalog",
            "--force",
            "--concurrency",
            "3",
            "--limit-titles",
            "5",
        ],
    )

    cfg = prepare_sync_config(settings=settings)
    assert cfg.target_schema == "target"
    assert cfg.clone_source_schema == "source"
    assert cfg.selected_platforms == {"xbox", "steam"}
    assert cfg.user_ids == [123, 456]
    assert cfg.skip_achievements is True
    assert cfg.skip_catalog is True
    assert cfg.force is True
    assert cfg.concurrency == 3
    assert cfg.limit_titles == 5
    assert cfg.translate is False


@pytest.mark.asyncio
async def test_clone_user_tables(database: Database, clone_source: Database) -> None:
    # Set up source and destination schemas with full schema
    src_repo = Repo(clone_source)
    await src_repo.ensure_user(111, username="user1", first_name="First1")
    await src_repo.link_xbox_account(
        await src_repo.person_id(111), "2533000000000001", "Gamer1", 1000
    )

    stats = await clone_user_tables(CLONE_SOURCE, database.conn)
    assert stats.get("users", 0) >= 1
    assert stats.get("accounts", 0) >= 1

    dst_repo = Repo(database)
    link = await dst_repo.get_platform_link(await dst_repo.person_id(111), "xbox")
    assert link is not None
    assert link.external_id == "2533000000000001"
    assert link.display_name == "Gamer1"

    # The id counter went past what came in: the next person is a new one.
    await dst_repo.ensure_user(112, username="user2", first_name="First2")
    assert await dst_repo.person_id(112) != await dst_repo.person_id(111)


@pytest.mark.asyncio
async def test_run_sync_flow(repo: Repo, _db_template: str) -> None:
    await repo.ensure_user(222, username="player", first_name="Player")
    await repo.link_xbox_account(await repo.person_id(222), "2533000000000002", "PlayerTag", 500)
    await repo.save_refresh_token(await repo.person_id(222), b"fake_encrypted_token")
    await repo.upsert_title("100", "Game One", Platform.XBOX_MODERN)
    person = await repo.person_id(222)

    fernet_val = Fernet.generate_key().decode()
    cfg = SyncConfig(
        target_schema="app",
        clone_source_schema=None,
        selected_platforms={"xbox"},
        user_ids=None,
        skip_achievements=False,
        skip_catalog=False,
        force=True,
        concurrency=1,
        limit_titles=1,
        translate=False,
        settings=MagicMock(
            fernet_key=MagicMock(get_secret_value=lambda: fernet_val),
            steam_api_key=None,
            anthropic_api_key=None,
        ),
        dsn=_db_template,
    )

    with (
        patch("scripts.pull_games_and_achievements.XboxAuthService") as mock_auth_cls,
        patch("scripts.pull_games_and_achievements.XboxClient"),
        patch("scripts.pull_games_and_achievements.Fetcher") as mock_fetcher_cls,
        patch("scripts.pull_games_and_achievements.TitleCatalogService") as mock_cat_cls,
    ):
        mock_auth = AsyncMock()
        mock_auth_cls.return_value = mock_auth

        mock_fetcher = AsyncMock()
        mock_fetcher.backfill.return_value = 10
        mock_fetcher_cls.return_value = mock_fetcher

        mock_cat = AsyncMock()
        mock_cat.ensure_title_achievements_fresh.return_value = [MagicMock()]
        mock_cat_cls.return_value = mock_cat

        await run_sync(cfg)

        mock_auth.start.assert_awaited_once()
        mock_fetcher.backfill.assert_awaited_once_with(person, "2533000000000002")
        mock_cat.ensure_title_achievements_fresh.assert_awaited_once_with(
            "xbox_modern", "100", force=True
        )
        mock_auth.close.assert_awaited_once()
