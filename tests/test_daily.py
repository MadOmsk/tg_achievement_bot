"""Daily summary (SPEC 5.7, 7.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from datetime import date as date_type

from bot.constants import AchievementBadge
from bot.db.repo import AchievementRow, Repo
from bot.poller.daily import DailySummary, _is_last_day_of_month, _monthly_key
from bot.services.admin_settings import MONTHLY_DELAY_KEY
from bot.util import start_of_month_utc, utcnow
from bot.views.parts import platform_breakdown_suffix
from bot.views.summary import DAY, MONTH, build_summary, full_leaderboard

CHAT_ID = -100500
XUID_A = "xuid-a"
XUID_B = "xuid-b"


async def summary_text(
    repo: Repo, chat_id: int, threshold: float, today: date_type, *, window: str = MONTH
) -> str | None:
    """build_summary now also returns an optional "показать всех" keyboard —
    most of these tests only care about the text.

    Defaults to the month, which is the richer of the two shapes (it carries
    the games block as well). One window per call since 2026-09-17: the
    combined report went away with /summary."""
    built = await build_summary(repo, chat_id, threshold, today, locale="ru", window=window)
    return built[0] if built is not None else None


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> None:
        self.sent.append((chat_id, text))


def achievement(
    achievement_id: str, unlocked_at: datetime, score: int = 10, rarity: float | None = 50.0
) -> AchievementRow:
    return AchievementRow(
        title_id="1",
        achievement_id=achievement_id,
        name=achievement_id,
        description=None,
        icon_url=None,
        unlocked_at=unlocked_at.isoformat(timespec="seconds"),
        gamerscore=score,
        rarity_percent=rarity,
        platform="xbox_modern",
    )


async def _chat_with_two_players(repo: Repo) -> None:
    """Both players carry a Telegram first name as well as an Xbox gamertag —
    the summary names *people* (#51), so the leaderboard shows the first
    name and the gamertag only ever appears on a platform's own line."""
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    for tg_id, xuid, tag in ((1, XUID_A, "Igor"), (2, XUID_B, "Alex")):
        await repo.ensure_user(tg_id, tag.lower(), first_name=tag)
        await repo.link_xbox_account(tg_id, xuid, tag, 1000)
        await repo.subscribe(CHAT_ID, tg_id)


async def test_summary_lists_everyone_and_marks_rare(repo: Repo) -> None:
    await _chat_with_two_players(repo)
    now = utcnow()
    await repo.insert_new_achievements(
        XUID_A,
        [
            achievement("a1", now, 50, rarity=2.4),
            achievement("a2", now, 40, rarity=30.0),
        ],
        is_backfill=False,
    )
    # Backfilled rows count too: the summary is a report, not the feed.
    await repo.insert_new_achievements(
        XUID_B, [achievement("b1", now, 20, rarity=None)], is_backfill=True
    )

    text = await summary_text(repo, CHAT_ID, 10.0, now.date())

    assert text is not None
    assert "Igor" in text and "Alex" in text
    # One window per message since 2026-09-17, so exactly one total line and
    # one header — the combined report went away with /summary.
    assert text.count("<b>Всего:</b>") == 1
    assert text.count("<b>Итоги месяца</b>") == 1
    assert "<blockquote expandable>" in text and "</blockquote>" in text


def test_platform_breakdown_suffix_always_flag() -> None:
    """The function's own contract, direct — always=False (/stats' default)
    hides a single-platform breakdown, always=True (/summary, 2026-09-05
    second follow-up) keeps it. Either way, nothing to show stays nothing."""
    assert platform_breakdown_suffix(3, 0) == ""
    assert platform_breakdown_suffix(3, 0, always=True) == " (🟢 3)"
    assert platform_breakdown_suffix(3, 5) == " (🟢 3 · ⚫ 5)"
    assert platform_breakdown_suffix(3, 5, always=True) == " (🟢 3 · ⚫ 5)"
    assert platform_breakdown_suffix(0, 0) == ""
    assert platform_breakdown_suffix(0, 0, always=True) == ""


def test_platform_breakdown_suffix_includes_psn() -> None:
    """#32: psn_count used to have nowhere to go — the combined total this
    sits next to already included PSN (a plain tg_id sum), only this
    breakdown silently dropped it."""
    assert platform_breakdown_suffix(3, 0, 2) == " (🟢 3 · 🔵 2)"  # two platforms, shown either way
    # Xbox, PlayStation, Steam — the one display order for a platform list
    # (2026-09-13); the arguments stay in their older (xbox, steam, psn) order.
    assert platform_breakdown_suffix(3, 5, 2) == " (🟢 3 · 🔵 2 · ⚫ 5)"
    assert platform_breakdown_suffix(0, 0, 2) == ""  # one platform, always=False hides it
    assert platform_breakdown_suffix(0, 0, 2, always=True) == " (🔵 2)"


async def test_leaderboard_shows_platform_breakdown_even_for_one_platform(repo: Repo) -> None:
    """2026-09-05 follow-up, reversal of "one combined number only": a
    parenthetical next to the total. Unlike /stats (which already spells
    out each platform on its own line above the counters), the leaderboard
    has nothing else saying which platform a row's achievements came from
    — so it shows the breakdown even for a single platform (2026-09-05,
    second follow-up), where /stats stays silent (SPEC 9, M-Steam-2e's own
    leaderboard sort is untouched either way)."""
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.ensure_user(1, "both", first_name="Both")
    await repo.link_xbox_account(1, XUID_A, "Both", 0)
    await repo.link_platform_account(1, "steam", "76561197960287930", "BothSteam")
    await repo.subscribe(CHAT_ID, 1)
    await repo.ensure_user(2, "xboxonly", first_name="XboxOnly")
    await repo.link_xbox_account(2, XUID_B, "XboxOnly", 0)
    await repo.subscribe(CHAT_ID, 2)

    now = utcnow()
    await repo.insert_new_achievements(XUID_A, [achievement("a1", now)], is_backfill=False)
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
                unlocked_at=now.isoformat(timespec="seconds"),
                gamerscore=0,
                rarity_percent=None,
                platform="steam",
            )
        ],
        is_backfill=False,
    )
    await repo.insert_new_achievements(XUID_B, [achievement("b1", now)], is_backfill=False)

    # Nothing from Telegram at all — no username, no first name — so the
    # person chain has to reach the PSN nickname to name this row (#51).
    await repo.ensure_user(3)
    await repo.link_platform_account(3, "psn", "internal-account-id", "PsnOnly")
    await repo.subscribe(CHAT_ID, 3)
    await repo.insert_new_achievements_psn(
        3,
        "internal-account-id",
        [
            AchievementRow(
                title_id="NPWR00001_00",
                achievement_id="p1",
                name="p1",
                description=None,
                icon_url=None,
                unlocked_at=now.isoformat(timespec="seconds"),
                gamerscore=0,
                rarity_percent=None,
                platform="psn",
            )
        ],
        is_backfill=False,
    )

    text = await summary_text(repo, CHAT_ID, 10.0, now.date())

    assert text is not None
    both_line = next(
        line for line in text.split("\n") if "Both" in line and "BothSteam" not in line
    )
    assert "(🟢 1 · ⚫ 1)" in both_line
    xbox_only_line = next(line for line in text.split("\n") if "XboxOnly" in line)
    assert "(🟢 1)" in xbox_only_line
    # PsnOnly has no Xbox gamertag and nothing from Telegram either, so the
    # person chain walks all the way down to the PSN nickname (#51). This
    # line used to read a bare "id3": the leaderboard selected only the Xbox
    # display cache, so a member without one had no name to render at all.
    assert "id3" not in text
    psn_only_line = next(line for line in text.split("\n") if "PsnOnly" in line)
    assert "(🔵 1)" in psn_only_line  # #32 — used to have no bucket to land in at all


