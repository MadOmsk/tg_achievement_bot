"""Where a catch-up window starts, and the hourly sweep that uses it (#82).

Two defects, one theme: nothing was asking Xbox about a game after the
person stopped playing it.

The window was measured from `presence_state.updated_at`, which the presence
poller rewrites on every tick — so "since we last looked" meant "since a
minute ago", `_played_since` found no candidate title, and startup catch-up
was a silent no-op on every account. And even with the window fixed it only
ran at startup, while a console uploads what was earned offline whenever it
next reaches the network.
"""

from __future__ import annotations

from datetime import timedelta

from bot.config import Settings
from bot.db.repo import AchievementRow, Repo
from bot.poller.catch_up import CatchUpPoller
from bot.poller.fetcher import catch_up_since
from bot.util import utcnow

TG_ID = 42
XUID = "xuid-catchup"
WINDOW_HOURS = 24


def _row(achievement_id: str, unlocked_at: str | None) -> AchievementRow:
    return AchievementRow(
        title_id="360",
        achievement_id=achievement_id,
        name=f"Achievement {achievement_id}",
        description=None,
        icon_url=None,
        unlocked_at=unlocked_at,
        gamerscore=10,
        rarity_percent=None,
        platform="xbox_360",
        title_name="Gears of War 3",
    )


async def _connected(repo: Repo, cipher) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await repo.save_refresh_token(TG_ID, cipher.encrypt("refresh"))
    await repo.link_xbox_account(TG_ID, XUID, "Mad Omsk", None)


async def test_the_window_starts_at_the_newest_stored_unlock(repo: Repo, cipher) -> None:
    await _connected(repo, cipher)
    earned = utcnow() - timedelta(hours=3)
    await repo.insert_new_achievements(
        XUID, [_row("a1", earned.isoformat(timespec="seconds"))], is_backfill=False
    )

    since = await catch_up_since(repo, XUID, WINDOW_HOURS)

    assert abs((since - earned).total_seconds()) < 2


async def test_an_account_with_nothing_stored_gets_the_window_floor(repo: Repo, cipher) -> None:
    """Not `None`: that has `_played_since` hand back the whole library, up
    to catchup_max_titles requests per account per pass, to publish nothing."""
    await _connected(repo, cipher)

    since = await catch_up_since(repo, XUID, WINDOW_HOURS)

    expected = utcnow() - timedelta(hours=WINDOW_HOURS)
    assert abs((since - expected).total_seconds()) < 2


async def test_a_long_idle_account_gets_the_floor_too(repo: Repo, cipher) -> None:
    await _connected(repo, cipher)
    await repo.insert_new_achievements(
        XUID,
        [_row("a1", (utcnow() - timedelta(days=400)).isoformat(timespec="seconds"))],
        is_backfill=False,
    )

    since = await catch_up_since(repo, XUID, WINDOW_HOURS)

    expected = utcnow() - timedelta(hours=WINDOW_HOURS)
    assert abs((since - expected).total_seconds()) < 2


async def test_the_window_ignores_presence_entirely(repo: Repo, cipher) -> None:
    """The regression this is all about. `presence_state.updated_at` is
    rewritten every tick, so a window taken from it is always minutes wide
    and no game ever looks freshly played."""
    await _connected(repo, cipher)
    earned = utcnow() - timedelta(hours=5)
    await repo.insert_new_achievements(
        XUID, [_row("a1", earned.isoformat(timespec="seconds"))], is_backfill=False
    )
    await repo.save_presence_state(XUID, "Online", "360", "Gears of War 3", changed=True)

    since = await catch_up_since(repo, XUID, WINDOW_HOURS)

    assert since < utcnow() - timedelta(hours=4)


class _FakeFetcher:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    async def catch_up(self, tg_id, xuid, gamertag, since, window_hours, max_titles):
        self.calls.append((tg_id, xuid))
        return 0, 0


def _settings(**kwargs) -> Settings:
    return Settings(
        bot_token="1:x",
        admin_tg_ids=[1],
        azure_client_id="x",
        azure_client_secret="x",
        oauth_redirect_url="https://example.test/auth/callback",
        fernet_key="x" * 44,
        **kwargs,
    )


async def test_the_hourly_sweep_waits_out_its_interval(repo: Repo, cipher) -> None:
    """Nothing runs in the first hour: startup catch-up has just swept
    everybody, and repeating it a minute later would be a request per
    account for nothing."""
    await _connected(repo, cipher)
    fetcher = _FakeFetcher()
    poller = CatchUpPoller(_settings(), repo, fetcher)  # type: ignore[arg-type]

    await poller.tick()

    assert fetcher.calls == []


async def test_the_hourly_sweep_takes_one_account_per_tick(repo: Repo, cipher) -> None:
    await _connected(repo, cipher)
    await repo.ensure_user(43, "second")
    await repo.save_refresh_token(43, cipher.encrypt("refresh"))
    await repo.link_xbox_account(43, "xuid-second", "Second", None)

    fetcher = _FakeFetcher()
    poller = CatchUpPoller(_settings(catchup_interval_minutes=0), repo, fetcher)  # type: ignore[arg-type]

    await poller.tick()
    assert len(fetcher.calls) == 1
    await poller.tick()
    assert len(fetcher.calls) == 2
    assert {xuid for _, xuid in fetcher.calls} == {XUID, "xuid-second"}


async def test_an_excluded_account_is_never_swept(repo: Repo, cipher) -> None:
    await _connected(repo, cipher)
    await repo._conn.execute("UPDATE users SET is_excluded = 1 WHERE tg_id = ?", (TG_ID,))
    await repo._conn.commit()

    fetcher = _FakeFetcher()
    poller = CatchUpPoller(_settings(catchup_interval_minutes=0), repo, fetcher)  # type: ignore[arg-type]

    await poller.tick()

    assert fetcher.calls == []


async def test_one_account_failing_does_not_stop_the_next_tick(repo: Repo, cipher) -> None:
    await _connected(repo, cipher)

    class _Angry(_FakeFetcher):
        async def catch_up(self, *args, **kwargs):
            self.calls.append((args[0], args[1]))
            raise RuntimeError("titlehub is having a day")

    fetcher = _Angry()
    poller = CatchUpPoller(_settings(catchup_interval_minutes=0), repo, fetcher)  # type: ignore[arg-type]

    await poller.tick()  # must not raise
    await poller.tick()

    assert len(fetcher.calls) == 2


async def test_dormant_xbox_account_uses_idle_interval(repo: Repo, cipher) -> None:
    await _connected(repo, cipher)
    twenty_days_ago = (utcnow() - timedelta(days=20)).isoformat()
    await repo._conn.execute(
        "UPDATE users SET last_online_at = ? WHERE tg_id = ?", (twenty_days_ago, TG_ID)
    )
    await repo._conn.execute(
        "UPDATE account_links SET linked_at = ? WHERE tg_id = ?", (twenty_days_ago, TG_ID)
    )
    await repo._conn.commit()

    poller = CatchUpPoller(_settings(), repo, _FakeFetcher())  # type: ignore[arg-type]
    [target] = await repo.pollable_users()
    assert poller._target_interval(target) == 1440 * 60  # 24 hours

    now_iso = utcnow().isoformat()
    await repo._conn.execute(
        "UPDATE users SET last_online_at = ? WHERE tg_id = ?", (now_iso, TG_ID)
    )
    await repo._conn.commit()
    [target] = await repo.pollable_users()
    assert poller._target_interval(target) == 60 * 60  # 1 hour
