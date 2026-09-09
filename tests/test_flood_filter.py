"""Anti-flood filter for achievement notifications (2026-09-09 user
request) — poller/publisher.py::Publisher._apply_flood_filter (the write
side) and poller/flood_flush.py (the read/flush side)."""

from __future__ import annotations

from datetime import timedelta

from bot.constants import RarityMode
from bot.db.repo import AchievementRow, Repo
from bot.poller.flood_flush import FloodFlush
from bot.poller.publisher import Publisher
from bot.services.achievements import format_digest
from bot.services.stats import local_now
from bot.util import utcnow

CHAT_ID = -100777
TG_ID = 1
XUID = "xuid-flood"


def achievement(achievement_id: str, platform: str = "modern") -> AchievementRow:
    return AchievementRow(
        title_id="title-1",
        achievement_id=achievement_id,
        name=achievement_id,
        description=None,
        icon_url=None,
        unlocked_at=utcnow().isoformat(timespec="seconds"),
        gamerscore=10,
        rarity_percent=None,
        platform=platform,
    )


async def _setup_chat(
    repo: Repo,
    *,
    flood_limit: int = 3,
    flood_window_minutes: int = 60,
) -> None:
    await repo.upsert_chat(CHAT_ID, "Test chat", 1)
    await repo.ensure_user(TG_ID, "gamer")
    await repo.link_xbox_account(TG_ID, XUID, "Gamer", 0)
    await repo.subscribe(CHAT_ID, TG_ID)
    await repo.update_chat_settings(
        CHAT_ID, flood_limit=flood_limit, flood_window_minutes=flood_window_minutes
    )
    # digest_threshold is a separate, unrelated mechanism (lives on the
    # subscription) — pushed out of reach so these tests aren't accidentally
    # exercising it too when several achievements land in one publish() call.
    await repo.update_subscription_digest_threshold(CHAT_ID, TG_ID, 99)


async def test_flood_filter_allows_the_limit_then_buffers_the_rest(repo: Repo) -> None:
    """The example from the feature request: N=3 lets three achievements
    through as usual; the rest accumulate instead of posting."""
    await _setup_chat(repo, flood_limit=3)
    publisher = Publisher(bot=None, repo=repo)  # type: ignore[arg-type]
    chat = (await repo.publication_targets(TG_ID))[0]

    for i in range(5):
        item = achievement(f"a{i}")
        await repo.insert_new_achievements(XUID, [item], is_backfill=False)
        for sent in await publisher._apply_flood_filter(TG_ID, chat, [item]):
            await repo.record_publication(CHAT_ID, XUID, sent.title_id, sent.achievement_id, None)

    state = await repo.get_flood_state(TG_ID, CHAT_ID)
    assert state is not None
    assert state.throttled is True
    assert state.count_in_window == 3

    pending = await repo.unpublished_achievements(TG_ID, CHAT_ID)
    assert {a.achievement_id for a in pending} == {"a3", "a4"}


async def test_flood_filter_splits_a_single_burst_right_at_the_limit(repo: Repo) -> None:
    """A burst that arrives in one publish() call (a PSN multi-trophy tick,
    say) must still flip into throttled mode at the Nth item, exactly as if
    each had arrived on its own."""
    await _setup_chat(repo, flood_limit=3)
    publisher = Publisher(bot=None, repo=repo)  # type: ignore[arg-type]
    chat = (await repo.publication_targets(TG_ID))[0]
    items = [achievement(f"b{i}") for i in range(5)]
    for item in items:
        await repo.insert_new_achievements(XUID, [item], is_backfill=False)

    to_send = await publisher._apply_flood_filter(TG_ID, chat, items)

    assert [a.achievement_id for a in to_send] == ["b0", "b1", "b2"]
    state = await repo.get_flood_state(TG_ID, CHAT_ID)
    assert state is not None and state.throttled is True and state.count_in_window == 3


async def test_flood_filter_disabled_when_limit_is_zero(repo: Repo) -> None:
    await _setup_chat(repo, flood_limit=0)
    publisher = Publisher(bot=None, repo=repo)  # type: ignore[arg-type]

    for i in range(10):
        item = achievement(f"c{i}")
        await repo.insert_new_achievements(XUID, [item], is_backfill=False)
        await publisher.publish(TG_ID, XUID, "Gamer", [item])

    assert publisher._queue.qsize() == 10
    assert await repo.get_flood_state(TG_ID, CHAT_ID) is None