async def test_zero_scorers_still_appear(repo: Repo) -> None:
    """A subscriber with nothing unlocked used to vanish from the table
    entirely — the roster should show him at zero, not hide him."""
    await _chat_with_two_players(repo)
    await repo.insert_new_achievements(XUID_A, [achievement("a1", utcnow())], is_backfill=False)

    text = await summary_text(repo, CHAT_ID, 10.0, utcnow().date())

    assert text is not None
    assert "Alex" in text  # unlocked nothing, still listed


async def test_gamertag_is_escaped_inside_the_html_table(repo: Repo) -> None:
    """The list lives inside a <blockquote>; an unescaped "<" or "&" in a
    name would break the markup Telegram parses.

    No Telegram name or username here on purpose (#51): that walks the person
    chain all the way down to the gamertag, so this covers both the escaping
    and the fallback that puts a gamertag on this line at all."""
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.ensure_user(1)
    await repo.link_xbox_account(1, XUID_A, "A&B<C>", 1000)
    await repo.subscribe(CHAT_ID, 1)
    await repo.insert_new_achievements(XUID_A, [achievement("a1", utcnow())], is_backfill=False)

    text = await summary_text(repo, CHAT_ID, 10.0, utcnow().date())

    assert text is not None
    assert "<C>" not in text  # would be parsed as a (bogus) HTML tag
    assert "&amp;" in text and "&lt;" in text


