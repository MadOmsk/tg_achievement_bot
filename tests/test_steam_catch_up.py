"""tests/test_steam_catch_up.py: SteamCatchUpPoller and steam_catch_up_since (#89)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import SecretStr

from bot.config import Settings
from bot.constants import Platform
from bot.db.repo import AchievementRow, Repo
from bot.poller.steam_catch_up import SteamCatchUpPoller, steam_catch_up_since
from bot.services.steam import client as steam_client
from bot.services.steam.auth import SteamAuth
from bot.services.steam.client import RecentlyPlayedGame, SteamApiError
from bot.util import utcnow

TG_ID = 42
STEAM_ID = "76561197960287930"


class FakeSteamFetcher:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str, str, str | None]] = []

    async def poll_title(
        self,
        tg_id: int,
        steam_id: str,
        persona_name: str,
        appid: str,
        game_name: str | None,
        **kwargs,
    ) -> int:
        self.calls.append((tg_id, steam_id, persona_name, appid, game_name))
        return 1


async def _linked_steam_user(
    repo: Repo, tg_id: int = TG_ID, steam_id: str = STEAM_ID, name: str = "Gabe"
) -> None:
    await repo.ensure_user(tg_id, name.lower())
    await repo.link_platform_account(tg_id, "steam", steam_id, name)


def _settings(**kwargs) -> Settings:
    base = {
        "bot_token": SecretStr("123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"),
        "admin_tg_ids": "1",
        "azure_client_id": "fake",
        "azure_client_secret": SecretStr("fake"),
        "oauth_redirect_url": "https://example.com",
        "fernet_key": SecretStr("A" * 43 + "="),
        "steam_api_key": SecretStr("fake-key"),
        "catchup_publish_window_hours": 24,
        "catchup_interval_minutes": 60,
    }
    base.update(kwargs)
    return Settings.model_validate(base)


async def test_steam_catch_up_since_with_no_unlocks_returns_floor(repo: Repo) -> None:
    floor_before = utcnow() - timedelta(hours=24)
    since = await steam_catch_up_since(repo, STEAM_ID, window_hours=24)
    floor_after = utcnow() - timedelta(hours=24)
    assert floor_before <= since <= floor_after


async def test_steam_catch_up_since_uses_latest_unlock_when_newer_than_floor(repo: Repo) -> None:
    recent = utcnow() - timedelta(hours=2)
    await repo.insert_new_achievements_steam(
        TG_ID,
        STEAM_ID,
        [
            AchievementRow(
                title_id="550",
                achievement_id="ach1",
                name="Test Ach",
                description=None,
                icon_url=None,
                unlocked_at=recent.isoformat(),
                gamerscore=0,
                rarity_percent=50.0,
                platform=Platform.STEAM,
            )
        ],
        is_backfill=False,
    )

    since = await steam_catch_up_since(repo, STEAM_ID, window_hours=24)
    assert abs((since - recent).total_seconds()) < 2.0


async def test_steam_catch_up_since_floors_at_window_when_unlock_is_older(repo: Repo) -> None:
    ancient = utcnow() - timedelta(days=30)
    await repo.insert_new_achievements_steam(
        TG_ID,
        STEAM_ID,
        [
            AchievementRow(
                title_id="550",
                achievement_id="ach1",
                name="Ancient Ach",
                description=None,
                icon_url=None,
                unlocked_at=ancient.isoformat(),
                gamerscore=0,
                rarity_percent=50.0,
                platform=Platform.STEAM,
            )
        ],
        is_backfill=False,
    )

    floor_before = utcnow() - timedelta(hours=24)
    since = await steam_catch_up_since(repo, STEAM_ID, window_hours=24)
    floor_after = utcnow() - timedelta(hours=24)
    assert floor_before <= since <= floor_after


async def test_tick_does_nothing_when_steam_not_configured(repo: Repo, cipher) -> None:
    unconfigured_auth = SteamAuth(repo, cipher)
    fetcher = FakeSteamFetcher()
    poller = SteamCatchUpPoller(_settings(), repo, fetcher, unconfigured_auth)  # type: ignore[arg-type]

    await poller.tick()
    assert fetcher.calls == []


async def test_hourly_sweep_waits_out_its_interval(repo: Repo, steam_auth) -> None:
    await _linked_steam_user(repo)
    fetcher = FakeSteamFetcher()
    poller = SteamCatchUpPoller(_settings(), repo, fetcher, steam_auth)  # type: ignore[arg-type]

    await poller.tick()
    assert fetcher.calls == []


async def test_hourly_sweep_takes_one_account_per_tick(repo: Repo, steam_auth, monkeypatch) -> None:
    await _linked_steam_user(repo, TG_ID, STEAM_ID, "Gabe")
    await _linked_steam_user(repo, 43, "76561197981065056", "Second")

    now_ts = int(datetime.now(UTC).timestamp())

    async def fake_recently_played(api_key, steam_id, count=10):
        return [
            RecentlyPlayedGame(
                appid="550",
                name="L4D2",
                playtime_2weeks=10,
                playtime_forever=100,
                last_played=now_ts,
            )
        ]

    monkeypatch.setattr(steam_client, "get_recently_played_games", fake_recently_played)

    fetcher = FakeSteamFetcher()
    poller = SteamCatchUpPoller(_settings(catchup_interval_minutes=0), repo, fetcher, steam_auth)  # type: ignore[arg-type]

    await poller.tick()
    assert len(fetcher.calls) == 1
    await poller.tick()
    assert len(fetcher.calls) == 2
    assert {sid for _, sid, _, _, _ in fetcher.calls} == {STEAM_ID, "76561197981065056"}


async def test_an_excluded_steam_account_is_never_swept(repo: Repo, steam_auth) -> None:
    await _linked_steam_user(repo)
    await repo._conn.execute("UPDATE users SET is_excluded = 1 WHERE tg_id = ?", (TG_ID,))
    await repo._conn.commit()

    fetcher = FakeSteamFetcher()
    poller = SteamCatchUpPoller(_settings(catchup_interval_minutes=0), repo, fetcher, steam_auth)  # type: ignore[arg-type]

    await poller.tick()
    assert fetcher.calls == []


async def test_one_account_failing_does_not_stop_the_next_tick(
    repo: Repo, steam_auth, monkeypatch
) -> None:
    await _linked_steam_user(repo, TG_ID, STEAM_ID, "Gabe")
    await _linked_steam_user(repo, 43, "76561197981065056", "Second")

    async def fake_recently_played(api_key, steam_id, count=10):
        if steam_id == STEAM_ID:
            raise RuntimeError("Steam exploded")
        return [
            RecentlyPlayedGame(
                appid="550",
                name="L4D2",
                playtime_2weeks=10,
                playtime_forever=100,
                last_played=int(datetime.now(UTC).timestamp()),
            )
        ]

    monkeypatch.setattr(steam_client, "get_recently_played_games", fake_recently_played)

    fetcher = FakeSteamFetcher()
    poller = SteamCatchUpPoller(_settings(catchup_interval_minutes=0), repo, fetcher, steam_auth)  # type: ignore[arg-type]

    await poller.tick()  # must not raise
    await poller.tick()
    assert len(fetcher.calls) == 1
    assert fetcher.calls[0][1] == "76561197981065056"


async def test_catch_up_target_filters_games_by_last_played(
    repo: Repo, steam_auth, monkeypatch
) -> None:
    await _linked_steam_user(repo)

    now = utcnow()
    now_ts = int(now.timestamp())
    old_ts = int((now - timedelta(days=2)).timestamp())  # 48h ago, older than 24h window

    async def fake_recently_played(api_key, steam_id, count=10):
        return [
            RecentlyPlayedGame(
                appid="550",
                name="L4D2 (old)",
                playtime_2weeks=10,
                playtime_forever=100,
                last_played=old_ts,
            ),
            RecentlyPlayedGame(
                appid="730",
                name="CS2 (fresh)",
                playtime_2weeks=30,
                playtime_forever=200,
                last_played=now_ts,
            ),
        ]

    monkeypatch.setattr(steam_client, "get_recently_played_games", fake_recently_played)

    fetcher = FakeSteamFetcher()
    poller = SteamCatchUpPoller(_settings(), repo, fetcher, steam_auth)  # type: ignore[arg-type]

    targets = await repo.steam_pollable_users()
    checked, published = await poller.catch_up_target(targets[0])

    assert checked == 1
    assert published == 1
    assert len(fetcher.calls) == 1
    assert fetcher.calls[0][3] == "730"
    assert fetcher.calls[0][4] == "CS2 (fresh)"


async def test_catch_up_target_handles_steam_api_error(repo: Repo, steam_auth, monkeypatch) -> None:
    await _linked_steam_user(repo)

    async def fake_recently_played(api_key, steam_id, count=10):
        raise SteamApiError("Steam service error")

    monkeypatch.setattr(steam_client, "get_recently_played_games", fake_recently_played)

    fetcher = FakeSteamFetcher()
    poller = SteamCatchUpPoller(_settings(), repo, fetcher, steam_auth)  # type: ignore[arg-type]

    targets = await repo.steam_pollable_users()
    checked, published = await poller.catch_up_target(targets[0])

    assert checked == 0
    assert published == 0
    assert fetcher.calls == []


async def test_dormant_steam_account_uses_idle_interval(repo: Repo, steam_auth) -> None:
    """An account inactive for >14 days is given the 24h idle interval instead of 1h."""
    await _linked_steam_user(repo)
    # Mark user as last online 20 days ago, and link 20 days ago
    twenty_days_ago = (utcnow() - timedelta(days=20)).isoformat()
    await repo._conn.execute(
        "UPDATE users SET last_online_at = ? WHERE tg_id = ?", (twenty_days_ago, TG_ID)
    )
    await repo._conn.execute(
        "UPDATE account_links SET linked_at = ? WHERE tg_id = ?", (twenty_days_ago, TG_ID)
    )
    await repo._conn.commit()

    poller = SteamCatchUpPoller(_settings(), repo, FakeSteamFetcher(), steam_auth)  # type: ignore[arg-type]
    [target] = await repo.steam_pollable_users()
    assert poller._target_interval(target) == 1440 * 60  # 24 hours

    # But an active user uses the normal 1h interval
    now_iso = utcnow().isoformat()
    await repo._conn.execute(
        "UPDATE users SET last_online_at = ? WHERE tg_id = ?", (now_iso, TG_ID)
    )
    await repo._conn.commit()
    [target] = await repo.steam_pollable_users()
    assert poller._target_interval(target) == 60 * 60  # 1 hour
