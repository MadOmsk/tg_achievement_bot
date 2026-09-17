"""`repo.users_games_achievements` — the one games listing (2026-09-17).

The rules it exists to hold, each of which was broken at some point by a
version of this query that looked reasonable on its own:

- what "since" means for a row the platform gave no unlock date for;
- that `is_backfill` is not a filter, because it means "do not publish",
  not "did not happen";
- that the ranking is about achievements earned, not gamerscore, which two
  of the three platforms do not have at all.
"""

from __future__ import annotations

from datetime import timedelta

from bot.db.repo import AchievementRow, Repo
from bot.util import utcnow

XUID = "xuid-games"
OTHER_XUID = "xuid-games-2"


def _row(
    achievement_id: str,
    *,
    title_id: str = "t1",
    unlocked_at: str | None = None,
    gamerscore: int = 0,
    rarity: float | None = None,
    platform: str = "xbox_modern",
    title_name: str | None = "A Game",
) -> AchievementRow:
    return AchievementRow(
        title_id=title_id,
        achievement_id=achievement_id,
        name=f"Achievement {achievement_id}",
        description=None,
        icon_url=None,
        unlocked_at=unlocked_at,
        gamerscore=gamerscore,
        rarity_percent=rarity,
        platform=platform,
        title_name=title_name,
    )


async def _person(repo: Repo, tg_id: int = 1, xuid: str = XUID) -> None:
    await repo.ensure_user(tg_id, f"person{tg_id}")
    await repo.link_xbox_account(tg_id, xuid, f"Gamer{tg_id}", 0)


async def _listing(repo: Repo, tg_ids: list[int], *, days: int = 30, threshold: float = 10.0):
    return await repo.users_games_achievements(
        tg_ids, utcnow() - timedelta(days=days), rare_threshold=threshold
    )


async def test_a_backfilled_row_with_a_real_date_counts(repo: Repo) -> None:
    """The bug this listing was rebuilt for: excluding backfill outright hid
    achievements the platform itself dated inside the window. `is_backfill`
    means "do not publish", not "did not happen"."""
    await _person(repo)
    await repo.insert_new_achievements(
        XUID, [_row("a1", unlocked_at=utcnow().isoformat(timespec="seconds"))], is_backfill=True
    )

    [game] = await _listing(repo, [1])
    assert game.count == 1


async def test_a_backfilled_row_with_no_date_is_ancient(repo: Repo) -> None:
    """Its `created_at` is when the import ran, not when anything was
    earned — counting it is what made a whole imported library look like
    this month's play (#69)."""
    await _person(repo)
    await repo.insert_new_achievements(XUID, [_row("a1", unlocked_at=None)], is_backfill=True)

    assert await _listing(repo, [1]) == []


async def test_a_live_row_with_no_date_falls_back_to_when_we_saw_it(repo: Repo) -> None:
    """Xbox 360 sends placeholder dates that parse to nothing. A live poll
    saw the achievement roughly when it happened, so that stands in — and
    the alternative is a row the bot announced in chat and then cannot show
    in the list beside it."""
    await _person(repo)
    await repo.insert_new_achievements(XUID, [_row("a1", unlocked_at=None)], is_backfill=False)

    [game] = await _listing(repo, [1])
    assert game.count == 1


async def test_rows_outside_the_window_are_left_out(repo: Repo) -> None:
    await _person(repo)
    old = (utcnow() - timedelta(days=90)).isoformat(timespec="seconds")
    await repo.insert_new_achievements(XUID, [_row("a1", unlocked_at=old)], is_backfill=False)

    assert await _listing(repo, [1]) == []