async def test_a_zero_activity_day_still_sends_the_roster(repo: Repo) -> None:
    """#34: reversed from the old "stay silent" behaviour — a day nobody
    unlocked anything still produces the report, everyone at 0."""
    await _chat_with_two_players(repo)

    built = await build_summary(repo, CHAT_ID, 10.0, utcnow().date(), locale="ru")

    assert built is not None
    text, _markup = built
    assert "0 достижений" in text
    assert "Igor" in text and "Alex" in text


async def test_no_report_only_when_there_are_no_subscribed_members(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Пустой чат", 1)  # a chat, but nobody subscribed

    assert await build_summary(repo, CHAT_ID, 10.0, utcnow().date(), locale="ru") is None


async def test_window_is_a_rolling_day_not_a_calendar_one(repo: Repo) -> None:
    """The summary fires at 23:00, so a calendar window would leave 23:00–00:00
    in no report at all — every day would lose its last hour."""
    await _chat_with_two_players(repo)
    await repo.insert_new_achievements(
        XUID_A, [achievement("too-old", utcnow() - timedelta(hours=25))], is_backfill=False
    )
    # The 25h-old unlock is outside the rolling day window — the report still
    # sends (#34), it just counts zero for it.
    text = await summary_text(repo, CHAT_ID, 10.0, utcnow().date(), window=DAY)
    assert text is not None and "Всего:</b> 0 достижений" in text

    # 23 hours ago is still inside the window, even though it is another
    # calendar day for someone.
    await repo.insert_new_achievements(
        XUID_A,
        [achievement("late-yesterday", utcnow() - timedelta(hours=23))],
        is_backfill=False,
    )
    text = await summary_text(repo, CHAT_ID, 10.0, utcnow().date(), window=DAY)
    assert text is not None and "Всего:</b> 1 достижение" in text


async def test_month_window_is_the_calendar_month(repo: Repo) -> None:
    """#14: the month block counts since midnight on the 1st, not a rolling
    30 days — an unlock from the last day of *last* month is out of window
    even though it's only a day or two old."""
    await _chat_with_two_players(repo)
    await repo.insert_new_achievements(XUID_A, [achievement("today", utcnow())], is_backfill=False)
    last_month = start_of_month_utc(None) - timedelta(minutes=1)
    await repo.insert_new_achievements(
        XUID_A, [achievement("last-month", last_month)], is_backfill=False
    )

    text = await summary_text(repo, CHAT_ID, 10.0, utcnow().date())

    assert text is not None
    # Only "today" lands in the month report — "last-month" is a different
    # calendar month, however recent.
    total_line = next(line for line in text.split("\n") if line.startswith("<b>Всего:</b>"))
    assert "1 достижение" in total_line


async def test_summary_is_sent_once_per_day(repo: Repo) -> None:
    await _chat_with_two_players(repo)
    await repo.insert_new_achievements(XUID_A, [achievement("a1", utcnow())], is_backfill=False)
    await repo.update_chat_settings(
        CHAT_ID, tz_offset_min=0, daily_summary_time=datetime.now(UTC).strftime("%H:%M")
    )

    bot = FakeBot()
    job = DailySummary(bot, repo)
    await job.tick()
    await job.tick()

    assert len(bot.sent) == 1
    assert bot.sent[0][0] == CHAT_ID


async def test_summary_offers_show_all_button_only_past_the_configured_limit(
    repo: Repo,
) -> None:
    """The admin-configurable summary_top_limit (default 15) caps the table;
    past it a "Показать всех" button should appear, pointing at a fresh,
    uncapped re-fetch — not the original list carried over (SPEC 6.3)."""
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    for i in range(3):
        tg_id, xuid, tag = i + 1, f"xuid-{i}", f"Player{i}"
        await repo.ensure_user(tg_id, tag.lower(), first_name=tag)
        await repo.link_xbox_account(tg_id, xuid, tag, 0)
        await repo.subscribe(CHAT_ID, tg_id)
        await repo.insert_new_achievements(
            xuid, [achievement(f"a{i}", utcnow())], is_backfill=False
        )
    await repo.set_app_setting("summary_top_limit", "2")

    # One window per message since 2026-09-17, so each carries its own button.
    for window in (DAY, MONTH):
        built = await build_summary(
            repo, CHAT_ID, 10.0, utcnow().date(), locale="ru", window=window
        )

        assert built is not None
        text, markup = built
        assert markup is not None
        buttons = [b for row in markup.inline_keyboard for b in row]
        assert any(b.callback_data == f"summary:all:{window}" for b in buttons)
        # Only 2 of the 3 players make it into the capped table.
        players = text.split("<b>Игроки:</b>")[1]
        assert sum(players.count(f"Player{i}") for i in range(3)) == 2


async def test_summary_top_limit_zero_means_no_cap(repo: Repo) -> None:
    """0 means "no cap" (SPEC 6.4) — everyone fits in the list, so there is
    nothing left for a «Показать всех» button to add."""
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    for i in range(3):
        tg_id, xuid, tag = i + 1, f"xuid-{i}", f"Player{i}"
        await repo.ensure_user(tg_id, tag.lower(), first_name=tag)
        await repo.link_xbox_account(tg_id, xuid, tag, 0)
        await repo.subscribe(CHAT_ID, tg_id)
        await repo.insert_new_achievements(
            xuid, [achievement(f"a{i}", utcnow())], is_backfill=False
        )
    await repo.set_app_setting("summary_top_limit", "0")

    built = await build_summary(repo, CHAT_ID, 10.0, utcnow().date(), locale="ru")

    assert built is not None
    text, markup = built
    assert markup is None  # nothing truncated, nothing to show more of
    assert all(f"Player{i}" in text for i in range(3))

    full = await full_leaderboard(repo, CHAT_ID, 10.0, "day", locale="ru")
    assert full is not None
    assert all(f"Player{i}" in full for i in range(3))


async def test_summary_has_no_show_all_button_under_the_limit(repo: Repo) -> None:
    await _chat_with_two_players(repo)
    await repo.insert_new_achievements(XUID_A, [achievement("a1", utcnow())], is_backfill=False)

    built = await build_summary(repo, CHAT_ID, 10.0, utcnow().date(), locale="ru")

    assert built is not None
    _text, markup = built
    assert markup is None


async def test_chat_rare_threshold_defaults_and_updates(repo: Repo) -> None:
    """Every chat has a real threshold from creation, no shared fallback
    (SPEC 5.5) — admin_chats()/publication_targets() both read this column."""
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)

    chat = next(c for c in await repo.admin_chats() if c.chat_id == CHAT_ID)
    assert chat.rare_threshold_percent == 10.0  # the hardcoded default for new chats

    await repo.update_chat_settings(CHAT_ID, rare_threshold_percent=7.5)
    chat = next(c for c in await repo.admin_chats() if c.chat_id == CHAT_ID)
    assert chat.rare_threshold_percent == 7.5


