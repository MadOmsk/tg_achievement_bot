"""Achievement history belongs to the account that earned it (#52).

The bug underneath is #29: history used to be keyed by the person, so a
person who swapped one account for another on the same platform inherited
the first account's rows — and, worse, kept losing the second account's
genuinely new unlocks forever, because `title_id`/`achievement_id` are not
account-specific and INSERT OR IGNORE saw them as already seen.
"""

from __future__ import annotations

from bot.db.repo import AchievementRow, Repo
from bot.util import utcnow

ALICE, BOB = 1, 2
ACCOUNT_A, ACCOUNT_B = "76561190000000001", "76561190000000002"


def _achievement(achievement_id: str = "a1", title_id: str = "550") -> AchievementRow:
    return AchievementRow(
        title_id=title_id,
        achievement_id=achievement_id,
        name="An achievement",
        description=None,
        icon_url=None,
        unlocked_at=utcnow().isoformat(timespec="seconds"),
        gamerscore=0,
        rarity_percent=None,
        platform="steam",
    )


async def test_a_second_account_keeps_its_own_copy_of_the_same_achievement(repo: Repo) -> None:
    """#29's own acceptance criterion. Two real accounts can both have
    earned the same achievement in the same game; the second one's copy
    used to be swallowed as a duplicate and never seen again."""
    await repo.ensure_user(ALICE, "alice")

    await repo.link_platform_account(ALICE, "steam", ACCOUNT_A, "AccountA")
    first = await repo.insert_new_achievements_steam(
        ALICE, ACCOUNT_A, [_achievement()], is_backfill=False
    )
    assert len(first) == 1

    await repo.link_platform_account(ALICE, "steam", ACCOUNT_B, "AccountB")
    second = await repo.insert_new_achievements_steam(
        ALICE, ACCOUNT_B, [_achievement()], is_backfill=False
    )
    assert len(second) == 1, "the new account's own unlock was dropped as already-seen"

    # And only the account they hold now counts toward anything.
    assert await repo.platform_achievement_count(ALICE, "steam") == 1


async def test_switching_accounts_hides_the_old_ones_history(repo: Repo) -> None:
    await repo.ensure_user(ALICE, "alice")
    await repo.link_platform_account(ALICE, "steam", ACCOUNT_A, "AccountA")
    await repo.insert_new_achievements_steam(
        ALICE, ACCOUNT_A, [_achievement("a1"), _achievement("a2")], is_backfill=False
    )
    assert await repo.platform_achievement_count(ALICE, "steam") == 2

    await repo.link_platform_account(ALICE, "steam", ACCOUNT_B, "AccountB")
    assert await repo.platform_achievement_count(ALICE, "steam") == 0


async def test_relinking_the_old_account_finds_its_history_waiting(repo: Repo) -> None:
    """Nothing is ever deleted (owner decision) — which is also what lets a
    relink run a delta instead of paying for a whole backfill again."""
    await repo.ensure_user(ALICE, "alice")
    await repo.link_platform_account(ALICE, "steam", ACCOUNT_A, "AccountA")
    await repo.insert_new_achievements_steam(
        ALICE, ACCOUNT_A, [_achievement("a1"), _achievement("a2")], is_backfill=False
    )

    await repo.link_platform_account(ALICE, "steam", ACCOUNT_B, "AccountB")
    await repo.link_platform_account(ALICE, "steam", ACCOUNT_A, "AccountA")

    assert await repo.platform_achievement_count(ALICE, "steam") == 2
    assert await repo.account_has_history("steam", ACCOUNT_A) is True


async def test_disconnecting_keeps_everything_and_only_hides_it(repo: Repo) -> None:
    await repo.ensure_user(ALICE, "alice")
    await repo.link_platform_account(ALICE, "steam", ACCOUNT_A, "AccountA")
    await repo.insert_new_achievements_steam(ALICE, ACCOUNT_A, [_achievement()], is_backfill=False)

    await repo.unlink_platform_account(ALICE, "steam")

    assert await repo.platform_achievement_count(ALICE, "steam") == 0
    assert await repo.platform_links_of(ALICE) == []
    assert await repo.account_has_history("steam", ACCOUNT_A) is True
    assert await repo.account_owner("steam", ACCOUNT_A) is None


async def test_taking_an_account_from_someone_else_moves_its_history(repo: Repo) -> None:
    """Allowed on purpose, with no hard block (owner decision) — the caller
    is the one that tells the previous owner, and `link_platform_account`
    hands it the tg_id to tell."""
    await repo.ensure_user(ALICE, "alice")
    await repo.ensure_user(BOB, "bob")
    await repo.link_platform_account(ALICE, "steam", ACCOUNT_A, "AccountA")
    await repo.insert_new_achievements_steam(ALICE, ACCOUNT_A, [_achievement()], is_backfill=False)
    assert await repo.platform_achievement_count(ALICE, "steam") == 1

    taken_from = await repo.link_platform_account(BOB, "steam", ACCOUNT_A, "AccountA")

    assert taken_from == ALICE
    assert await repo.platform_achievement_count(ALICE, "steam") == 0
    assert await repo.platform_achievement_count(BOB, "steam") == 1
    assert await repo.account_owner("steam", ACCOUNT_A) == BOB


async def test_linking_an_untouched_account_reports_no_previous_owner(repo: Repo) -> None:
    await repo.ensure_user(ALICE, "alice")
    assert await repo.link_platform_account(ALICE, "steam", ACCOUNT_A, "AccountA") is None
    # Relinking the same account to the same person is not a takeover either.
    assert await repo.link_platform_account(ALICE, "steam", ACCOUNT_A, "AccountA") is None


async def test_both_xbox_generations_belong_to_one_account(repo: Repo) -> None:
    """Owner decision: Xbox binds as a pair and reads as one platform. The
    GENERATED `account_platform` column is what makes that true in SQL, so
    an x360 row resolves to the same account as a modern one."""
    await repo.ensure_user(ALICE, "alice")
    await repo.link_xbox_account(ALICE, "xuid-1", "Someone", 0)
    rows = [
        AchievementRow(
            title_id="t1",
            achievement_id="m1",
            name="modern",
            description=None,
            icon_url=None,
            unlocked_at=utcnow().isoformat(timespec="seconds"),
            gamerscore=10,
            rarity_percent=None,
            platform="xbox_modern",
        ),
        AchievementRow(
            title_id="t2",
            achievement_id="o1",
            name="old",
            description=None,
            icon_url=None,
            unlocked_at=utcnow().isoformat(timespec="seconds"),
            gamerscore=5,
            rarity_percent=None,
            platform="xbox_360",
        ),
    ]
    await repo.insert_new_achievements("xuid-1", rows, is_backfill=False)

    assert await repo.xbox_achievement_count(ALICE) == 2
    assert await repo.account_has_history("xbox", "xuid-1") is True

    # One link covers both generations, so unlinking hides both at once.
    await repo.unlink_xbox_account(ALICE)
    assert await repo.xbox_achievement_count(ALICE) == 0


async def test_an_account_can_only_have_one_owner_at_a_time(repo: Repo) -> None:
    await repo.ensure_user(ALICE, "alice")
    await repo.ensure_user(BOB, "bob")
    await repo.link_platform_account(ALICE, "steam", ACCOUNT_A, "AccountA")
    await repo.link_platform_account(BOB, "steam", ACCOUNT_A, "AccountA")

    assert await repo.account_owner("steam", ACCOUNT_A) == BOB
    assert await repo.platform_links_of(ALICE) == []
