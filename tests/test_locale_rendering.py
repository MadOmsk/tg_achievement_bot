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
from bot.views.admin import render_chat_card
from bot.views.notification import format_digest, format_single
from bot.views.online import render_online_table
from bot.views.summary import DAY, build_summary

CHAT_ID = -100700
TG_ID = 7007


def _achievement(
    achievement_id: str = "a1",
    platform: str = "xbox_modern",
    device: str | None = None,
) -> AchievementRow:
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
        device=device,
    )


# ------------------------------------------------------- message formatting


def test_single_achievement_renders_in_english() -> None:
    text = format_single("Igor", _achievement(), "Halo Infinite", locale="en")
    assert text.startswith("<b>Igor</b> gets an achievement")
    assert "rarity" in text


def test_single_achievement_shows_device_in_game_line() -> None:
    row = _achievement(device="XboxSeriesX")
    text = format_single("Igor", row, "Halo Infinite", locale="ru")
    assert "🟢 XBOX Series X|S" in text


def test_single_trophy_shows_device_in_game_line() -> None:
    trophy = _achievement(platform="psn", device="PS5")
    text = format_single("Igor", trophy, "Spider-Man", locale="ru")
    assert "🔵 PlayStation 5" in text


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

    built = await build_summary(repo, CHAT_ID, 10.0, date(2026, 6, 12), locale="en", window=DAY)
    assert built is not None
    text, _markup = built
    assert "<b>The day in review</b>" in text
    assert "<b>Total:</b>" in text and "<b>Players:</b>" in text
    assert "Итоги" not in text


async def test_the_same_summary_in_russian(repo: Repo) -> None:
    """The date left the header on 2026-09-17, and with it the one case that
    genuinely differed by word order ("June 12" against "12 июня") — what is
    left to check is that every label follows the chat's language."""
    await repo.ensure_user(TG_ID)
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", TG_ID)
    await repo.subscribe(CHAT_ID, TG_ID)

    built = await build_summary(repo, CHAT_ID, 10.0, date(2026, 6, 12), locale="ru", window=DAY)
    assert built is not None
    text, _markup = built
    assert "<b>Итоги дня</b>" in text
    assert "<b>Всего:</b>" in text and "<b>Игроки:</b>" in text


# ------------------------------------------------------ the super-admin panel


async def test_the_super_admin_panel_renders_in_english(repo: Repo) -> None:
    """The super-admin's own screens follow their `user_settings.locale`,
    same as any other DM — the panel is not a special case (#48)."""
    await repo.upsert_chat(CHAT_ID, "Gaming chat", TG_ID)

    text, _markup = await render_chat_card(repo, CHAT_ID, locale="en")

    assert "Daily summary:" in text
    assert "Anti-flood:" in text
    assert "Итог дня" not in text


async def test_the_same_super_admin_screen_in_russian(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", TG_ID)

    text, _markup = await render_chat_card(repo, CHAT_ID, locale="ru")

    assert "Итог дня:" in text
    assert "Антиспам:" in text