async def test_chat_own_summary_time_and_zone_decide_when_it_fires(repo: Repo) -> None:
    """A chat's own daily_summary_time/tz_offset_min (SPEC 5.7) are what the
    scheduler checks — no shared value behind them any more."""
    await _chat_with_two_players(repo)
    await repo.insert_new_achievements(XUID_A, [achievement("a1", utcnow())], is_backfill=False)
    own_time = datetime.now(UTC).strftime("%H:%M")
    await repo.update_chat_settings(CHAT_ID, daily_summary_time=own_time, tz_offset_min=0)

    bot = FakeBot()
    await DailySummary(bot, repo).tick()

    assert len(bot.sent) == 1
    assert bot.sent[0][0] == CHAT_ID


async def test_chat_own_time_does_not_fire_outside_its_own_slot(repo: Repo) -> None:
    """A time that does NOT match "now" must not fire."""
    await _chat_with_two_players(repo)
    await repo.insert_new_achievements(XUID_A, [achievement("a1", utcnow())], is_backfill=False)
    now = datetime.now(UTC).strftime("%H:%M")
    off_hour = "00:00" if now != "00:00" else "00:01"  # keep it distinct from "now"
    await repo.update_chat_settings(CHAT_ID, daily_summary_time=off_hour, tz_offset_min=0)

    bot = FakeBot()
    await DailySummary(bot, repo).tick()

    assert bot.sent == []


