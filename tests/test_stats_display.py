"""The headline gamerscore next to a name must always be the profile value,
never a sum over `seen_achievements` (SPEC 5.4) — the sum is permanently
best-effort (title_history is capped, achievements with no unlock date exist,
etc.), while the profile number is what a person actually sees on the Xbox
site. Locked down here after chasing the opposite assumption for a while."""

from __future__ import annotations

from bot.db.repo import (
    AchievementRow,
    ChatPresenceRow,
    Repo,
    SteamSchemaAchievement,
    TopGame,
)
from bot.handlers.chat import _build_stats_text, _games_list, _send_stats_card, _who_label
from bot.services.achievements import COMPLETED_BADGE
from bot.util import utcnow

CHAT_ID = -100500


class _FakeMessage:
    def __init__(self, message_id: int) -> None:
        self.message_id = message_id


class FakeBot:
    """Same pattern as test_single_message.py's own FakeBot — captures the
    kwargs a real aiogram Bot.send_message would receive, so a missing
    Telegram-level send option (like disable_web_page_preview) is a plain
    assertion, not something only visible once it's actually live."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str, dict[str, object]]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> _FakeMessage:
        self.sent.append((chat_id, text, kwargs))
        return _FakeMessage(len(self.sent))

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        pass


XUID = "xuid-profile-check"


def _achievement(title_id: str) -> AchievementRow:
    return AchievementRow(
        title_id=title_id,
        achievement_id="1",
        name="A",
        description=None,
        icon_url=None,
        unlocked_at=utcnow().isoformat(timespec="seconds"),
        gamerscore=10,
        rarity_percent=50.0,
        platform="xbox_modern",
    )


async def test_header_gamerscore_is_the_profile_value_not_a_sum(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    # Profile says a lot more than seen_achievements will ever sum to.
    await repo.link_xbox_account(1, XUID, "Someone", 999_999)
    await repo.insert_new_achievements(
        XUID,
        [
            AchievementRow(
                title_id="1",
                achievement_id="1",
                name="An achievement",
                description=None,
                icon_url=None,
                unlocked_at="2026-01-01T00:00:00+00:00",
                gamerscore=10,
                rarity_percent=50.0,
                platform="xbox_modern",
            )
        ],
        is_backfill=False,
    )

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    # Line 0 is just the display name now (SPEC 9, M-Steam-2e); the Xbox
    # line with its gamerscore is line 1.
    xbox_line = text.split("\n")[1]
    assert "999" in xbox_line  # thousands() formatting, profile value
    assert "10 G" not in xbox_line


async def test_header_shows_the_telegram_username_not_the_gamertag(repo: Repo) -> None:
    """Follow-up 2026-09-06, user request — the header identifies the
    person via Telegram, not whichever platform happened to be Xbox; the
    card already lists XBOX's own name on its own line below."""
    await repo.ensure_user(1, "realusername")
    await repo.link_xbox_account(1, XUID, "GamerTag", 0)

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    header = text.split("\n")[0]
    # Bare, with no "@" (#51): a username is never rendered as a live
    # mention anywhere in the bot.
    assert "realusername" in header
    assert "@realusername" not in header
    assert "GamerTag" not in header


async def test_header_falls_back_to_full_name_with_no_username(repo: Repo) -> None:
    await repo.ensure_user(1, None, "Igor", "Petrov")
    await repo.link_xbox_account(1, XUID, "GamerTag", 0)

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    header = text.split("\n")[0]
    assert "Igor Petrov" in header


async def test_header_falls_back_to_first_name_alone_with_no_last_name(repo: Repo) -> None:
    await repo.ensure_user(1, None, "Igor", None)
    await repo.link_xbox_account(1, XUID, "GamerTag", 0)

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    header = text.split("\n")[0]
    assert "Igor" in header
    assert "GamerTag" not in header


