"""The shared rarity cache, and the walker that fills it for Xbox.

Rarity is a fact about the achievement, not about whoever earned it, but
until 2026-09-17 it lived only on `seen_achievements` rows — written once,
with INSERT OR IGNORE, never updated. On Xbox that meant almost nowhere:
backfill reads the library with contract 2, which carries no percentage at
all, so 25 692 of production's 25 825 rows had none and never could.
"""

from __future__ import annotations

from datetime import timedelta

from bot.constants import Platform
from bot.db.repo import AchievementRow, Repo
from bot.poller.rarity_backfill import RarityBackfill
from bot.services.stats import month_cutoff_utc
from bot.services.xbox.models import parse_rarity, parse_rarity_with_title
from bot.util import utcnow

XUID = "xuid-rarity"
CHAT_ID = -100500
TG_ID = 1
TITLE = "t-rare"


def _row(achievement_id: str, *, rarity: float | None) -> AchievementRow:
    return AchievementRow(
        title_id=TITLE,
        achievement_id=achievement_id,
        name=f"Achievement {achievement_id}",
        description=None,
        icon_url=None,
        unlocked_at=utcnow().isoformat(timespec="seconds"),
        gamerscore=10,
        rarity_percent=rarity,
        platform=Platform.XBOX_MODERN,
        title_name="A Game",
    )


