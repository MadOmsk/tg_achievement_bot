"""Things that were declared immutable and are not (#49, #50), plus the
per-game progress counter that rides on the same data (#46)."""

from __future__ import annotations

from bot.constants import AccountPlatform, account_platform_of
from bot.db.repo import (
    AchievementRow,
    Repo,
    SteamSchemaAchievement,
    TitleHistoryRow,
    TitleProgress,
)
from bot.services.achievements import format_digest, format_single
from bot.util import utcnow

TG_ID = 1
XUID = "2533274829605736"
STEAM_ID = "76561197981065056"


def _achievement(
    achievement_id: str = "a1",
    platform: str = "xbox_modern",
    title_id: str = "550",
    trophy_group_id: str | None = None,
) -> AchievementRow:
    return AchievementRow(
        title_id=title_id,
        achievement_id=achievement_id,
        name="An achievement",
        description=None,
        icon_url=None,
        unlocked_at=utcnow().isoformat(timespec="seconds"),
        gamerscore=10,
        rarity_percent=None,
        platform=platform,
        title_name="Left 4 Dead 2",
        trophy_group_id=trophy_group_id,
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

    assert await repo.title_progress(AccountPlatform.XBOX, XUID, "550") == TitleProgress(
        unlocked=47, total=50
    )


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

    assert await repo.title_progress(AccountPlatform.STEAM, STEAM_ID, "550") == TitleProgress(
        unlocked=2, total=4
    )


async def test_psn_counts_against_the_titles_whole_trophy_set(repo: Repo) -> None:
    """PSN reports no count for a person, but the title list the poller
    already walks carries how many trophies the game has (#46).

    That total includes DLC groups — verified against production: Marvel's
    Spider-Man reports 74, split 51 base + 23 across four DLC groups. So
    somebody who platinumed the base game reads 51/74, not 51/51, which is
    exactly what Sony's own trophy list and every PSN tracker show. Taking
    only the `default` group instead would need an extra request per title
    and disagree with all of them.
    """
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_platform_account(TG_ID, "psn", "acc-1", "Someone")
    await repo.upsert_title("NPWR00001_00", "Spider-Man", "psn", achievements_total=74)
    await repo.insert_new_achievements_psn(
        TG_ID,
        "acc-1",
        [
            _achievement("t1", "psn", title_id="NPWR00001_00"),
            _achievement("t2", "psn", title_id="NPWR00001_00"),
        ],
        is_backfill=False,
    )

    assert await repo.title_progress(AccountPlatform.PSN, "acc-1", "NPWR00001_00") == TitleProgress(
        unlocked=2, total=74
    )


async def test_psn_reports_none_until_the_total_is_known(repo: Repo) -> None:
    """A game last polled before the total was being stored — the counter is
    left off that line rather than invented."""
    assert await repo.title_progress(AccountPlatform.PSN, "acc-1", "NPWR99999_00") is None


async def test_upsert_title_never_blanks_a_known_total(repo: Repo) -> None:
    """Most upserts here know only the name — the Steam/PSN insert paths call
    this per game — and must not erase a total the poller cached."""
    await repo.upsert_title("NPWR00001_00", "Spider-Man", "psn", achievements_total=74)
    await repo.upsert_title("NPWR00001_00", "Spider-Man", "psn")

    assert await repo.title_progress(AccountPlatform.PSN, "acc-1", "NPWR00001_00") == TitleProgress(
        unlocked=0, total=74
    )


async def test_steam_progress_is_none_until_the_schema_is_cached(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_platform_account(TG_ID, "steam", STEAM_ID, "Someone")
    assert await repo.title_progress(AccountPlatform.STEAM, STEAM_ID, "550") is None


def test_the_counter_is_rendered_next_to_the_game(i18n) -> None:
    text = format_single(
        "Igor", _achievement(), "Left 4 Dead 2", locale="ru", progress=TitleProgress(47, 50)
    )
    assert "47/50" in text

    # Omitted, not zeroed, when the total is unknown. Asserting "no slash
    # anywhere" would be wrong: the game line closes an </i> tag.
    without = format_single("Igor", _achievement(), "Left 4 Dead 2", locale="ru")
    assert "47/50" not in without
    assert "0/0" not in without


def test_a_digest_carries_one_counter_per_game(i18n) -> None:
    rows = [_achievement("a1"), _achievement("a2")]
    text = format_digest(
        "Igor",
        None,
        rows,
        locale="ru",
        progress={("xbox_modern", "550", None): TitleProgress(47, 50)},
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


# ------------------------------------- PSN trophy groups, the second line


async def _spider_man(repo: Repo) -> None:
    """Marvel's Spider-Man as production actually reports it: 74 trophies in
    the title, 51 of them in the base group, the rest across four DLC."""
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_platform_account(TG_ID, "psn", "acc-1", "Someone")
    await repo.upsert_title("NPWR00001_00", "Marvel's Spider-Man", "psn", achievements_total=74)
    await repo.save_title_groups(
        "NPWR00001_00",
        [
            ("default", "Marvel's Spider-Man", 51),
            ("001", "The Heist", 7),
            ("002", "Turf Wars", 8),
        ],
    )


async def test_group_progress_counts_only_that_groups_trophies(repo: Repo) -> None:
    await _spider_man(repo)
    await repo.insert_new_achievements_psn(
        TG_ID,
        "acc-1",
        [
            _achievement("t1", "psn", title_id="NPWR00001_00", trophy_group_id="default"),
            _achievement("t2", "psn", title_id="NPWR00001_00", trophy_group_id="001"),
            _achievement("t3", "psn", title_id="NPWR00001_00", trophy_group_id="001"),
        ],
        is_backfill=False,
    )

    whole = await repo.title_progress(AccountPlatform.PSN, "acc-1", "NPWR00001_00", "001")
    assert whole is not None
    assert (whole.unlocked, whole.total) == (3, 74)
    assert (whole.group_name, whole.group_unlocked, whole.group_total) == ("The Heist", 2, 7)
    assert not whole.group_is_default


async def test_a_single_group_title_reports_no_group_at_all(repo: Repo) -> None:
    """Sony gives every title a 'default' group, so "has groups" is never
    the question — a game that is only that one group would render a second
    line repeating the first."""
    await repo.ensure_user(TG_ID, "igor")
    await repo.link_platform_account(TG_ID, "psn", "acc-1", "Someone")
    await repo.upsert_title("NPWR00002_00", "Stray", "psn", achievements_total=25)
    await repo.save_title_groups("NPWR00002_00", [("default", "Stray", 25)])

    progress = await repo.title_progress(AccountPlatform.PSN, "acc-1", "NPWR00002_00", "default")
    assert progress is not None
    assert progress.group_total == 0


def test_the_group_line_names_the_dlc_and_its_own_count(i18n) -> None:
    trophy = _achievement("t2", "psn", title_id="NPWR00001_00", trophy_group_id="001")
    text = format_single(
        "Igor",
        trophy,
        "Marvel's Spider-Man",
        locale="ru",
        progress=TitleProgress(
            unlocked=31, total=74, group_name="The Heist", group_unlocked=3, group_total=7
        ),
    )

    assert "31/74" in text
    assert "The Heist · 3/7" in text
    # And the trophy's own line is still there, under both of them.
    assert "«An achievement»" in text


def test_the_base_group_is_renamed_not_repeated(i18n) -> None:
    """Sony calls the base group after the game itself; printing the title
    on two lines in a row says nothing (owner decision)."""
    trophy = _achievement("t1", "psn", title_id="NPWR00001_00", trophy_group_id="default")
    text = format_single(
        "Igor",
        trophy,
        "Marvel's Spider-Man",
        locale="ru",
        progress=TitleProgress(
            unlocked=24,
            total=74,
            group_name="Marvel's Spider-Man",
            group_unlocked=24,
            group_total=51,
            group_is_default=True,
        ),
    )

    assert "Основная игра · 24/51" in text
    # html-escaped, as everything that reaches Telegram is.
    assert text.count("Marvel&#x27;s Spider-Man") == 1


def test_a_mixed_group_digest_block_keeps_the_game_counter_alone(i18n) -> None:
    """One digest block is one game, but a PSN burst can cross groups — no
    single group line is true of all of them, so none is printed."""
    rows = [
        _achievement("t1", "psn", title_id="NPWR00001_00", trophy_group_id="default"),
        _achievement("t2", "psn", title_id="NPWR00001_00", trophy_group_id="001"),
    ]
    progress = {
        ("psn", "NPWR00001_00", None): TitleProgress(unlocked=31, total=74),
        ("psn", "NPWR00001_00", "001"): TitleProgress(
            unlocked=31, total=74, group_name="The Heist", group_unlocked=3, group_total=7
        ),
    }
    text = format_digest("Igor", None, rows, locale="ru", progress=progress)

    assert "31/74" in text
    assert "The Heist" not in text
