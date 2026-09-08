"""poller/psn_fetcher.py: publish, backfill gating and the tick's own
debounce + #21 backfill gate (SPEC 9, M-PSN-2). sync_account() is faked at
the module boundary, same as the rest of this project's poller tests fake
their client/service layer. The scan/persist/ordering itself is covered by
test_psn_achievements.py against the real repo."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bot.config import Settings
from bot.db.repo import AchievementRow, Repo
from bot.poller import psn_fetcher as psn_fetcher_module
from bot.poller.psn_fetcher import PsnFetcher
from bot.services.crypto import TokenCipher
from bot.services.psn.achievements import PsnSyncOutcome
from bot.services.psn.auth import PsnAuth

TG_ID = 42
ACCOUNT_ID = "acc-1"


def row(achievement_id: str, title_id: str = "NPWR00001_00") -> AchievementRow:
    return AchievementRow(
        title_id=title_id,
        achievement_id=achievement_id,
        name=f"Trophy {achievement_id}",
        description=None,
        icon_url=None,
        unlocked_at=None,
        gamerscore=0,
        rarity_percent=42.0,
        platform="psn",
        title_name="Some Game",
    )


class FakePublisher:
    def __init__(self) -> None:
        self.published: list[list[AchievementRow]] = []

    async def publish(self, tg_id, xuid, name, achievements, title_name=None) -> None:
        self.published.append(list(achievements))


def _fake_sync(monkeypatch, outcomes):
    """`outcomes` is either a single PsnSyncOutcome (returned every call) or a
    list consumed one per call. Records the kwargs each call was made with."""
    calls: list[dict] = []
    queue = list(outcomes) if isinstance(outcomes, list) else None

    async def fake_sync_account(repo_, client, tg_id, account_id, *, is_backfill, limit=None):
        calls.append(
            {
                "tg_id": tg_id,
                "account_id": account_id,
                "is_backfill": is_backfill,
                "limit": limit,
            }
        )
        if queue is not None:
            return queue.pop(0)
        return outcomes

    monkeypatch.setattr(psn_fetcher_module, "sync_account", fake_sync_account)
    return calls


async def _linked_user(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_platform_account(TG_ID, "psn", ACCOUNT_ID, "Gamer")


async def _configured_auth(repo: Repo, cipher: TokenCipher, monkeypatch) -> PsnAuth:
    async def _build(npsso: str) -> object:
        return object()

    async def _alive(client: object) -> bool:
        return True

    monkeypatch.setattr("bot.services.psn.auth.build_client", _build)
    monkeypatch.setattr("bot.services.psn.auth.check_alive", _alive)
    auth = PsnAuth(repo, cipher)
    await auth.set_npsso("fake-npsso", admin_id=1)
    return auth


def _fake_level(monkeypatch, level: int = 7) -> None:
    async def _account_trophy_level(client: object, account_id: str) -> int:
        return level

    monkeypatch.setattr(psn_fetcher_module, "account_trophy_level", _account_trophy_level)


async def test_poll_account_publishes_what_sync_account_returns(
    repo: Repo, cipher: TokenCipher, settings: Settings, monkeypatch
) -> None:
    await _linked_user(repo)
    auth = await _configured_auth(repo, cipher, monkeypatch)
    _fake_level(monkeypatch)
    _fake_sync(
        monkeypatch,
        [
            PsnSyncOutcome(new_rows=[row("1"), row("2")]),
            PsnSyncOutcome(),  # nothing new
            PsnSyncOutcome(new_rows=[row("3")]),
        ],
    )
    publisher = FakePublisher()
    fetcher = PsnFetcher(settings, repo, auth, publisher)  # type: ignore[arg-type]

    assert await fetcher.poll_account(TG_ID, ACCOUNT_ID, "Gamer") == 2
    # Found new trophies — level gets refreshed (Follow-up 2026-09-06).
    link = await repo.get_platform_link(TG_ID, "psn")
    assert link is not None and link.psn_trophy_level == 7

    assert await fetcher.poll_account(TG_ID, ACCOUNT_ID, "Gamer") == 0
    assert len(publisher.published) == 1

    assert await fetcher.poll_account(TG_ID, ACCOUNT_ID, "Gamer") == 1
    assert [a.achievement_id for a in publisher.published[1]] == ["3"]


async def test_backfill_marks_done_and_returns_the_private_titles(
    repo: Repo, cipher: TokenCipher, settings: Settings, monkeypatch
) -> None:
    await _linked_user(repo)
    auth = await _configured_auth(repo, cipher, monkeypatch)
    _fake_level(monkeypatch, level=3)
    calls = _fake_sync(
        monkeypatch,
        PsnSyncOutcome(new_rows=[row("1"), row("2")], private_title_ids=["NPWR00009_00"]),
    )
    publisher = FakePublisher()
    fetcher = PsnFetcher(settings, repo, auth, publisher)  # type: ignore[arg-type]

    # Before: the gate is closed, tick() would not touch this account.
    [target] = await repo.psn_pollable_users()
    assert target.backfill_done is False

    result = await fetcher.backfill(TG_ID, ACCOUNT_ID)

    assert result.stored == 2
    assert result.private_title_ids == ["NPWR00009_00"]
    assert publisher.published == []  # backfill never publishes
    assert calls[0]["is_backfill"] is True
    assert calls[0]["limit"] is None  # whole history, not just the recent window
    # After: the gate is open — the regular poller may now poll it (#21).
    [target] = await repo.psn_pollable_users()
    assert target.backfill_done is True
    link = await repo.get_platform_link(TG_ID, "psn")
    assert link is not None and link.psn_trophy_level == 3


async def test_tick_skips_an_account_whose_backfill_has_not_finished(
    repo: Repo, cipher: TokenCipher, settings: Settings, monkeypatch
) -> None:
    """#21: a freshly-linked account has no psn_poll_state row yet, so its
    backfill_done reads False and tick() must leave it alone — polling it
    would race the in-flight backfill and dump the whole history into chat."""
    await _linked_user(repo)
    auth = await _configured_auth(repo, cipher, monkeypatch)
    calls = _fake_sync(monkeypatch, PsnSyncOutcome())
    fetcher = PsnFetcher(settings, repo, auth, FakePublisher())  # type: ignore[arg-type]

    await fetcher.tick()

    assert calls == []


async def test_tick_polls_a_due_account_once_backfill_is_done(
    repo: Repo, cipher: TokenCipher, settings: Settings, monkeypatch
) -> None:
    await _linked_user(repo)
    auth = await _configured_auth(repo, cipher, monkeypatch)
    _fake_level(monkeypatch)
    stale = (datetime.now(UTC) - timedelta(hours=1)).isoformat(timespec="seconds")
    await repo._conn.execute(
        "INSERT INTO psn_poll_state (account_id, last_polled_at, backfill_done) VALUES (?, ?, 1)",
        (ACCOUNT_ID, stale),
    )
    await repo._conn.commit()
    _fake_sync(monkeypatch, PsnSyncOutcome(new_rows=[row("1")]))
    publisher = FakePublisher()
    fetcher = PsnFetcher(settings, repo, auth, publisher)  # type: ignore[arg-type]

    await fetcher.tick()

    assert len(publisher.published) == 1
    [target] = await repo.psn_pollable_users()
    assert target.last_polled_at is not None


async def test_tick_skips_an_account_polled_too_recently(
    repo: Repo, cipher: TokenCipher, settings: Settings, monkeypatch
) -> None:
    await _linked_user(repo)
    auth = await _configured_auth(repo, cipher, monkeypatch)
    await repo.mark_psn_backfill_done(ACCOUNT_ID)  # gate open, and stamps last_polled_at = now
    calls = _fake_sync(monkeypatch, PsnSyncOutcome())
    fetcher = PsnFetcher(settings, repo, auth, FakePublisher())  # type: ignore[arg-type]

    await fetcher.tick()

    assert calls == []  # debounce, not the backfill gate, is what stops it here


async def test_tick_does_nothing_when_psn_is_not_configured(
    repo: Repo, cipher: TokenCipher, settings: Settings, monkeypatch
) -> None:
    await _linked_user(repo)
    auth = PsnAuth(repo, cipher)  # never configured
    calls = _fake_sync(monkeypatch, PsnSyncOutcome())
    fetcher = PsnFetcher(settings, repo, auth, FakePublisher())  # type: ignore[arg-type]

    await fetcher.tick()

    assert calls == []


async def test_insert_new_achievements_psn_dedups_and_keeps_the_tier(repo: Repo) -> None:
    """The actual db/repo.py write path for the new column (SPEC 9,
    M-PSN-2) — INSERT OR IGNORE on (tg_id, platform, title_id,
    achievement_id) same as the Xbox/Steam siblings, trophy_type round-
    trips where they always leave it NULL."""
    await _linked_user(repo)
    trophy_row = AchievementRow(
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

    first = await repo.insert_new_achievements_psn(
        TG_ID, ACCOUNT_ID, [trophy_row], is_backfill=False
    )
    second = await repo.insert_new_achievements_psn(
        TG_ID, ACCOUNT_ID, [trophy_row], is_backfill=False
    )

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
    assert target.backfill_done is False  # no psn_poll_state row yet (#21)