async def test_disabled_chat_gets_nothing(repo: Repo) -> None:
    await _chat_with_two_players(repo)
    await repo.insert_new_achievements(XUID_A, [achievement("a1", utcnow())], is_backfill=False)
    await repo.update_chat_settings(
        CHAT_ID,
        daily_summary=0,
        tz_offset_min=0,
        daily_summary_time=datetime.now(UTC).strftime("%H:%M"),
    )

    bot = FakeBot()
    await DailySummary(bot, repo).tick()

    assert bot.sent == []


def test_is_last_day_of_month() -> None:
    assert _is_last_day_of_month(date_type(2026, 9, 30)) is True
    assert _is_last_day_of_month(date_type(2026, 9, 29)) is False
    assert _is_last_day_of_month(date_type(2026, 2, 28)) is True  # 2026 is not a leap year
    assert _is_last_day_of_month(date_type(2026, 12, 31)) is True


def test_monthly_key_cannot_collide_with_a_daily_marker() -> None:
    key = _monthly_key(date_type(2026, 9, 30))
    assert key == "2026-09-monthly"
    # A real daily marker is report_date.isoformat() — never has this suffix.
    assert "monthly" in key and key != date_type(2026, 9, 30).isoformat()


async def test_scheduled_daily_report_has_no_month_block(repo: Repo) -> None:
    await _chat_with_two_players(repo)
    await repo.insert_new_achievements(XUID_A, [achievement("a1", utcnow())], is_backfill=False)

    built = await build_summary(repo, CHAT_ID, 10.0, utcnow().date(), locale="ru", window=DAY)

    assert built is not None
    text, _markup = built
    assert "<b>Итоги дня</b>" in text
    assert "Всего:</b>" in text
    assert "<b>с 1 " not in text


async def test_month_end_wrapup_is_month_block_only(repo: Repo) -> None:
    await _chat_with_two_players(repo)
    await repo.insert_new_achievements(XUID_A, [achievement("a1", utcnow())], is_backfill=False)

    built = await build_summary(repo, CHAT_ID, 10.0, utcnow().date(), locale="ru", window=MONTH)

    assert built is not None
    text, _markup = built
    assert "<b>Итоги месяца</b>" in text
    assert "<b>Всего:</b>" in text
    assert "<b>Итоги дня</b>" not in text
    assert "Igor" in text and "Alex" in text  # still the full roster