async def test_flood_filter_never_starts_a_timer_for_a_filtered_out_achievement(
    repo: Repo,
) -> None:
    """ "Работает только на то, что уведомляется" (feature request) —
    rarity_mode=hidden means nothing is ever notified here, so nothing
    should ever touch notification_throttle either."""
    await _setup_chat(repo, flood_limit=1)
    await repo.update_subscription_rarity_mode(CHAT_ID, TG_ID, RarityMode.HIDDEN)
    publisher = Publisher(bot=None, repo=repo)  # type: ignore[arg-type]
    item = achievement("z1")
    await repo.insert_new_achievements(XUID, [item], is_backfill=False)

    await publisher.publish(TG_ID, XUID, "Gamer", [item])

    assert publisher._queue.qsize() == 0
    assert await repo.get_flood_state(TG_ID, CHAT_ID) is None


async def test_flood_flush_sends_pending_items_as_one_digest_once_the_window_expires(
    repo: Repo,
) -> None:
    """The buffered backlog can mix platforms — the whole point of scoping
    the filter to the person, not one platform at a time (feature request)."""
    await _setup_chat(repo, flood_limit=1, flood_window_minutes=60)
    xbox_item = achievement("x1", platform="modern")
    steam_item = achievement("s1", platform="steam")
    await repo.insert_new_achievements(XUID, [xbox_item], is_backfill=False)
    await repo.link_platform_account(TG_ID, "steam", "steamid-1", "SteamGamer")
    await repo.insert_new_achievements_steam(TG_ID, "steamid-1", [steam_item], is_backfill=False)
    await repo.set_flood_state(
        TG_ID,
        CHAT_ID,
        window_started_at=utcnow() - timedelta(minutes=61),
        count_in_window=1,
        throttled=True,
    )

    publisher = Publisher(bot=None, repo=repo)  # type: ignore[arg-type]
    await FloodFlush(repo, publisher).tick()

    assert publisher._queue.qsize() == 1
    job = publisher._queue.get_nowait()
    assert {(x, t, a) for x, t, a in job.items} == {
        (XUID, "title-1", "x1"),
        ("steamid-1", "title-1", "s1"),
    }
    assert await repo.get_flood_state(TG_ID, CHAT_ID) is None


async def test_flood_flush_force_flushes_five_minutes_before_the_daily_summary(
    repo: Repo,
) -> None:
    """A safety valve (user request): the summary should describe
    achievements that have actually been announced, not ones still sitting
    in the buffer — so a window still well inside its hour gets force-closed
    anyway, right at T-5 of that chat's own scheduled summary."""
    await _setup_chat(repo, flood_limit=1, flood_window_minutes=60)
    item = achievement("e1")
    await repo.insert_new_achievements(XUID, [item], is_backfill=False)
    target_time = (local_now(180) + timedelta(minutes=5)).strftime("%H:%M")
    await repo.update_chat_settings(CHAT_ID, daily_summary_time=target_time)
    await repo.set_flood_state(
        TG_ID, CHAT_ID, window_started_at=utcnow(), count_in_window=1, throttled=True
    )

    publisher = Publisher(bot=None, repo=repo)  # type: ignore[arg-type]
    await FloodFlush(repo, publisher).tick()

    assert publisher._queue.qsize() == 1
    assert await repo.get_flood_state(TG_ID, CHAT_ID) is None


async def test_flood_flush_all_force_exits_every_window_regardless_of_expiry(
    repo: Repo,
) -> None:
    """The other safety valve (user request): a bot restart must not leave
    a mid-count window's buffer stuck forever."""
    await _setup_chat(repo, flood_limit=1, flood_window_minutes=60)
    item = achievement("f1")
    await repo.insert_new_achievements(XUID, [item], is_backfill=False)
    await repo.set_flood_state(
        TG_ID, CHAT_ID, window_started_at=utcnow(), count_in_window=1, throttled=True
    )

    publisher = Publisher(bot=None, repo=repo)  # type: ignore[arg-type]
    await FloodFlush(repo, publisher).flush_all()

    assert publisher._queue.qsize() == 1
    assert await repo.get_flood_state(TG_ID, CHAT_ID) is None


def test_format_digest_says_achievements_not_trophies_for_a_mixed_platform_batch() -> None:
    items = [achievement("m1", platform="modern"), achievement("m2", platform="psn")]
    text = format_digest("Игрок", None, items)
    assert "трофе" not in text.lower()


def test_format_digest_still_says_trophies_when_everything_is_psn() -> None:
    items = [achievement("m1", platform="psn"), achievement("m2", platform="psn")]
    text = format_digest("Игрок", None, items)
    assert "трофе" in text.lower()