async def test_header_falls_back_to_gamertag_with_nothing_from_telegram_yet(repo: Repo) -> None:
    """A brand-new /start before this person's own message middleware has
    ever run — same defensive last resort this function already had."""
    await repo.ensure_user(1, None, None, None)
    await repo.link_xbox_account(1, XUID, "GamerTag", 0)

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    assert "GamerTag" in text.split("\n")[0]


async def test_update_names_does_not_clobber_a_known_name_with_none(repo: Repo) -> None:
    """Same COALESCE shape update_username already relies on — a message
    where Telegram's own last_name happens to be absent must not erase a
    last_name this person already had on file."""
    await repo.ensure_user(1, None, "Igor", "Petrov")
    await repo.update_names(1, "Igor", None)

    user = await repo.get_user(1)
    assert user is not None
    assert user.first_name == "Igor"
    assert user.last_name == "Petrov"


async def test_steam_line_shows_its_own_lifetime_achievement_count(repo: Repo) -> None:
    """SPEC 9, M-Steam-2e: unlike Xbox's line (profile gamerscore, never a
    seen_achievements sum), Steam's line shows a lifetime count from
    seen_achievements directly — no cap risk there (backfill sees the whole
    owned-games library), so it's trustworthy as a total."""
    await repo.ensure_user(1, "someone")
    await repo.link_platform_account(1, "steam", "76561197960287930", "SteamPerson")
    await repo.insert_new_achievements_steam(
        1,
        "76561197960287930",
        [
            AchievementRow(
                title_id="550",
                achievement_id="a1",
                name="A",
                description=None,
                icon_url=None,
                unlocked_at="2026-01-01T00:00:00+00:00",
                gamerscore=0,
                rarity_percent=50.0,
                platform="steam",
            ),
            AchievementRow(
                title_id="550",
                achievement_id="a2",
                name="B",
                description=None,
                icon_url=None,
                unlocked_at="2026-01-02T00:00:00+00:00",
                gamerscore=0,
                rarity_percent=20.0,
                platform="steam",
            ),
        ],
        is_backfill=True,
    )

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    steam_line = next(line for line in text.split("\n") if line.startswith("⚫"))
    assert "SteamPerson" in steam_line
    assert "2 достижения" in steam_line


def test_games_list_colours_x360_the_same_as_modern_xbox() -> None:
    """Found live (2026-09-05 platform-icon refactor): chat.py's own
    _PLATFORM_ICON copy never had an "xbox_360" key at all, so an Xbox 360
    game silently got no icon here — unlike services/achievements.py's own
    copy, used everywhere else, which always has. Both now share one dict."""
    line = _games_list([TopGame(name="Fallout 3", gamerscore=100, unlocked=5, platform="xbox_360")])
    assert "🟢 Fallout 3" in line


async def test_games_list_is_capped_by_the_configured_limit(repo: Repo) -> None:
    """stats_games_limit (default 15) caps how many games show — no separate
    "показать все игры" button any more, the list is a collapsible quote
    (SPEC 1.6, 6.4)."""
    await repo.ensure_user(1, "someone")
    await repo.link_xbox_account(1, XUID, "Someone", 0)
    await repo.set_app_setting("stats_games_limit", "2")
    for i in range(3):
        await repo.insert_new_achievements(XUID, [_achievement(str(i))], is_backfill=False)

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    # 3 distinct games exist, but only 2 (the limit) render as list rows.
    assert text.count("без названия") == 2