async def _person_with_uncached_history(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(TG_ID, XUID, "Gamer", 0)
    await repo.upsert_chat(CHAT_ID, "Chat", TG_ID)
    await repo.subscribe(CHAT_ID, TG_ID)
    # As a contract-2 backfill leaves them: no percentage at all.
    await repo.insert_new_achievements(
        XUID, [_row("a1", rarity=None), _row("a2", rarity=None)], is_backfill=True
    )


class FakeClient:
    """Answers like contract 4: every achievement of the title, including the
    ones this caller never earned."""

    def __init__(
        self,
        rarity: dict[str, float] | None = None,
        title_name: str | None = None,
    ) -> None:
        self.asked: list[tuple[int, str]] = []
        self._rarity = rarity if rarity is not None else {"a1": 2.0, "a2": 80.0, "a3": 0.5}
        self._title_name = title_name

    async def title_rarity(self, tg_id: int, title_id: str) -> dict[str, float]:
        self.asked.append((tg_id, title_id))
        return self._rarity

    async def title_rarity_with_name(
        self, tg_id: int, title_id: str
    ) -> tuple[dict[str, float], str | None]:
        self.asked.append((tg_id, title_id))
        return self._rarity, self._title_name


def test_parse_rarity_keeps_the_achievements_nobody_earned() -> None:
    """The whole point of asking: one owner's request answers for every
    achievement in the game, so the cache it fills serves everybody."""
    payload = {
        "achievements": [
            {"id": "earned", "progressState": "Achieved", "rarity": {"currentPercentage": 4.5}},
            {"id": "locked", "progressState": "NotStarted", "rarity": {"currentPercentage": 0.9}},
            {"id": "no-rarity", "progressState": "Achieved"},
        ]
    }
    assert parse_rarity(payload) == {"earned": 4.5, "locked": 0.9}


def test_parse_rarity_with_title_extracts_title_name() -> None:
    payload = {
        "achievements": [
            {
                "id": "1",
                "progressState": "Achieved",
                "rarity": {"currentPercentage": 4.5},
                "titleAssociations": [{"id": 111, "name": "Halo Infinite"}],
            },
        ]
    }
    rarity, name = parse_rarity_with_title(payload)
    assert rarity == {"1": 4.5}
    assert name == "Halo Infinite"


async def test_the_cache_answers_where_the_row_is_silent(repo: Repo) -> None:
    await _person_with_uncached_history(repo)
    since = month_cutoff_utc(180)

    rare_before, _tiers = await repo.achievement_value_breakdown(TG_ID, since, 10.0)
    assert rare_before == 0  # nothing ever said how rare these are

    await repo.cache_rarity(Platform.XBOX_MODERN, TITLE, {"a1": 2.0, "a2": 80.0})

    rare_after, _tiers = await repo.achievement_value_breakdown(TG_ID, since, 10.0)
    assert rare_after == 1  # a1 at 2% clears a 10% threshold, a2 at 80% does not


async def test_the_row_still_answers_when_the_cache_has_nothing(repo: Repo) -> None:
    """The cache is preferred, not required — a Steam or PSN row has carried
    its own percentage all along."""
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(TG_ID, XUID, "Gamer", 0)
    await repo.insert_new_achievements(XUID, [_row("a1", rarity=1.5)], is_backfill=False)

    rare, _tiers = await repo.achievement_value_breakdown(TG_ID, month_cutoff_utc(180), 10.0)
    assert rare == 1


async def test_the_cache_wins_over_a_stale_row(repo: Repo) -> None:
    """A row keeps whatever the platform said the first time somebody here
    earned the achievement, and is never updated; the cache is refreshed."""
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(TG_ID, XUID, "Gamer", 0)
    await repo.insert_new_achievements(XUID, [_row("a1", rarity=1.0)], is_backfill=False)
    await repo.cache_rarity(Platform.XBOX_MODERN, TITLE, {"a1": 60.0})

    rare, _tiers = await repo.achievement_value_breakdown(TG_ID, month_cutoff_utc(180), 10.0)
    assert rare == 0  # no longer rare, and the row cannot say otherwise


async def test_the_leaderboard_reads_the_cache_too(repo: Repo) -> None:
    await _person_with_uncached_history(repo)
    await repo.cache_rarity(Platform.XBOX_MODERN, TITLE, {"a1": 2.0, "a2": 80.0})

    [member] = await repo.chat_member_stats(CHAT_ID, month_cutoff_utc(180), 10.0)
    assert member.rare == 1


async def test_the_games_list_reads_the_cache_too(repo: Repo) -> None:
    await _person_with_uncached_history(repo)
    await repo.cache_rarity(Platform.XBOX_MODERN, TITLE, {"a1": 2.0, "a2": 80.0})

    [game] = await repo.users_games_achievements(
        [TG_ID], month_cutoff_utc(180), rare_threshold=10.0
    )
    assert game.rare == 1


async def test_the_walker_fills_a_title_and_stops_asking(repo: Repo) -> None:
    await _person_with_uncached_history(repo)
    client = FakeClient()
    walker = RarityBackfill(repo, client)  # type: ignore[arg-type]

    await walker.tick()
    assert client.asked == [(TG_ID, TITLE)]

    # Cached now, so the next tick has nothing left to ask about.
    await walker.tick()
    assert client.asked == [(TG_ID, TITLE)]


async def test_the_walker_caches_percentages_for_achievements_nobody_here_earned(
    repo: Repo,
) -> None:
    """a3 is in the game but in nobody's history — caching it now is what
    makes the first person to earn it show up as rare immediately."""
    await _person_with_uncached_history(repo)
    await RarityBackfill(repo, FakeClient()).tick()  # type: ignore[arg-type]

    await repo.insert_new_achievements(XUID, [_row("a3", rarity=None)], is_backfill=False)
    rare, _tiers = await repo.achievement_value_breakdown(TG_ID, month_cutoff_utc(180), 10.0)
    assert rare == 2  # a1 at 2% and the brand-new a3 at 0.5%


async def test_a_title_with_no_rarity_is_not_asked_again(repo: Repo) -> None:
    """An Xbox 360 title reached through a modern row: contract 4 answers it
    with nothing, and contract 1 has no percentages to give. Retrying every
    minute forever would be a hot loop against somebody else's API."""
    await _person_with_uncached_history(repo)
    client = FakeClient(rarity={})
    walker = RarityBackfill(repo, client)  # type: ignore[arg-type]

    await walker.tick()
    await walker.tick()
    assert client.asked == [(TG_ID, TITLE)]


async def test_coverage_counts_what_is_left(repo: Repo) -> None:
    await _person_with_uncached_history(repo)
    assert await repo.rarity_coverage(Platform.XBOX_MODERN) == (0, 1)

    await RarityBackfill(repo, FakeClient()).tick()  # type: ignore[arg-type]
    assert await repo.rarity_coverage(Platform.XBOX_MODERN) == (1, 1)


async def test_an_old_cache_entry_is_still_used(repo: Repo) -> None:
    """`checked_at` orders the refresh queue; it is not an expiry. A
    year-old percentage is worth more than none (owner, 2026-09-17)."""
    await _person_with_uncached_history(repo)
    await repo.cache_rarity(Platform.XBOX_MODERN, TITLE, {"a1": 2.0})
    await repo._conn.execute(
        "UPDATE achievement_rarity_cache SET checked_at = ?",
        ((utcnow() - timedelta(days=400)).isoformat(timespec="seconds"),),
    )
    await repo._conn.commit()

    rare, _tiers = await repo.achievement_value_breakdown(TG_ID, month_cutoff_utc(180), 10.0)
    assert rare == 1


async def test_the_walker_upserts_title_name_learned_from_contract_4(repo: Repo) -> None:
    await _person_with_uncached_history(repo)
    client = FakeClient(title_name="Halo Infinite")
    walker = RarityBackfill(repo, client)  # type: ignore[arg-type]

    await walker.tick()
    assert await repo.title_name(TITLE) == "Halo Infinite"


async def test_the_walker_heals_titles_missing_from_catalogue(repo: Repo) -> None:
    # Title has rarity cached, but no row in `titles` catalog (#77)
    await _person_with_uncached_history(repo)
    await repo.cache_rarity(Platform.XBOX_MODERN, TITLE, {"a1": 2.0})

    await repo.save_refresh_token(TG_ID, b"mock-token")

    assert await repo.title_name(TITLE) is None
    missing = await repo.titles_missing_from_catalogue(10)
    assert len(missing) == 1

    client = FakeClient(title_name="Healed Game Title")
    walker = RarityBackfill(repo, client)  # type: ignore[arg-type]

    await walker.tick()
    assert await repo.title_name(TITLE) == "Healed Game Title"
    assert await repo.titles_missing_from_catalogue(10) == []


async def test_the_walker_fills_xbox_360_title_and_views_pick_up_cache(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(TG_ID, XUID, "Gamer", 0)
    await repo.upsert_chat(CHAT_ID, "Chat", TG_ID)
    await repo.subscribe(CHAT_ID, TG_ID)

    row_360 = AchievementRow(
        title_id="t-360",
        achievement_id="ach-1",
        name="Episode 1",
        description="Completed episode",
        icon_url="http://image.xboxlive.com/global/t.12345/ach/0/1",
        unlocked_at=utcnow().isoformat(timespec="seconds"),
        gamerscore=15,
        rarity_percent=None,
        platform=Platform.XBOX_360,
        title_name="Wolf 3D",
    )
    await repo.insert_new_achievements(XUID, [row_360], is_backfill=True)

    client = FakeClient(rarity={"ach-1": 8.5}, title_name="Wolf 3D")
    walker = RarityBackfill(repo, client)  # type: ignore[arg-type]

    await walker.tick()
    assert (TG_ID, "t-360") in client.asked

    # Verify cached rarity is picked up in queries
    recent = await repo.recent_achievements(XUID, limit=5)
    assert len(recent) == 1
    assert recent[0].rarity_percent == 8.5

    person_rec = await repo.person_recent(TG_ID, limit=5)
    assert len(person_rec) == 1
    assert person_rec[0].rarity_percent == 8.5

    chat_rec = await repo.chat_recent(CHAT_ID, limit=5)
    assert len(chat_rec) == 1
    assert chat_rec[0].rarity_percent == 8.5


async def test_unpublished_achievements_reads_rarity_cache(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "someone")
    await repo.link_xbox_account(TG_ID, XUID, "Gamer", 0)
    await repo.upsert_chat(CHAT_ID, "Chat", TG_ID)
    await repo.subscribe(CHAT_ID, TG_ID)

    row_360 = AchievementRow(
        title_id="t-360",
        achievement_id="ach-2",
        name="Episode 2",
        description="Completed episode 2",
        icon_url="http://image.xboxlive.com/global/t.12345/ach/0/2",
        unlocked_at=utcnow().isoformat(timespec="seconds"),
        gamerscore=15,
        rarity_percent=None,
        platform=Platform.XBOX_360,
        title_name="Wolf 3D",
    )
    await repo.insert_new_achievements(XUID, [row_360], is_backfill=False)
    await repo.cache_rarity(Platform.XBOX_360, "t-360", {"ach-2": 4.2})

    pending = await repo.unpublished_achievements(TG_ID, CHAT_ID)
    assert len(pending) == 1
    assert pending[0].rarity_percent == 4.2
