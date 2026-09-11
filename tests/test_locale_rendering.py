"""What a chat actually receives renders in that chat's own language (#48).

The locale seam is only worth anything if it survives the trip from
chat_settings to the message text, through code paths that have no aiogram
context to carry it — the publisher, the daily summary, the /online
auto-refresh. These tests walk that trip.

They also pin the two queries that hand a chat's locale to the pollers.
Both `ChatTarget` and `ChatDailySettings` default `locale` to "ru" for the
call sites that build them by hand, which means a query forgetting to SELECT
the column fails silently and renders Russian into an English chat — found
exactly that way in `admin_chats()` while writing this.
"""

from __future__ import annotations

from datetime import date

from bot.db.repo import AchievementRow, Repo
from bot.poller.daily import build_summary
from bot.services.achievements import format_digest, format_single
from bot.services.online_view import render_online_table

CHAT_ID = -100700
TG_ID = 7007


def _achievement(achievement_id: str = "a1", platform: str = "modern") -> AchievementRow:
    return AchievementRow(
        title_id="t1",
        achievement_id=achievement_id,
        name="Ashes to Ashes",
        description=None,
        icon_url=None,
        unlocked_at="2026-09-02T10:00:00+00:00",
        gamerscore=10,
        rarity_percent=2.5,
        platform=platform,
        title_name="Halo Infinite",
    )


# ------------------------------------------------------- message formatting


def test_single_achievement_renders_in_english() -> None:
    text = format_single("Igor", _achievement(), "Halo Infinite", locale="en")
    assert text.startswith("<b>Igor</b> gets an achievement")
    assert "rarity" in text


def test_single_trophy_keeps_psns_own_word_in_english() -> None:
    trophy = _achievement(platform="psn")
    text = format_single("Igor", trophy, "Bloodborne", locale="en")
    assert text.startswith("<b>Igor</b> gets a trophy")


def test_digest_counts_in_english_plurals() -> None:
    items = [_achievement("a1"), _achievement("a2")]
    text = format_digest("Igor", "Halo Infinite", items, locale="en")
    # "2 achievements", not Russian's "few" form — English's own CLDR
    # categories, chosen by Fluent from the en bundle.
    assert "gets 2 achievements" in text


def test_all_psn_digest_says_trophies_in_english() -> None:
    items = [_achievement("a1", platform="psn"), _achievement("a2", platform="psn")]
    assert "gets 2 trophies" in format_digest("Igor", "Bloodborne", items, locale="en")


def test_the_same_batch_still_renders_russian() -> None:
    items = [_achievement("a1"), _achievement("a2")]
    assert "получает 2 достижения" in format_digest("Igor", "Halo Infinite", items, locale="ru")


def test_online_table_renders_in_english() -> None:
    assert "Who's online" in render_online_table([], "14:32", "en")
    assert "Updated: 14:32" in render_online_table([], "14:32", "en")


# ------------------------------------------- the queries that carry a locale


async def test_publication_targets_carry_the_chats_locale(repo: Repo) -> None:
    await repo.ensure_user(TG_ID)
    await repo.upsert_chat(CHAT_ID, "Gaming chat", TG_ID)
    await repo.subscribe(CHAT_ID, TG_ID)
    await repo.update_chat_settings(CHAT_ID, locale="en")

    targets = await repo.publication_targets(TG_ID)
    assert [target.locale for target in targets] == ["en"]


async def test_admin_chats_carry_the_chats_locale(repo: Repo) -> None:
    # The daily summary reads its locale off exactly this query.
    await repo.ensure_user(TG_ID)
    await repo.upsert_chat(CHAT_ID, "Gaming chat", TG_ID)
    await repo.update_chat_settings(CHAT_ID, locale="en")

    chats = await repo.admin_chats()
    assert [chat.locale for chat in chats if chat.chat_id == CHAT_ID] == ["en"]


async def test_chat_daily_settings_carry_the_chats_locale(repo: Repo) -> None:
    # /summary, /online and the /online auto-refresh all read it off this one.
    await repo.upsert_chat(CHAT_ID, "Gaming chat", TG_ID)
    await repo.update_chat_settings(CHAT_ID, locale="en")

    assert (await repo.get_chat_daily_settings(CHAT_ID)).locale == "en"


# -------------------------------------------------------------- the summary


async def test_daily_summary_renders_in_the_chats_language(repo: Repo) -> None:
    await repo.ensure_user(TG_ID)
    await repo.upsert_chat(CHAT_ID, "Gaming chat", TG_ID)
    await repo.subscribe(CHAT_ID, TG_ID)

    built = await build_summary(
        repo, CHAT_ID, 10.0, date(2026, 6, 12), locale="en", with_day=True, with_month=False
    )
    assert built is not None
    text, _markup = built
    assert "<b>Daily summary</b>, June 12" in text  # month before day in English
    assert "24 hours" in text


async def test_the_same_summary_in_russian_keeps_its_own_word_order(repo: Repo) -> None:
    await repo.ensure_user(TG_ID)
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", TG_ID)
    await repo.subscribe(CHAT_ID, TG_ID)

    built = await build_summary(
        repo, CHAT_ID, 10.0, date(2026, 6, 12), locale="ru", with_day=True, with_month=False
    )
    assert built is not None
    text, _markup = built
    assert "<b>Итог дня</b>, 12 июня" in text  # day before month, genitive