async def test_both_windows_call_out_a_rare_pull(repo: Repo) -> None:
    """Reverses #9, which dropped the 💎 from the day block only (owner,
    2026-09-17): the two reports are now one form with a different cutoff,
    and one form is easier to read across two messages than two that are
    nearly the same."""
    await _chat_with_two_players(repo)
    await repo.insert_new_achievements(
        XUID_A, [achievement("a1", utcnow(), 50, rarity=2.4)], is_backfill=False
    )

    for window in (DAY, MONTH):
        text = await summary_text(repo, CHAT_ID, 10.0, utcnow().date(), window=window)
        assert text is not None
        assert AchievementBadge.DIAMOND in text


async def test_monthly_summary_includes_a_games_block(repo: Repo) -> None:
    """#7, user request: the monthly summary lists which games the chat
    actually played this month, with achievement/trophy counts — not just
    who played, `_section`'s own job."""
    await _chat_with_two_players(repo)
    await repo.insert_new_achievements(
        XUID_A, [achievement("a1", utcnow()), achievement("a2", utcnow())], is_backfill=False
    )
    await repo.upsert_title("1", "Halo Infinite", "xbox_modern")

    text = await summary_text(repo, CHAT_ID, 10.0, utcnow().date())

    assert text is not None
    assert "<b>Игры:</b>" in text
    games_section = text.split("<b>Игры:</b>")[1]
    assert "Halo Infinite" in games_section
    assert "2 достижения" in games_section


async def test_games_block_shows_platform_icon_and_gamerscore(repo: Repo) -> None:
    """(2026-09-08, user request) — the games block now leads with the same
    platform icon /stats' own games list uses, and shows gamerscore for a
    Xbox/Steam game (skipped when it's 0, `score_suffix`'s own rule)."""
    await _chat_with_two_players(repo)
    await repo.insert_new_achievements(
        XUID_A, [achievement("a1", utcnow(), score=50)], is_backfill=False
    )
    await repo.upsert_title("1", "Halo Infinite", "xbox_modern")

    text = await summary_text(repo, CHAT_ID, 10.0, utcnow().date())

    assert text is not None
    games_section = text.split("<b>Игры:</b>")[1]
    assert "🟢 " in games_section and "Halo Infinite" in games_section
    assert "(+50 G)" in games_section


async def test_games_block_shows_psn_tier_breakdown_not_gamerscore(repo: Repo) -> None:
    """PSN games show a per-tier trophy breakdown instead of gamerscore
    (2026-09-08, user request) — same tier icons TROPHY_TIER_BADGE uses
    everywhere else on a PSN row."""
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.ensure_user(1, "someone")
    await repo.link_platform_account(1, "psn", "acc-1", "PsnPerson")
    await repo.subscribe(CHAT_ID, 1)
    await repo.insert_new_achievements_psn(
        1,
        "acc-1",
        [
            AchievementRow(
                title_id="NPWR00001_00",
                achievement_id="gold1",
                name="gold1",
                description=None,
                icon_url=None,
                unlocked_at=utcnow().isoformat(timespec="seconds"),
                gamerscore=0,
                rarity_percent=None,
                platform="psn",
                title_name="Astro Bot",
                trophy_type="gold",
            ),
            AchievementRow(
                title_id="NPWR00001_00",
                achievement_id="bronze1",
                name="bronze1",
                description=None,
                icon_url=None,
                unlocked_at=utcnow().isoformat(timespec="seconds"),
                gamerscore=0,
                rarity_percent=None,
                platform="psn",
                title_name="Astro Bot",
                trophy_type="bronze",
            ),
        ],
        is_backfill=False,
    )

    text = await summary_text(repo, CHAT_ID, 10.0, utcnow().date())

    assert text is not None
    games_section = text.split("<b>Игры:</b>")[1]
    assert "🔵 " in games_section and "Astro Bot" in games_section
    assert "2 трофея" in games_section
    assert AchievementBadge.GOLD in games_section
    assert AchievementBadge.BRONZE in games_section
    assert " G)" not in games_section