async def test_counters_show_platform_breakdown_only_with_two_platforms(repo: Repo) -> None:
    """2026-09-05 follow-up, reversal of "one combined number only" (SPEC 9,
    M-Steam-2e): a parenthetical next to "Сегодня"/"За месяц", but only once
    there's something to break down."""
    await repo.ensure_user(1, "both")
    await repo.link_xbox_account(1, XUID, "Both", 0)
    await repo.link_platform_account(1, "steam", "76561197960287930", "BothSteam")
    await repo.insert_new_achievements(XUID, [_achievement("1")], is_backfill=False)
    await repo.insert_new_achievements_steam(
        1,
        "76561197960287930",
        [
            AchievementRow(
                title_id="550",
                achievement_id="s1",
                name="s1",
                description=None,
                icon_url=None,
                unlocked_at=utcnow().isoformat(timespec="seconds"),
                gamerscore=0,
                rarity_percent=None,
                platform="steam",
            )
        ],
        is_backfill=False,
    )

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    today_line = next(line for line in text.split("\n") if line.startswith("Сегодня"))
    assert "(🟢 1 · ⚫ 1)" in today_line


async def test_counters_show_psn_in_the_platform_breakdown(repo: Repo) -> None:
    """#32: the combined "Сегодня"/"За месяц" number already included PSN
    (a plain tg_id sum) — only the "(🟢 N · ⚫ N)" breakdown next to it
    silently had nowhere for a psn row to land."""
    await repo.ensure_user(1, "triple")
    await repo.link_xbox_account(1, XUID, "Triple", 0)
    await repo.link_platform_account(1, "steam", "76561197960287930", "TripleSteam")
    await repo.link_platform_account(1, "psn", "internal-account-id", "TriplePsn")
    await repo.insert_new_achievements(XUID, [_achievement("1")], is_backfill=False)
    await repo.insert_new_achievements_steam(
        1,
        "76561197960287930",
        [
            AchievementRow(
                title_id="550",
                achievement_id="s1",
                name="s1",
                description=None,
                icon_url=None,
                unlocked_at=utcnow().isoformat(timespec="seconds"),
                gamerscore=0,
                rarity_percent=None,
                platform="steam",
            )
        ],
        is_backfill=False,
    )
    await repo.insert_new_achievements_psn(
        1,
        "internal-account-id",
        [
            AchievementRow(
                title_id="NPWR00001_00",
                achievement_id="p1",
                name="p1",
                description=None,
                icon_url=None,
                unlocked_at=utcnow().isoformat(timespec="seconds"),
                gamerscore=0,
                rarity_percent=None,
                platform="psn",
            )
        ],
        is_backfill=False,
    )

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    today_line = next(line for line in text.split("\n") if line.startswith("Сегодня"))
    assert "(🟢 1 · 🔵 1 · ⚫ 1)" in today_line  # Xbox, PlayStation, Steam (2026-09-13)


async def test_counters_hide_breakdown_for_a_single_platform(repo: Repo) -> None:
    await repo.ensure_user(1, "xboxonly")
    await repo.link_xbox_account(1, XUID, "XboxOnly", 0)
    await repo.insert_new_achievements(XUID, [_achievement("1")], is_backfill=False)

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    today_line = next(line for line in text.split("\n") if line.startswith("Сегодня"))
    assert "🟢" not in today_line and "⚫" not in today_line


async def test_games_list_includes_steam_games(repo: Repo) -> None:
    """Found live: the games table used to be `if target.xuid:` only (SPEC
    9, M-Steam-2c's own scoping note) — recent_games() itself was never
    Xbox-specific, just never called for a Steam link. Now merged into one
    combined ranked list, same "one number, not one per platform" spirit
    as the counters above."""
    await repo.ensure_user(1, "someone")
    await repo.link_platform_account(1, "steam", "76561197960287930", "SteamPerson")
    await repo.insert_new_achievements_steam(
        1,
        "76561197960287930",
        [
            AchievementRow(
                title_id="550",
                achievement_id="a1",
                name="A",
                description=None,
                icon_url=None,
                unlocked_at=utcnow().isoformat(timespec="seconds"),
                gamerscore=0,
                rarity_percent=50.0,
                platform="steam",
                title_name="Left 4 Dead 2",
            )
        ],
        is_backfill=False,
    )

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    assert "Left 4 Dead 2" in text


