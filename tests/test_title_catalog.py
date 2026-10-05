"""Tests for TitleCatalogService, title_achievements repo, and Mini App game details API."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from urllib.parse import urlencode

from aiohttp import web

from bot.config import Settings
from bot.constants import Platform
from bot.db.repo import (
    AchievementRow,
    Repo,
    TitleAchievementRow,
)
from bot.services.models import ParsedAchievement
from bot.services.title_catalog import TitleCatalogService
from bot.util import utcnow, utcnow_iso
from bot.web.mini_api import handle_game_details


def _signed_init_data(
    *, auth_date: int | None = None, user_id: int = 42, bot_token: str = "123456:ABC-DEF"
) -> str:
    user = json.dumps(
        {"id": user_id, "first_name": "Ada", "username": "ada", "language_code": "ru"},
        separators=(",", ":"),
    )
    pairs = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "user": user,
    }
    data_check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


async def test_repo_title_achievements_crud(repo: Repo) -> None:
    # 1. Upsert achievements into catalog
    rows = [
        TitleAchievementRow(
            platform=Platform.XBOX_MODERN,
            title_id="12345",
            achievement_id="ach_1",
            name_ru="Первое",
            name_en="First",
            description_ru="Описание",
            description_en="Description",
            icon_url="https://example.com/1.png",
            is_secret=False,
            gamerscore=10,
            rarity_percent=50.0,
        ),
        TitleAchievementRow(
            platform=Platform.XBOX_MODERN,
            title_id="12345",
            achievement_id="ach_2",
            name_ru="Второе",
            name_en="Second",
            description_ru="Описание 2",
            description_en="Description 2",
            icon_url="https://example.com/2.png",
            is_secret=True,
            gamerscore=25,
            rarity_percent=12.5,
        ),
    ]
    await repo.upsert_title_achievements(rows, complete=True)

    count = await repo.title_achievements_count(Platform.XBOX_MODERN, "12345")
    assert count == 2

    stored = await repo.get_title_achievements(Platform.XBOX_MODERN, "12345")
    assert len(stored) == 2
    assert stored[0].achievement_id == "ach_1"
    assert stored[0].name_ru == "Первое"
    assert stored[0].gamerscore == 10
    assert stored[1].achievement_id == "ach_2"
    assert stored[1].is_secret is True

    # 2. Check title checked_at timestamp
    await repo.upsert_title("12345", "Test Game", Platform.XBOX_MODERN)
    assert await repo.title_achievements_checked_at("12345") is None

    ts = (utcnow() - timedelta(hours=2)).isoformat(timespec="seconds")
    await repo.set_title_achievements_checked_at("12345", ts)
    assert await repo.title_achievements_checked_at("12345") == ts

    # 3. Check title groups
    groups = [
        ("default", "Main Game", 50, "Основная игра", "Main Game"),
        ("001", "DLC 1", 10, "Дополнение 1", "DLC 1"),
    ]
    await repo.save_title_groups("12345", groups)
    stored_groups = await repo.get_title_groups("12345")
    assert len(stored_groups) == 2
    assert stored_groups[0]["group_id"] == "001" or stored_groups[1]["group_id"] == "001"
    dlc = next(g for g in stored_groups if g["group_id"] == "001")
    assert dlc["name_ru"] == "Дополнение 1"
    assert dlc["total"] == 10


async def test_repo_title_achievements_with_user_unlocks(repo: Repo) -> None:
    # Populate title and catalog
    await repo.upsert_title("game_1", "Game One", Platform.XBOX_MODERN)
    rows = [
        TitleAchievementRow(
            platform=Platform.XBOX_MODERN,
            title_id="game_1",
            achievement_id="a1",
            name_en="Ach 1",
            name_ru="Ачивка 1",
        ),
        TitleAchievementRow(
            platform=Platform.XBOX_MODERN,
            title_id="game_1",
            achievement_id="a2",
            name_en="Ach 2",
            name_ru="Ачивка 2",
        ),
    ]
    await repo.upsert_title_achievements(rows, complete=True)

    # Link user and unlock only a1
    await repo.ensure_user(101, "player_one")
    await repo.link_xbox_account(101, "xuid_101", "PlayerOne", 0)

    unlocked_row = AchievementRow(
        title_id="game_1",
        achievement_id="a1",
        name="Ach 1",
        description="Desc",
        icon_url=None,
        unlocked_at="2026-09-21T10:00:00+00:00",
        gamerscore=10,
        rarity_percent=5.0,
        platform=Platform.XBOX_MODERN,
        title_name="Game One",
    )
    await repo.insert_new_achievements("xuid_101", [unlocked_row], is_backfill=False)

    checklist = await repo.get_title_achievements_with_user_unlocks(
        Platform.XBOX_MODERN, "game_1", "xuid_101"
    )
    assert len(checklist) == 2

    item_1 = next(item for item in checklist if item.achievement.achievement_id == "a1")
    assert item_1.is_unlocked is True
    assert item_1.unlocked_at == "2026-09-21T10:00:00+00:00"

    item_2 = next(item for item in checklist if item.achievement.achievement_id == "a2")
    assert item_2.is_unlocked is False
    assert item_2.unlocked_at is None


async def test_catalog_service_24h_debounce(repo: Repo) -> None:
    # Set up catalog with 1 achievement and checked_at 2 hours ago
    await repo.upsert_title("debounced_game", "Debounced Game", Platform.XBOX_MODERN)
    await repo.upsert_title_achievements(
        [
            TitleAchievementRow(
                platform=Platform.XBOX_MODERN,
                title_id="debounced_game",
                achievement_id="x1",
                name_en="X1",
            )
        ],
        complete=True,
    )
    two_hours_ago = (datetime.now(UTC) - timedelta(hours=2)).isoformat(timespec="seconds")
    await repo.set_title_achievements_checked_at("debounced_game", two_hours_ago)

    # Fake xbox client
    mock_xbox_client = AsyncMock()
    service = TitleCatalogService(
        repo=repo,
        xbox_client=mock_xbox_client,
    )

    # Call ensure_title_achievements_fresh without force -> within 24h, must skip API call
    achievements = await service.ensure_title_achievements_fresh(
        Platform.XBOX_MODERN, "debounced_game"
    )
    assert len(achievements) == 1
    mock_xbox_client.title_achievements_with_total.assert_not_called()

    # Call with force=True -> must call API
    mock_xbox_client.title_achievements_with_total.return_value = ([], 0)
    await service.ensure_title_achievements_fresh(
        Platform.XBOX_MODERN, "debounced_game", tg_id=42, force=True
    )
    assert mock_xbox_client.title_achievements_with_total.called


async def test_catalog_service_count_match_skips_translation(repo: Repo) -> None:
    # Set up Xbox game with 2 stored achievements, but checked_at is old (> 24h)
    await repo.upsert_title("xbox_game", "Xbox Game", Platform.XBOX_MODERN)
    await repo.upsert_title_achievements(
        [
            TitleAchievementRow(
                platform=Platform.XBOX_MODERN,
                title_id="xbox_game",
                achievement_id="x1",
                name_en="X1",
            ),
            TitleAchievementRow(
                platform=Platform.XBOX_MODERN,
                title_id="xbox_game",
                achievement_id="x2",
                name_en="X2",
            ),
        ],
        complete=True,
    )
    old_time = (datetime.now(UTC) - timedelta(hours=30)).isoformat(timespec="seconds")
    await repo.set_title_achievements_checked_at("xbox_game", old_time)

    mock_xbox_client = AsyncMock()
    parsed_dummy = [
        ParsedAchievement(
            achievement_id="x1",
            title_id="xbox_game",
            title_name="Xbox Game",
            name="X1",
            description="D1",
            icon_url=None,
            unlocked_at=None,
            gamerscore=10,
            rarity_percent=50.0,
            platform=Platform.XBOX_MODERN,
        ),
        ParsedAchievement(
            achievement_id="x2",
            title_id="xbox_game",
            title_name="Xbox Game",
            name="X2",
            description="D2",
            icon_url=None,
            unlocked_at=None,
            gamerscore=10,
            rarity_percent=50.0,
            platform=Platform.XBOX_MODERN,
        ),
    ]
    # Total count matches stored count (2 == 2)
    mock_xbox_client.title_achievements_with_total.return_value = (parsed_dummy, 2)

    mock_auth = AsyncMock()
    service = TitleCatalogService(
        repo=repo,
        xbox_client=mock_xbox_client,
        anthropic_auth=mock_auth,
    )

    result = await service.ensure_title_achievements_fresh(
        Platform.XBOX_MODERN, "xbox_game", tg_id=42
    )
    assert len(result) == 2
    # Count matched -> Claude translation was NOT called (0 tokens)
    mock_auth.bilingual_descriptions.assert_not_called()

    # But checked_at was updated to fresh time
    new_checked_at = await repo.title_achievements_checked_at("xbox_game")
    assert new_checked_at is not None
    assert new_checked_at > old_time


async def test_get_game_details_with_checklist_and_groups(repo: Repo, settings: Settings) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    app = web.Application()

    # Seed data
    await repo.ensure_user(42, "ada")
    await repo.link_platform_account(42, Platform.PSN, "psn_42", "AdaPSN")
    await repo.upsert_title("NPWR999", "Spider-Man", Platform.PSN)
    await repo.save_title_groups(
        "NPWR999",
        [
            ("default", "Base Game", 51, "Основная игра", "Base Game"),
            ("001", "The Heist", 7, "Ограбление", "The Heist"),
        ],
    )
    await repo.upsert_title_achievements(
        [
            TitleAchievementRow(
                platform=Platform.PSN,
                title_id="NPWR999",
                achievement_id="t1",
                name_ru="Трофей 1",
                name_en="Trophy 1",
                trophy_type="bronze",
                trophy_group_id="default",
            ),
            TitleAchievementRow(
                platform=Platform.PSN,
                title_id="NPWR999",
                achievement_id="t2",
                name_ru="Трофей DLC",
                name_en="Trophy DLC",
                trophy_type="silver",
                trophy_group_id="001",
            ),
        ],
        complete=True,
    )
    await repo.set_title_achievements_checked_at("NPWR999", utcnow_iso())

    catalog_service = TitleCatalogService(repo=repo)

    app["mini_repo"] = repo
    app["mini_title_catalog"] = catalog_service
    app["mini_settings"] = settings

    app.router.add_get(
        "/api/mini/games/{platform}/{title_id}",
        handle_game_details,
    )

    bot_token = settings.bot_token.get_secret_value()
    init_data = _signed_init_data(user_id=42, bot_token=bot_token)
    headers = {"X-Telegram-Init-Data": init_data}

    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        resp = await client.get("/api/mini/games/psn/NPWR999", headers=headers)
        assert resp.status == 200
        data = await resp.json()

        assert data["ok"] is True
        assert data["platform"] == "psn"
        assert data["title_id"] == "NPWR999"
        assert data["name"] == "Spider-Man"
        assert data["achievements_total"] == 2
        assert data["achievements_unlocked"] == 0
        assert data["completion_percent"] == 0.0

        # Check groups
        assert len(data["groups"]) == 2
        heist = next(g for g in data["groups"] if g["group_id"] == "001")
        assert heist["name_ru"] == "Ограбление"

        # Check achievements checklist
        assert len(data["achievements"]) == 2
        t1 = next(a for a in data["achievements"] if a["achievement_id"] == "t1")
        assert t1["name_ru"] == "Трофей 1"
        assert t1["trophy_type"] == "bronze"
        assert t1["trophy_group_id"] == "default"
        assert t1["is_unlocked"] is False
    finally:
        await client.close()


async def test_repo_catalog_helper_methods(repo: Repo) -> None:
    # 1. any_active_external_id
    assert await repo.any_active_external_id("psn") is None
    await repo.ensure_user(100, "user100")
    await repo.link_platform_account(100, Platform.PSN, "psn_ext_1", "PSNUser")
    assert await repo.any_active_external_id("psn") == "psn_ext_1"

    # 2. any_active_xbox_tg_id
    assert await repo.any_active_xbox_tg_id() is None
    await repo.link_xbox_account(100, "xuid_100", "XboxUser", 100)
    await repo.save_refresh_token(100, b"fake_enc")
    assert await repo.any_active_xbox_tg_id() == 100

    # 3. title_seen_platform
    assert await repo.title_seen_platform("game_1") is None
    await repo.insert_new_achievements(
        "xuid_100",
        [
            AchievementRow(
                title_id="game_1",
                achievement_id="a1",
                name="A1",
                description=None,
                icon_url=None,
                unlocked_at=utcnow_iso(),
                gamerscore=10,
                rarity_percent=5.0,
                platform="xbox_360",
            )
        ],
        is_backfill=False,
    )
    assert await repo.title_seen_platform("game_1") == "xbox_360"


async def test_refresh_xbox_updates_platform_to_360(repo: Repo) -> None:
    # Game was initially seeded as xbox_modern in titles and seen_achievements
    await repo.ensure_user(200, "user200")
    await repo.link_xbox_account(200, "xuid_200", "XboxUser200", 200)
    await repo.save_refresh_token(200, b"fake_enc")
    await repo.upsert_title("t_x360_fallback", "Gears 3", Platform.XBOX_MODERN)
    await repo.insert_new_achievements(
        "xuid_200",
        [
            AchievementRow(
                title_id="t_x360_fallback",
                achievement_id="ach_1",
                name="Gears Ach",
                description="Desc",
                icon_url=None,
                unlocked_at=utcnow_iso(),
                gamerscore=10,
                rarity_percent=None,
                platform="xbox_modern",
            )
        ],
        is_backfill=True,
    )

    # Initial state
    rec = await repo.title_record("t_x360_fallback")
    assert rec is not None
    assert rec["platform"] == "xbox_modern"
    assert await repo.title_seen_platform("t_x360_fallback") == "xbox_modern"

    # Mock client returns Xbox 360 achievements (contract 3 fallback)
    mock_xbox_client = AsyncMock()
    parsed_x360 = [
        ParsedAchievement(
            achievement_id="ach_1",
            title_id="t_x360_fallback",
            title_name="Gears of War 3",
            name="Gears Ach",
            description="Desc",
            icon_url=None,
            unlocked_at=None,
            gamerscore=10,
            rarity_percent=None,
            platform=Platform.XBOX_360,
        )
    ]
    mock_xbox_client.title_achievements_with_total.return_value = (parsed_x360, 1)
    mock_xbox_client.title_achievements.return_value = parsed_x360

    service = TitleCatalogService(repo=repo, xbox_client=mock_xbox_client)
    # Query with xbox_modern (as stored in titles)
    rows = await service.ensure_title_achievements_fresh(
        Platform.XBOX_MODERN, "t_x360_fallback", tg_id=200, force=True
    )
    assert len(rows) == 1
    assert rows[0].platform == "xbox_360"

    # Verify database updated
    rec_after = await repo.title_record("t_x360_fallback")
    assert rec_after is not None
    assert rec_after["platform"] == "xbox_360"
    assert rec_after["platforms"] == '["Xbox360"]'
    assert await repo.title_seen_platform("t_x360_fallback") == "xbox_360"

    stored_achs = await repo.get_title_achievements("xbox_360", "t_x360_fallback")
    assert len(stored_achs) == 1
    assert stored_achs[0].platform == "xbox_360"
    # Old xbox_modern catalog row should NOT exist
    stored_old = await repo.get_title_achievements("xbox_modern", "t_x360_fallback")
    assert len(stored_old) == 0
