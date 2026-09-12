"""Things that were declared immutable and are not (#49, #50), plus the
per-game progress counter that rides on the same data (#46)."""

from __future__ import annotations

from bot.constants import AccountPlatform, account_platform_of
from bot.db.repo import AchievementRow, Repo, SteamSchemaAchievement, TitleHistoryRow
from bot.services.achievements import format_digest, format_single
from bot.util import utcnow

TG_ID = 1
XUID = "2533274829605736"
STEAM_ID = "76561197981065056"


def _achievement(achievement_id: str = "a1", platform: str = "xbox_modern") -> AchievementRow:
    return AchievementRow(
        title_id="550",
        achievement_id=achievement_id,
        name="An achievement",
        description=None,
        icon_url=None,
        unlocked_at=utcnow().isoformat(timespec="seconds"),
        gamerscore=10,
        rarity_percent=None,
        platform=platform,
        title_name="Left 4 Dead 2",
    )


# ---------------------------------------------------------------- #46


async def test_xbox_progress_comes_from_title_history(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_xbox_account(TG_ID, XUID, "Someone", 0)
    await repo.save_title_history(
        XUID,
        [
            TitleHistoryRow(
                title_id="550",
                name="Left 4 Dead 2",
                platform="xbox_modern",
                current_gamerscore=470,
                max_gamerscore=500,
                achievements_unlocked=47,
                achievements_total=50,
                last_played_at=utcnow().isoformat(timespec="seconds"),
            )
        ],
    )

    assert await repo.title_progress(AccountPlatform.XBOX, XUID, "550") == (47, 50)


async def test_steam_progress_counts_rows_against_the_cached_schema(repo: Repo) -> None:
    """Steam publishes no per-user total, but the schema is the game's whole
    achievement list — its length is the total."""
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_platform_account(TG_ID, "steam", STEAM_ID, "Someone")
    await repo.steam_schema_cache_result(
        "550",
        "Left 4 Dead 2",
        [SteamSchemaAchievement(apiname=f"a{i}", icon="", hidden=False) for i in range(4)],
    )
    await repo.insert_new_achievements_steam(
        TG_ID,
        STEAM_ID,
        [_achievement("a1", "steam"), _achievement("a2", "steam")],
        is_backfill=False,
    )

    assert await repo.title_progress(AccountPlatform.STEAM, STEAM_ID, "550") == (2, 4)


async def test_psn_has_no_honest_total_so_reports_none(repo: Repo) -> None:
    """PSN stores progress as a percentage and never a count — the counter
    is left off that line rather than invented."""
    assert await repo.title_progress(AccountPlatform.PSN, "acc-1", "NPWR00001_00") is None


async def test_steam_progress_is_none_until_the_schema_is_cached(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_platform_account(TG_ID, "steam", STEAM_ID, "Someone")
    assert await repo.title_progress(AccountPlatform.STEAM, STEAM_ID, "550") is None


def test_the_counter_is_rendered_next_to_the_game(i18n) -> None:
    text = format_single("Igor", _achievement(), "Left 4 Dead 2", locale="ru", progress=(47, 50))
    assert "47/50" in text

    # Omitted, not zeroed, when the total is unknown. Asserting "no slash
    # anywhere" would be wrong: the game line closes an </i> tag.
    without = format_single("Igor", _achievement(), "Left 4 Dead 2", locale="ru")
    assert "47/50" not in without
    assert "0/0" not in without


def test_a_digest_carries_one_counter_per_game(i18n) -> None:
    rows = [_achievement("a1"), _achievement("a2")]
    text = format_digest(
        "Igor", None, rows, locale="ru", progress={("xbox_modern", "550"): (47, 50)}
    )
    assert text.count("47/50") == 1, "one figure per game, not per achievement"


# ---------------------------------------------------------------- #52 twin


def test_account_platform_of_matches_the_generated_column() -> None:
    """The Python twin of `seen_achievements.account_platform`. If these two
    ever disagree, a progress lookup silently finds nothing."""
    assert account_platform_of("xbox_modern") == AccountPlatform.XBOX
    assert account_platform_of("xbox_360") == AccountPlatform.XBOX
    assert account_platform_of("steam") == AccountPlatform.STEAM
    assert account_platform_of("psn") == AccountPlatform.PSN


async def test_the_generated_column_agrees_with_the_python_twin(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_xbox_account(TG_ID, XUID, "Someone", 0)
    await repo.insert_new_achievements(
        XUID, [_achievement("m1", "xbox_modern"), _achievement("o1", "xbox_360")], is_backfill=False
    )

    # Both generations resolve to the one Xbox account, in SQL as in Python.
    assert await repo.account_achievement_count(AccountPlatform.XBOX, XUID) == 2
