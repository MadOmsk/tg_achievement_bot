"""One date rule, everywhere a window is asked about (#69).

The rule: a row the platform dated is placed by that date; an undated row a
live poll found is placed by when the bot saw it; an undated row an import
brought in is ancient, because its `created_at` is when the import ran.

These tests are per *reader* rather than per SQL fragment on purpose — the
fragment being shared is an implementation detail, and what broke in
production was a screen, not a query.
"""

from __future__ import annotations

from datetime import timedelta

from bot.db.repo import AchievementRow, Repo
from bot.services.stats import month_cutoff_utc
from bot.util import utcnow

XUID = "xuid-window"
CHAT_ID = -100500
TG_ID = 1


def _row(achievement_id: str, *, unlocked_at: str | None, title_id: str = "t1") -> AchievementRow:
    return AchievementRow(
        title_id=title_id,
        achievement_id=achievement_id,
        name=f"Achievement {achievement_id}",
        description=None,
        icon_url=None,
        unlocked_at=unlocked_at,
        gamerscore=10,
        rarity_percent=None,
        platform="xbox_modern",
        title_name="A Game",
    )


async def _subscribed_person(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(TG_ID, XUID, "Gamer", 0)
    await repo.upsert_chat(CHAT_ID, "Chat", TG_ID)
    await repo.subscribe(CHAT_ID, TG_ID)


async def _store(repo: Repo, rows: list[AchievementRow], *, is_backfill: bool) -> None:
    await repo.insert_new_achievements(XUID, rows, is_backfill=is_backfill)


async def test_counters_ignore_an_undated_import(repo: Repo) -> None:
    """#69 as production met it: a freshly linked library counted as this
    month's play — 767 achievements for somebody who had earned none."""
    await _subscribed_person(repo)
    await _store(repo, [_row(f"a{n}", unlocked_at=None) for n in range(20)], is_backfill=True)

    count, score = await repo.achievement_counts(XUID, month_cutoff_utc(180))
    assert (count, score) == (0, 0)


async def test_counters_keep_an_import_the_platform_dated(repo: Repo) -> None:
    """The opposite failure, and the reason `is_backfill = 0` alone was
    wrong: these are real unlocks, imported."""
    await _subscribed_person(repo)
    now = utcnow().isoformat(timespec="seconds")
    await _store(repo, [_row("a1", unlocked_at=now)], is_backfill=True)

    count, _score = await repo.achievement_counts(XUID, month_cutoff_utc(180))
    assert count == 1


async def test_counters_keep_an_undated_live_poll(repo: Repo) -> None:
    """Xbox 360's placeholder dates parse to nothing, and the bot saw these
    within hours of them happening — that is what makes the fallback honest
    here and dishonest for an import."""
    await _subscribed_person(repo)
    await _store(repo, [_row("a1", unlocked_at=None)], is_backfill=False)

    count, _score = await repo.achievement_counts(XUID, month_cutoff_utc(180))
    assert count == 1


async def test_the_per_platform_breakdown_agrees_with_the_total(repo: Repo) -> None:
    """Two readers, one window — they were separately capable of
    disagreeing, which is exactly what #32 already had to fix once."""
    await _subscribed_person(repo)
    now = utcnow().isoformat(timespec="seconds")
    await _store(repo, [_row("dated", unlocked_at=now)], is_backfill=True)
    await _store(repo, [_row("undated", unlocked_at=None)], is_backfill=True)

    since = month_cutoff_utc(180)
    total, _score = await repo.achievement_counts_for_person(TG_ID, since)
    xbox, steam, psn = await repo.achievement_platform_breakdown(TG_ID, since)
    assert total == 1
    assert (xbox, steam, psn) == (1, 0, 0)


async def test_the_leaderboard_ignores_an_undated_import(repo: Repo) -> None:
    await _subscribed_person(repo)
    await _store(repo, [_row(f"a{n}", unlocked_at=None) for n in range(5)], is_backfill=True)

    [member] = await repo.chat_member_stats(CHAT_ID, month_cutoff_utc(180), 10.0)
    assert member.count == 0


async def test_recent_ignores_an_undated_import(repo: Repo) -> None:
    """`/recent` has no window of its own, so the rule applies as an
    exclusion: an import's timestamp is "now" at connect time, which would
    put somebody's whole imported history at the top of the list in the one
    window where a first link is supposed to be silent."""
    await _subscribed_person(repo)
    old = (utcnow() - timedelta(days=200)).isoformat(timespec="seconds")
    await _store(repo, [_row("real", unlocked_at=old)], is_backfill=False)
    await _store(repo, [_row(f"import{n}", unlocked_at=None) for n in range(5)], is_backfill=True)

    rows = await repo.chat_recent(CHAT_ID, 10)
    assert [row.name for row in rows] == ["Achievement real"]


async def test_the_admin_roster_counters_follow_the_same_rule(repo: Repo) -> None:
    await _subscribed_person(repo)
    await _store(repo, [_row("a1", unlocked_at=None)], is_backfill=True)

    by_person = await repo.achievement_counts_by_tg_id(month_cutoff_utc(180))
    assert by_person.get(TG_ID, (0, 0))[0] == 0


async def test_a_lifetime_count_still_includes_everything(repo: Repo) -> None:
    """No window, no rule: `since=None` is "ever", and an undated import
    did happen — it just cannot be placed in time."""
    await _subscribed_person(repo)
    await _store(repo, [_row(f"a{n}", unlocked_at=None) for n in range(7)], is_backfill=True)

    count, _score = await repo.achievement_counts(XUID, None)
    assert count == 7


async def test_recent_shows_what_the_achievement_was_worth(repo: Repo) -> None:
    """Not what the player's career is worth. `XBOX_COLUMNS` selects the
    profile's own lifetime `gamerscore`, and `chat_recent` selected the
    achievement's under the same bare name — sqlite3.Row resolves a duplicate
    to the first, so every row showed the career total (249 504 G on the test
    bot) instead of the 15 G the achievement actually gave. Found by
    rendering the screen, not by any test that existed."""
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(TG_ID, XUID, "Gamer", 249_504)
    await repo.upsert_chat(CHAT_ID, "Chat", TG_ID)
    await repo.subscribe(CHAT_ID, TG_ID)
    now = utcnow().isoformat(timespec="seconds")
    await repo.insert_new_achievements(XUID, [_row("a1", unlocked_at=now)], is_backfill=False)

    [row] = await repo.chat_recent(CHAT_ID, 5)
    assert row.gamerscore == 10