async def test_nicknames_are_plain_text_by_default(repo: Repo) -> None:
    """show_profile_links defaults to 0 (Follow-up 2026-09-06) — no <a href>
    anywhere until the person opts in."""
    await repo.ensure_user(1, "someone")
    await repo.link_xbox_account(1, XUID, "Someone", 0)
    await repo.link_platform_account(1, "steam", "76561197960287930", "SteamPerson")

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    assert "<a href" not in text


async def test_nicknames_link_out_once_the_person_opts_in(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    await repo.link_xbox_account(1, XUID, "Someone", 0)
    await repo.link_platform_account(1, "steam", "76561197960287930", "SteamPerson")
    await repo.update_user_settings(1, show_profile_links=1)

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    xbox_line = next(line for line in text.split("\n") if "XBOX" in line)
    steam_line = next(line for line in text.split("\n") if line.startswith("⚫"))
    assert '<a href="https://account.xbox.com/en-us/profile?gamertag=Someone">Someone</a>' in (
        xbox_line
    )
    assert (
        '<a href="https://steamcommunity.com/profiles/76561197960287930">SteamPerson</a>'
        in steam_line
    )


async def test_opted_in_but_no_gamertag_yet_stays_plain(repo: Repo) -> None:
    """Pre-first-sync edge case (same reasoning as panel_keyboard's own
    profile-button guard) — an empty gamertag has no page to link to."""
    await repo.ensure_user(1, "someone")
    await repo.link_xbox_account(1, XUID, "", 0)
    await repo.update_user_settings(1, show_profile_links=1)

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    assert "<a href" not in text


async def test_zero_limit_shows_every_game_uncapped(repo: Repo) -> None:
    """0 means "no cap" (SPEC 6.4) — the whole point of dropping the old
    fixed-height table for a collapsible quote."""
    await repo.ensure_user(1, "someone")
    await repo.link_xbox_account(1, XUID, "Someone", 0)
    await repo.set_app_setting("stats_games_limit", "0")
    for i in range(5):
        await repo.insert_new_achievements(XUID, [_achievement(str(i))], is_backfill=False)

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    assert text.count("без названия") == 5


async def test_psn_line_says_trophies_not_achievements(repo: Repo) -> None:
    """CLAUDE.md: PSN calls its own achievements "trophies" everywhere —
    /stats' per-link line used to say "N достижений" for PSN too, same
    wording as every other platform, which was simply wrong (2026-09-08)."""
    await repo.ensure_user(1, "someone")
    await repo.link_platform_account(1, "psn", "acc-1", "PsnPerson")
    await repo.insert_new_achievements_psn(
        1,
        "acc-1",
        [
            AchievementRow(
                title_id="NPWR00001_00",
                achievement_id="p1",
                name="A",
                description=None,
                icon_url=None,
                unlocked_at=utcnow().isoformat(timespec="seconds"),
                gamerscore=0,
                rarity_percent=None,
                platform="psn",
            )
        ],
        is_backfill=True,
    )

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    psn_line = next(line for line in text.split("\n") if line.startswith("🔵"))
    assert "1 трофей" in psn_line
    assert "достижени" not in psn_line


async def test_psn_level_suffix_has_a_space_on_both_sides_of_the_dot(repo: Repo) -> None:
    """Found live: the level suffix used to be its own Fluent string with
    leading spaces, and Fluent's whitespace handling on a single-line value
    silently dropped the space before the "·" while keeping the one after —
    "242 достижения· уровень 73" (2026-09-08). The separator is now built in
    Python, like every other segment on this line."""
    await repo.ensure_user(1, "someone")
    await repo.link_platform_account(1, "psn", "acc-1", "PsnPerson")
    await repo.set_psn_trophy_level(1, 73)

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    psn_line = next(line for line in text.split("\n") if line.startswith("🔵"))
    assert "  ·  уровень 73" in psn_line


async def test_today_and_month_lines_omit_a_zero_score(repo: Repo) -> None:
    """(+0 G) on every single line was pure noise (2026-09-08, user
    request) — a Steam/PSN-only person's score is always 0."""
    await repo.ensure_user(1, "someone")
    await repo.link_platform_account(1, "steam", "76561197960287930", "SteamPerson")
    await repo.insert_new_achievements_steam(
        1,
        "76561197960287930",
        [
            AchievementRow(
                title_id="550",
                achievement_id="a1",
                name="A",
                description=None,
                icon_url=None,
                unlocked_at=utcnow().isoformat(timespec="seconds"),
                gamerscore=0,
                rarity_percent=None,
                platform="steam",
            )
        ],
        is_backfill=False,
    )

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    today_line = next(line for line in text.split("\n") if line.startswith("Сегодня"))
    month_line = next(line for line in text.split("\n") if line.startswith("За месяц"))
    assert "G)" not in today_line
    assert "G)" not in month_line


async def test_game_row_tail_omits_a_zero_score_too(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    await repo.link_xbox_account(1, XUID, "Someone", 0)
    await repo.insert_new_achievements(
        XUID,
        [
            AchievementRow(
                title_id="1",
                achievement_id="a1",
                name="A",
                description=None,
                icon_url=None,
                unlocked_at=utcnow().isoformat(timespec="seconds"),
                gamerscore=0,
                rarity_percent=None,
                platform="xbox_modern",
            )
        ],
        is_backfill=False,
    )

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    # The games list is one blockquote-wrapped block, no newline between the
    # opening tag and its first row — "1. " is a substring, not a line start.
    game_line = next(line for line in text.split("\n") if "1. " in line)
    assert "G)" not in game_line


async def test_xbox_line_shows_the_achievement_count_before_gamerscore(repo: Repo) -> None:
    """User request (2026-09-08) — see repo.py::xbox_achievement_count's own
    docstring and CLAUDE.md's Statistics rules for why this is trustworthy."""
    await repo.ensure_user(1, "someone")
    await repo.link_xbox_account(1, XUID, "Someone", 500)
    await repo.insert_new_achievements(XUID, [_achievement("1")], is_backfill=False)

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    xbox_line = next(line for line in text.split("\n") if "XBOX" in line)
    assert xbox_line.index("1 достижение") < xbox_line.index("gamerscore 500")


async def test_xbox_line_shows_completed_games_when_there_are_any(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    await repo.link_xbox_account(1, XUID, "Someone", 0)
    await repo._conn.execute(
        "INSERT INTO title_history "
        "(xuid, title_id, achievements_unlocked, achievements_total, updated_at) "
        "VALUES (?, '1', 3, 3, '2026-01-01T00:00:00+00:00')",
        (XUID,),
    )
    await repo._conn.commit()

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    xbox_line = next(line for line in text.split("\n") if "XBOX" in line)
    assert f"{COMPLETED_BADGE} 1" in xbox_line


async def test_psn_line_shows_platinum_count_when_there_are_any(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    await repo.link_platform_account(1, "psn", "acc-1", "PsnPerson")
    await repo.insert_new_achievements_psn(
        1,
        "acc-1",
        [
            AchievementRow(
                title_id="NPWR00001_00",
                achievement_id="p1",
                name="A",
                description=None,
                icon_url=None,
                unlocked_at=utcnow().isoformat(timespec="seconds"),
                gamerscore=0,
                rarity_percent=None,
                platform="psn",
                trophy_type="platinum",
            )
        ],
        is_backfill=True,
    )

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    psn_line = next(line for line in text.split("\n") if line.startswith("🔵"))
    assert f"{COMPLETED_BADGE} 1" in psn_line


async def test_steam_line_shows_completed_games_when_there_are_any(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    await repo.link_platform_account(1, "steam", "76561197960287930", "SteamPerson")
    await repo.steam_schema_cache_result(
        "550",
        "Left 4 Dead 2",
        [SteamSchemaAchievement(apiname="a1", icon="", hidden=False)],
    )
    await repo.insert_new_achievements_steam(
        1,
        "76561197960287930",
        [
            AchievementRow(
                title_id="550",
                achievement_id="a1",
                name="A",
                description=None,
                icon_url=None,
                unlocked_at=utcnow().isoformat(timespec="seconds"),
                gamerscore=0,
                rarity_percent=None,
                platform="steam",
            )
        ],
        is_backfill=False,
    )

    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)

    assert text is not None
    steam_line = next(line for line in text.split("\n") if line.startswith("⚫"))
    assert f"{COMPLETED_BADGE} 1" in steam_line


async def test_games_list_does_not_truncate_long_names() -> None:
    """User request (2026-09-08) — this list already lives inside its own
    collapsible quote, unlike /recent's row, so a long title wrapping costs
    nothing."""
    long_name = "Marvel Spider-Man Remastered Definitive Edition Deluxe Collection"
    line = _games_list([TopGame(name=long_name, gamerscore=0, unlocked=5, platform="psn")])
    assert long_name in line
    assert "…" not in line


async def test_xbox_achievement_count_counts_modern_and_x360(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    await repo.link_xbox_account(1, XUID, "Someone", 0)
    await repo.insert_new_achievements(XUID, [_achievement("1")], is_backfill=False)
    await repo.insert_new_achievements(
        XUID,
        [
            AchievementRow(
                title_id="2",
                achievement_id="x1",
                name="A",
                description=None,
                icon_url=None,
                unlocked_at=utcnow().isoformat(timespec="seconds"),
                gamerscore=10,
                rarity_percent=None,
                platform="xbox_360",
            )
        ],
        is_backfill=False,
    )

    assert await repo.xbox_achievement_count(1) == 2


async def test_xbox_completed_games_count_needs_a_nonzero_total(repo: Repo) -> None:
    await repo._conn.execute(
        "INSERT INTO title_history "
        "(xuid, title_id, achievements_unlocked, achievements_total, updated_at) "
        "VALUES (?, '1', 3, 3, '2026-01-01T00:00:00+00:00'),"
        "       (?, '2', 0, 0, '2026-01-01T00:00:00+00:00'),"
        "       (?, '3', 2, 5, '2026-01-01T00:00:00+00:00')",
        (XUID, XUID, XUID),
    )
    await repo._conn.commit()

    assert await repo.xbox_completed_games_count(XUID) == 1  # only title "1" is fully unlocked


async def test_psn_platinum_count_only_counts_platinum_rows(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    # Linked, not merely inserted (#52): a statistic counts the accounts a
    # person holds, so trophies of an unlinked account are correctly zero.
    await repo.link_platform_account(1, "psn", "acc-1", "SomeonePSN")
    await repo.insert_new_achievements_psn(
        1,
        "acc-1",
        [
            AchievementRow(
                title_id="NPWR00001_00",
                achievement_id="gold",
                name="A",
                description=None,
                icon_url=None,
                unlocked_at=utcnow().isoformat(timespec="seconds"),
                gamerscore=0,
                rarity_percent=None,
                platform="psn",
                trophy_type="gold",
            ),
            AchievementRow(
                title_id="NPWR00001_00",
                achievement_id="plat",
                name="B",
                description=None,
                icon_url=None,
                unlocked_at=utcnow().isoformat(timespec="seconds"),
                gamerscore=0,
                rarity_percent=None,
                platform="psn",
                trophy_type="platinum",
            ),
        ],
        is_backfill=True,
    )

    assert await repo.psn_platinum_count(1) == 1


async def test_steam_completed_games_count_joins_against_the_schema_cache(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    await repo.link_platform_account(1, "steam", "76561197960287930", "Someone")
    await repo.steam_schema_cache_result(
        "550",
        "Left 4 Dead 2",
        [
            SteamSchemaAchievement(apiname="a1", icon="", hidden=False),
            SteamSchemaAchievement(apiname="a2", icon="", hidden=False),
        ],
    )
    # Fully unlocked (2/2).
    await repo.insert_new_achievements_steam(
        1,
        "76561197960287930",
        [
            AchievementRow(
                title_id="550",
                achievement_id=aid,
                name=aid,
                description=None,
                icon_url=None,
                unlocked_at=utcnow().isoformat(timespec="seconds"),
                gamerscore=0,
                rarity_percent=None,
                platform="steam",
            )
            for aid in ("a1", "a2")
        ],
        is_backfill=False,
    )
    # Another game with no cached schema at all — must not crash or count.
    await repo.insert_new_achievements_steam(
        1,
        "76561197960287930",
        [
            AchievementRow(
                title_id="999",
                achievement_id="b1",
                name="B",
                description=None,
                icon_url=None,
                unlocked_at=utcnow().isoformat(timespec="seconds"),
                gamerscore=0,
                rarity_percent=None,
                platform="steam",
            )
        ],
        is_backfill=False,
    )

    assert await repo.steam_completed_games_count(1) == 1


async def test_send_stats_card_disables_the_link_preview(repo: Repo) -> None:
    """Found live (2026-09-08): a card with show_profile_links on embeds a
    real <a href> (Mad Omsk's own XBOX profile link) — Telegram attached a
    link-preview card under the message because nothing here told it not
    to, unlike connect.py's and panel.py's own links."""
    await repo.ensure_user(1, "someone")
    await repo.link_xbox_account(1, XUID, "Someone", 0)
    await repo.update_user_settings(1, show_profile_links=1)
    user = await repo.get_user(1)
    assert user is not None
    text = await _build_stats_text(repo, user)
    assert text is not None

    bot = FakeBot()
    await _send_stats_card(bot, repo, CHAT_ID, user, text)

    assert len(bot.sent) == 1
    _chat_id, _text, kwargs = bot.sent[0]
    assert kwargs.get("disable_web_page_preview") is True


def _presence_row(**over) -> ChatPresenceRow:
    base = dict(
        tg_id=1,
        gamertag=None,
        xuid=None,
        state=None,
        title_id=None,
        title_name=None,
        platform="none",
    )
    base.update(over)
    return ChatPresenceRow(**base)  # type: ignore[arg-type]


def test_who_label_prefers_the_name_then_username_then_gamertag() -> None:
    """The one person chain (#51): name first, then a bare username, then a
    platform nickname. A Telegram name now outranks a username — it is the
    more human form — and the username carries no "@"."""
    assert (
        _who_label(_presence_row(first_name="Igor", last_name="Petrov", username="mad"))
        == "Igor Petrov"
    )
    assert _who_label(_presence_row(first_name="Igor")) == "Igor"
    assert _who_label(_presence_row(username="mad", gamertag="MadXbox")) == "mad"
    assert _who_label(_presence_row(gamertag="MadXbox")) == "MadXbox"


def test_who_label_prefers_the_modern_gamertag_over_the_classic_one() -> None:
    row = _presence_row(gamertag="MadOmsk", gamertag_modern="Mad Omsk")
    assert _who_label(row) == "Mad Omsk"


def test_who_label_falls_back_to_a_platform_name_not_a_bare_id() -> None:
    # A Steam/PSN-only member with no Telegram identity — used to render "idNNNN".
    assert _who_label(_presence_row(steam_display_name="SteamNick")) == "SteamNick"
    assert _who_label(_presence_row(psn_display_name="PsnNick")) == "PsnNick"


def test_who_label_never_stops_at_the_empty_xbox_dash() -> None:
    """The account chains end at a dash so their own line renders something;
    inside the person chain that dash is an absence, and stopping on it
    would show "—" while a real PSN nickname sat one step further down."""
    assert _who_label(_presence_row(psn_display_name="PsnNick")) != "—"


def test_who_label_last_resort_is_the_id_when_nothing_else_exists() -> None:
    assert "1" in _who_label(_presence_row(tg_id=1))