async def test_the_day_report_has_a_games_block_too(repo: Repo) -> None:
    """Owner, 2026-09-17: the day report is the same form with a different
    cutoff, games block included. It was month-only while the month was the
    only report that had one at all (#7)."""
    await _chat_with_two_players(repo)
    await repo.insert_new_achievements(XUID_A, [achievement("a1", utcnow())], is_backfill=False)

    built = await build_summary(repo, CHAT_ID, 10.0, utcnow().date(), locale="ru", window=DAY)

    assert built is not None
    text, _markup = built
    assert "<b>Игры:</b>" in text


async def test_a_quiet_day_has_no_games_block(repo: Repo) -> None:
    """Nothing earned in the window, so nothing to rank — the roster still
    sends (#34), it just has no games under it."""
    await _chat_with_two_players(repo)
    await repo.insert_new_achievements(
        XUID_A, [achievement("old", utcnow() - timedelta(hours=30))], is_backfill=False
    )

    built = await build_summary(repo, CHAT_ID, 10.0, utcnow().date(), locale="ru", window=DAY)

    assert built is not None
    text, _markup = built
    assert "<b>Игроки:</b>" in text
    assert "<b>Игры:</b>" not in text


async def test_month_end_wrapup_trails_daily_summary_by_five_minutes(repo: Repo) -> None:
    """#74: on the last day of the month, the month-end wrap-up sends five minutes
    after the daily summary rather than at the same minute."""
    await _chat_with_two_players(repo)
    sept_30 = datetime(2026, 9, 30, 20, 0, tzinfo=UTC)
    await repo.insert_new_achievements(
        XUID_A, [achievement("a1", sept_30 - timedelta(hours=2))], is_backfill=False
    )
    await repo.update_chat_settings(CHAT_ID, daily_summary_time="20:00", tz_offset_min=0)

    bot = FakeBot()
    job = DailySummary(bot, repo)

    # 1. At 20:00: only the daily summary fires.
    await job.tick(now=sept_30)
    assert len(bot.sent) == 1
    assert "<b>Итоги дня</b>" in bot.sent[0][1]
    assert "<b>Итоги месяца</b>" not in bot.sent[0][1]

    # 2. Before +5m: nothing fires.
    await job.tick(now=sept_30 + timedelta(minutes=4))
    assert len(bot.sent) == 1

    # 3. At 20:05 (+5m): the month-end wrap-up fires.
    await job.tick(now=sept_30 + timedelta(minutes=5))
    assert len(bot.sent) == 2
    assert "<b>Итоги месяца</b>" in bot.sent[1][1]

    # 4. Subsequent ticks: nothing re-sends.
    await job.tick(now=sept_30 + timedelta(minutes=5))
    await job.tick(now=sept_30 + timedelta(minutes=6))
    assert len(bot.sent) == 2


async def test_monthly_wrapup_does_not_fire_on_non_last_day_of_month(repo: Repo) -> None:
    """#74: on a normal day, the +5m tick does not send a monthly report."""
    await _chat_with_two_players(repo)
    sept_29 = datetime(2026, 9, 29, 20, 0, tzinfo=UTC)
    await repo.insert_new_achievements(
        XUID_A, [achievement("a1", sept_29 - timedelta(hours=2))], is_backfill=False
    )
    await repo.update_chat_settings(CHAT_ID, daily_summary_time="20:00", tz_offset_min=0)

    bot = FakeBot()
    job = DailySummary(bot, repo)

    # Daily report fires.
    await job.tick(now=sept_29)
    assert len(bot.sent) == 1
    assert "<b>Итоги дня</b>" in bot.sent[0][1]

    # Five minutes later: no monthly report because Sept 29 is not month-end.
    await job.tick(now=sept_29 + timedelta(minutes=5))
    assert len(bot.sent) == 1


