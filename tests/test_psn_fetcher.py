"""poller/psn_fetcher.py: dedup, publish, backfill isolation and the tick's
own debounce (SPEC 9, M-PSN-2) — the PSN counterpart of
test_steam_fetcher.py. fetch_unlocked() is faked at the module boundary,
same as the rest of this project's poller tests fake their client layer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bot.config import Settings
from bot.db.repo import AchievementRow, Repo
from bot.poller import psn_fetcher as psn_fetcher_module
from bot.poller.psn_fetcher import PsnFetcher
from bot.services.crypto import TokenCipher
from bot.services.models import ParsedAchievement
from bot.services.psn.auth import PsnAuth

TG_ID = 42
ACCOUNT_ID = "acc-1"


def parsed(achievement_id: str, title_id: str = "NPWR00001_00") -> ParsedAchievement:
    return ParsedAchievement(
        achievement_id=achievement_id,
        title_id=title_id,
        title_name="Some Game",
        name=f"Trophy {achievement_id}",
        description=None,
        icon_url=None,
        unlocked_at=None,
        gamerscore=0,
        rarity_percent=42.0,
        platform="psn",
    )


class FakePublisher:
    def __init__(self) -> None:
        self.published: list[list[AchievementRow]] = []

    async def publish(self, tg_id, xuid, name, achievements, title_name=None) -> None:
        self.published.append(list(achievements))


async def _linked_user(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_platform_account(TG_ID, "psn", ACCOUNT_ID, "Gamer")


async def _configured_auth(repo: Repo, cipher: TokenCipher, monkeypatch) -> PsnAuth:
    async def _build(npsso: str) -> object:
        return object()

    monkeypatch.setattr("bot.services.psn.auth.build_client", _build)
    auth = PsnAuth(repo, cipher)
    await auth.set_npsso("fake-npsso", admin_id=1)
    return auth


async def test_poll_account_publishes_only_new_trophies(
    repo: Repo, cipher: TokenCipher, settings: Settings, monkeypatch
) -> None:
    await _linked_user(repo)
    auth = await _configured_auth(repo, cipher, monkeypatch)
    pool = [parsed("1"), parsed("2")]

    async def fake_fetch_unlocked(repo_, client, account_id, limit=None):
        return list(pool)

    monkeypatch.setattr(psn_fetcher_module, "fetch_unlocked", fake_fetch_unlocked)
    publisher = FakePublisher()
    fetcher = PsnFetcher(settings, repo, auth, publisher)  # type: ignore[arg-type]

    assert await fetcher.poll_account(TG_ID, ACCOUNT_ID, "Gamer") == 2
    # Same answer a tick later: nothing new, nothing published.
    assert await fetcher.poll_account(TG_ID, ACCOUNT_ID, "Gamer") == 0
    assert len(publisher.published) == 1

    pool.append(parsed("3"))
    assert await fetcher.poll_account(TG_ID, ACCOUNT_ID, "Gamer") == 1
    assert [a.achievement_id for a in publisher.published[1]] == ["3"]


async def test_backfill_publishes_nothing(
    repo: Repo, cipher: TokenCipher, settings: Settings, monkeypatch
) -> None:
    """The whole point of SPEC 5.6/9's backfill: the first link must be
    silent."""
    await _linked_user(repo)
    auth = await _configured_auth(repo, cipher, monkeypatch)
    seen_limit = []

    async def fake_fetch_unlocked(repo_, client, account_id, limit=None):
        seen_limit.append(limit)
        return [parsed("1"), parsed("2")]

    monkeypatch.setattr(psn_fetcher_module, "fetch_unlocked", fake_fetch_unlocked)
    publisher = FakePublisher()
    fetcher = PsnFetcher(settings, repo, auth, publisher)  # type: ignore[arg-type]

    stored = await fetcher.backfill(TG_ID, ACCOUNT_ID)

    assert stored == 2
    assert publisher.published == []
    assert seen_limit == [None]  # whole history, not just the recent window


async def test_tick_skips_an_account_polled_too_recently(
    repo: Repo, cipher: TokenCipher, settings: Settings, monkeypatch
) -> None:
    await _linked_user(repo)
    auth = await _configured_auth(repo, cipher, monkeypatch)
    await repo.touch_psn_poll_state(ACCOUNT_ID)
    calls = 0

    async def fake_fetch_unlocked(repo_, client, account_id, limit=None):
        nonlocal calls
        calls += 1
        return []

    monkeypatch.setattr(psn_fetcher_module, "fetch_unlocked", fake_fetch_unlocked)
    fetcher = PsnFetcher(settings, repo, auth, FakePublisher())  # type: ignore[arg-type]

    await fetcher.tick()

    assert calls == 0


async def test_tick_polls_a_due_account(
    repo: Repo, cipher: TokenCipher, settings: Settings, monkeypatch
) -> None:
    await _linked_user(repo)
    auth = await _configured_auth(repo, cipher, monkeypatch)
    stale = (datetime.now(UTC) - timedelta(hours=1)).isoformat(timespec="seconds")
    await repo._conn.execute(
        "INSERT INTO psn_poll_state (account_id, last_polled_at) VALUES (?, ?)",
        (ACCOUNT_ID, stale),
    )
    await repo._conn.commit()

    async def fake_fetch_unlocked(repo_, client, account_id, limit=None):
        return [parsed("1")]

    monkeypatch.setattr(psn_fetcher_module, "fetch_unlocked", fake_fetch_unlocked)
    publisher = FakePublisher()
    fetcher = PsnFetcher(settings, repo, auth, publisher)  # type: ignore[arg-type]

    await fetcher.tick()

    assert len(publisher.published) == 1
    state = await repo.psn_pollable_users()
    assert state[0].last_polled_at is not None


async def test_tick_does_nothing_when_psn_is_not_configured(
    repo: Repo, cipher: TokenCipher, settings: Settings, monkeypatch
) -> None:
    await _linked_user(repo)
    auth = PsnAuth(repo, cipher)  # never configured
    calls = 0

    async def fake_fetch_unlocked(repo_, client, account_id, limit=None):
        nonlocal calls
        calls += 1
        return []

    monkeypatch.setattr(psn_fetcher_module, "fetch_unlocked", fake_fetch_unlocked)
    fetcher = PsnFetcher(settings, repo, auth, FakePublisher())  # type: ignore[arg-type]

    await fetcher.tick()

    assert calls == 0


async def test_insert_new_achievements_psn_dedups_and_keeps_the_tier(repo: Repo) -> None:
    """The actual db/repo.py write path for the new column (SPEC 9,
    M-PSN-2) — INSERT OR IGNORE on (tg_id, platform, title_id,
    achievement_id) same as the Xbox/Steam siblings, trophy_type round-
    trips where they always leave it NULL."""
    await _linked_user(repo)
    row = AchievementRow(
        title_id="NPWR00001_00",
        achievement_id="1",
        name="Platinum",
        description=None,
        icon_url=None,
        unlocked_at="2026-09-06T10:00:00+00:00",
        gamerscore=0,
        rarity_percent=2.2,
        platform="psn",
        trophy_type="platinum",
    )

    first = await repo.insert_new_achievements_psn(TG_ID, ACCOUNT_ID, [row], is_backfill=False)
    second = await repo.insert_new_achievements_psn(TG_ID, ACCOUNT_ID, [row], is_backfill=False)

    assert len(first) == 1
    assert second == []  # already seen, same key as the first call
    recent = await repo.recent_achievements(ACCOUNT_ID, 5)
    assert recent[0].trophy_type == "platinum"


async def test_psn_pollable_users_falls_back_to_account_id_with_no_online_id(
    repo: Repo,
) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_platform_account(TG_ID, "psn", ACCOUNT_ID, None)

    [target] = await repo.psn_pollable_users()

    assert target.account_id == ACCOUNT_ID
    assert target.online_id is None
    assert target.last_polled_at is None
