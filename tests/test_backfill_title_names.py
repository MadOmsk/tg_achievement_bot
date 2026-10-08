"""The gap `scripts/backfill_title_names.py` closes (2026-09-19 audit).

A query rather than logic, and the kind that looks obvious and is easy to get
subtly wrong — the owner pairing especially, which must never hand back
somebody whose Xbox login is dead. (The other gap, rows with no platform,
closed for good with migration 089.)
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
    await repo.save_refresh_token(await repo.person_id(TG_ID), cipher.encrypt("refresh"))
    await repo.link_xbox_account(await repo.person_id(TG_ID), XUID, "Mad Omsk", None)


async def test_a_game_with_no_catalogue_row_is_found(repo: Repo, cipher) -> None:
    await _owner(repo, cipher)
    await repo.insert_new_achievements(XUID, [_row("111")], is_backfill=True)

    assert await repo.titles_missing_from_catalogue(10) == [
        ("111", Platform.XBOX_MODERN, await repo.person_id(TG_ID))
    ]

    await repo.upsert_title("111", "A Named Game", Platform.XBOX_MODERN)
    assert await repo.titles_missing_from_catalogue(10) == []


async def test_a_dead_login_is_not_offered_as_the_owner(repo: Repo, cipher) -> None:
    """Asking through one buys a refusal from Microsoft and a doomed token
    refresh — the same rule the cover walker had to learn on 2026-09-18."""
    await _owner(repo, cipher)
    await repo.insert_new_achievements(XUID, [_row("111")], is_backfill=True)
    await repo.set_token_status(await repo.person_id(TG_ID), "invalid")

    assert await repo.titles_missing_from_catalogue(10) == []