async def test_ranked_by_achievements_earned_not_gamerscore(repo: Repo) -> None:
    """Gamerscore is always 0 on Steam and PSN, so ranking by it sank every
    game on those platforms below every Xbox one no matter what was played."""
    await _person(repo)
    now = utcnow().isoformat(timespec="seconds")
    # The name is read from `titles`, never from the achievement row — which
    # is why a Steam game polled without one shows as a bare appid (#70).
    await repo.upsert_title("rich", "One Big", "xbox_modern")
    await repo.upsert_title("many", "Many Small", "xbox_modern")
    await repo.insert_new_achievements(
        XUID,
        [
            _row("big", title_id="rich", unlocked_at=now, gamerscore=500, title_name="One Big"),
            *(
                _row(f"s{n}", title_id="many", unlocked_at=now, title_name="Many Small")
                for n in range(3)
            ),
        ],
        is_backfill=False,
    )

    games = await _listing(repo, [1])
    assert [(g.name, g.count) for g in games] == [("Many Small", 3), ("One Big", 1)]


async def test_a_tie_is_broken_by_the_most_recent_unlock(repo: Repo) -> None:
    await _person(repo)
    older = (utcnow() - timedelta(days=3)).isoformat(timespec="seconds")
    newer = (utcnow() - timedelta(hours=1)).isoformat(timespec="seconds")
    await repo.upsert_title("stale", "Played Earlier", "xbox_modern")
    await repo.upsert_title("fresh", "Played Just Now", "xbox_modern")
    await repo.insert_new_achievements(
        XUID,
        [
            _row("a", title_id="stale", unlocked_at=older, title_name="Played Earlier"),
            _row("b", title_id="fresh", unlocked_at=newer, title_name="Played Just Now"),
        ],
        is_backfill=False,
    )

    games = await _listing(repo, [1])
    assert [g.name for g in games] == ["Played Just Now", "Played Earlier"]


async def test_two_people_earning_the_same_achievement_count_twice(repo: Repo) -> None:
    """The chat-wide block counts what the chat did, not distinct
    achievements (owner, 2026-09-17)."""
    await _person(repo, 1, XUID)
    await _person(repo, 2, OTHER_XUID)
    now = utcnow().isoformat(timespec="seconds")
    for xuid in (XUID, OTHER_XUID):
        await repo.insert_new_achievements(xuid, [_row("same", unlocked_at=now)], is_backfill=False)

    [game] = await _listing(repo, [1, 2])
    assert game.count == 2


async def test_rare_is_counted_against_the_threshold_it_was_given(repo: Repo) -> None:
    await _person(repo)
    now = utcnow().isoformat(timespec="seconds")
    await repo.insert_new_achievements(
        XUID,
        [
            _row("rare", unlocked_at=now, rarity=2.0),
            _row("common", unlocked_at=now, rarity=60.0),
            _row("unknown", unlocked_at=now, rarity=None),
        ],
        is_backfill=False,
    )

    [strict] = await _listing(repo, [1], threshold=10.0)
    assert (strict.count, strict.rare) == (3, 1)
    # The same rows, a chat that calls anything under 70% rare.
    [loose] = await _listing(repo, [1], threshold=70.0)
    assert loose.rare == 2


async def test_one_game_on_two_platforms_is_two_rows(repo: Repo) -> None:
    """Grouped by (title_id, platform): a Steam appid and an Xbox title id
    are both bare numbers and can collide by accident."""
    await _person(repo)
    await repo.link_platform_account(1, "steam", "76561197960287930", "SteamPerson")
    now = utcnow().isoformat(timespec="seconds")
    await repo.insert_new_achievements(
        XUID, [_row("x", title_id="1234", unlocked_at=now)], is_backfill=False
    )
    await repo.insert_new_achievements_steam(
        1,
        "76561197960287930",
        [_row("s", title_id="1234", unlocked_at=now, platform="steam")],
        is_backfill=False,
    )

    games = await _listing(repo, [1])
    assert sorted(g.platform or "" for g in games) == ["steam", "xbox_modern"]


async def test_nobody_asked_about_is_nothing_queried(repo: Repo) -> None:
    """An empty roster must not become an `IN ()`, which is a syntax error."""
    assert await repo.users_games_achievements([], utcnow(), rare_threshold=10.0) == []
