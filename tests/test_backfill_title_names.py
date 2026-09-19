"""The two gaps `scripts/backfill_title_names.py` closes (2026-09-19 audit).

Both are queries rather than logic, and both are the kind that look obvious
and are easy to get subtly wrong — the owner pairing especially, which must
never hand back somebody whose Xbox login is dead.
"""

from __future__ import annotations

from bot.constants import Platform
from bot.db.repo import AchievementRow, Repo

XUID = "xuid-catalogue"
TG_ID = 5


def _row(title_id: str, achievement_id: str = "a1") -> AchievementRow:
    return AchievementRow(
        title_id=title_id,
        achievement_id=achievement_id,
        name="Achievement",
        description=None,
        icon_url=None,
        unlocked_at=None,
        gamerscore=10,
        rarity_percent=None,
        platform=Platform.XBOX_MODERN,
        title_name=None,
    )


async def _owner(repo: Repo, cipher) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await repo.save_refresh_token(TG_ID, cipher.encrypt("refresh"))
    await repo.link_xbox_account(TG_ID, XUID, "Mad Omsk", None)


async def test_a_game_with_no_catalogue_row_is_found(repo: Repo, cipher) -> None:
    await _owner(repo, cipher)
    await repo.insert_new_achievements(XUID, [_row("111")], is_backfill=True)

    assert await repo.titles_missing_from_catalogue(10) == [("111", TG_ID)]

    await repo.upsert_title("111", "A Named Game", Platform.XBOX_MODERN)
    assert await repo.titles_missing_from_catalogue(10) == []


async def test_a_dead_login_is_not_offered_as_the_owner(repo: Repo, cipher) -> None:
    """Asking through one buys a refusal from Microsoft and a doomed token
    refresh — the same rule the cover walker had to learn on 2026-09-18."""
    await _owner(repo, cipher)
    await repo.insert_new_achievements(XUID, [_row("111")], is_backfill=True)
    await repo.set_token_status(TG_ID, "invalid")

    assert await repo.titles_missing_from_catalogue(10) == []


async def test_a_platform_is_taken_from_the_rows_that_know_it(repo: Repo, cipher) -> None:
    await _owner(repo, cipher)
    await repo.insert_new_achievements(XUID, [_row("222")], is_backfill=True)
    await repo._conn.execute(
        "INSERT INTO titles (title_id, name, platform, updated_at) VALUES ('222', 'Game', NULL, '')"
    )
    await repo._conn.commit()

    assert await repo.titles_without_platform() == [("222", Platform.XBOX_MODERN)]

    await repo.set_title_platform("222", Platform.XBOX_MODERN)
    assert await repo.titles_without_platform() == []


async def test_a_platform_already_recorded_is_never_overwritten(repo: Repo, cipher) -> None:
    """A stray row must not relabel a game that was seen on its own
    platform — the update is scoped to rows where it is still unknown."""
    await _owner(repo, cipher)
    await repo.upsert_title("333", "Game", Platform.XBOX_360)

    await repo.set_title_platform("333", Platform.XBOX_MODERN)

    cursor = await repo._conn.execute("SELECT platform FROM titles WHERE title_id = '333'")
    assert (await cursor.fetchone())["platform"] == Platform.XBOX_360