async def test_month_end_wrapup_near_midnight_rollover_into_next_month(repo: Repo) -> None:
    """#74: a chat whose summary time is within five minutes of midnight (e.g. 23:58)
    fires its month-end wrap-up at 00:03 on the 1st of the next month.
    The wrap-up must still fire and must cover the month that just ended."""
    await _chat_with_two_players(repo)
    # Achievement earned in September
    sept_ach = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    await repo.insert_new_achievements(
        XUID_A, [achievement("sept-ach", sept_ach)], is_backfill=False
    )
    # Achievement earned in October after midnight
    oct_ach = datetime(2026, 10, 1, 0, 1, tzinfo=UTC)
    await repo.insert_new_achievements(XUID_B, [achievement("oct-ach", oct_ach)], is_backfill=False)

    await repo.update_chat_settings(CHAT_ID, daily_summary_time="23:58", tz_offset_min=0)

    bot = FakeBot()
    job = DailySummary(bot, repo)

    # 1. On Sept 30 at 23:58: daily report fires.
    now_2358 = datetime(2026, 9, 30, 23, 58, tzinfo=UTC)
    await job.tick(now=now_2358)
    assert len(bot.sent) == 1
    assert "<b>Итоги дня</b>" in bot.sent[0][1]
    assert await repo.daily_report_sent(CHAT_ID, "2026-09-30") is True

    # 2. On Oct 1 at 00:03 (+5m into next month): monthly report for September fires!
    now_0003 = datetime(2026, 10, 1, 0, 3, tzinfo=UTC)
    await job.tick(now=now_0003)
    assert len(bot.sent) == 2
    month_text = bot.sent[1][1]
    assert "<b>Итоги месяца</b>" in month_text
    # Month report covers September: contains sept-ach, excludes oct-ach.
    assert "1 достижение" in month_text
    # Dedup marker is for September:
    assert await repo.daily_report_sent(CHAT_ID, "2026-09-monthly") is True


async def test_month_end_wrapup_respects_custom_delay_setting(repo: Repo) -> None:
    """The month-end delay obeys the admin variable
    (app_settings['monthly_summary_delay_minutes'])."""
    await _chat_with_two_players(repo)
    await repo.set_app_setting(MONTHLY_DELAY_KEY, "10")
    sept_30 = datetime(2026, 9, 30, 20, 0, tzinfo=UTC)
    await repo.insert_new_achievements(
        XUID_A, [achievement("a1", sept_30 - timedelta(hours=2))], is_backfill=False
    )
    await repo.update_chat_settings(CHAT_ID, daily_summary_time="20:00", tz_offset_min=0)

    bot = FakeBot()
    job = DailySummary(bot, repo)

    # 1. At 20:00: daily summary fires.
    await job.tick(now=sept_30)
    assert len(bot.sent) == 1

    # 2. At 20:05 (default delay, but admin set 10m): nothing fires.
    await job.tick(now=sept_30 + timedelta(minutes=5))
    assert len(bot.sent) == 1

    # 3. At 20:10 (custom delay): monthly wrap-up fires!
    await job.tick(now=sept_30 + timedelta(minutes=10))
    assert len(bot.sent) == 2
    assert "<b>Итоги месяца</b>" in bot.sent[1][1]


async def test_month_end_wrapup_zero_delay_sends_immediately(repo: Repo) -> None:
    """When delay is 0, both reports send in the same tick (the legacy behavior)."""
    await _chat_with_two_players(repo)
    await repo.set_app_setting(MONTHLY_DELAY_KEY, "0")
    sept_30 = datetime(2026, 9, 30, 20, 0, tzinfo=UTC)
    await repo.insert_new_achievements(
        XUID_A, [achievement("a1", sept_30 - timedelta(hours=2))], is_backfill=False
    )
    await repo.update_chat_settings(CHAT_ID, daily_summary_time="20:00", tz_offset_min=0)

    bot = FakeBot()
    job = DailySummary(bot, repo)

    # At 20:00: both daily and monthly send in the same tick.
    await job.tick(now=sept_30)
    assert len(bot.sent) == 2
    assert "<b>Итоги дня</b>" in bot.sent[0][1]
    assert "<b>Итоги месяца</b>" in bot.sent[1][1]
