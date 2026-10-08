"""Admin panel helpers that don't need a router (SPEC 6.4)."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.poller.message_cleanup import TTL_SETTING_KEY as SYSTEM_MESSAGE_TTL_KEY
from bot.poller.online_refresh import REFRESH_INTERVAL_KEY as ONLINE_REFRESH_INTERVAL_KEY
from bot.services.admin_registry import find, value_label
from bot.services.admin_registry import values as registry_values
from bot.services.admin_settings import (
    ACCOUNT_RESET_COOLDOWN_HOURS_KEY,
    LIMIT_MAX,
    LIMIT_MIN,
    MONTHLY_DELAY_KEY,
    NUMERIC_SETTINGS,
    RARE_THRESHOLD_MAX,
    RARE_THRESHOLD_MIN,
    SHOW_LINKS_KEY,
    TOP_LIMIT_KEY,
    unlimited_label,
)
from bot.views.admin import render_user_list
from bot.views.admin_home import format_api_usage
from bot.views.admin_settings import render_setting_prompt, render_settings_group


def test_api_usage_formats_seconds_and_minutes() -> None:
    text = format_api_usage([(3, 100, 15.0), (12, 300, 300.0)], locale="ru")
    assert text == "3/100 за 15с · 12/300 за 5 мин"


def test_api_usage_with_no_windows() -> None:
    assert format_api_usage([], locale="ru") == "нет данных"


def test_threshold_bounds_reject_zero_and_over_a_hundred() -> None:
    # 0 would mean "nothing is ever rare" — indistinguishable from a typo.
    assert not (RARE_THRESHOLD_MIN <= 0 <= RARE_THRESHOLD_MAX)
    assert not (RARE_THRESHOLD_MIN <= 100.5 <= RARE_THRESHOLD_MAX)
    assert RARE_THRESHOLD_MIN <= 7.5 <= RARE_THRESHOLD_MAX


def test_row_limit_bounds_reject_zero_and_absurdly_large() -> None:
    assert not (LIMIT_MIN <= 0 <= LIMIT_MAX)
    assert not (LIMIT_MIN <= 500 <= LIMIT_MAX)
    assert LIMIT_MIN <= 15 <= LIMIT_MAX


def _row(screen, key: str):
    return next(
        b for row in screen.keyboard.inline_keyboard for b in row if b.callback_data == f"a:s:{key}"
    )


async def test_profile_links_are_a_global_switch_on_by_default(repo: Repo) -> None:
    """The admin's one switch for everybody (owner, 2026-09-29), in the
    settings' «Правила» group."""

    async def rules():
        return render_settings_group("rules", await registry_values(repo, "global"), locale="ru")

    assert "да" in _row(await rules(), SHOW_LINKS_KEY).text
    await repo.set_app_setting(SHOW_LINKS_KEY, "0")
    assert "нет" in _row(await rules(), SHOW_LINKS_KEY).text


def test_only_summary_stats_and_ttl_limits_allow_zero() -> None:
    """0 means "no cap" (SPEC 6.4) — meaningful for a list inside a
    collapsible quote, not for hltb_page_size (feeds a keyboard grid) or
    hltb_results_limit (a search pool of 0 is just broken). system_message_
    ttl_min/online_refresh_interval_min's own 0 means "off" instead
    (2026-09-05 follow-up), a different zero_label but the same
    allowed-at-zero treatment."""
    zero_allowed = {key for key, spec in NUMERIC_SETTINGS.items() if spec.min == 0}
    assert zero_allowed == {
        "summary_top_limit",
        "stats_games_limit",
        SYSTEM_MESSAGE_TTL_KEY,
        ONLINE_REFRESH_INTERVAL_KEY,
        MONTHLY_DELAY_KEY,
        ACCOUNT_RESET_COOLDOWN_HOURS_KEY,
    }


def test_a_zero_is_worded_by_what_it_means() -> None:
    delay = find("global", MONTHLY_DELAY_KEY)
    assert value_label(delay, 0, locale="ru") == "без задержки"
    assert value_label(delay, 0, locale="en") == "no delay"
    top = find("global", "summary_top_limit")
    assert value_label(top, 0, locale="ru") == unlimited_label("ru")
    assert value_label(top, 15, locale="ru") == "15"
    # system_message_ttl_min's 0 disables the auto-delete, it is not unlimited.
    assert value_label(find("global", SYSTEM_MESSAGE_TTL_KEY), 0, locale="ru") == "выключено"


def test_every_numeric_setting_default_is_within_its_own_bounds() -> None:
    """Would have caught a typo'd bound the moment it landed, rather than
    only when an admin happened to hit it (2026-09-05, NUMERIC_SETTINGS
    registry refactor)."""
    for key, spec in NUMERIC_SETTINGS.items():
        assert spec.min <= spec.default <= spec.max, key


def test_a_number_whose_minimum_is_zero_says_what_its_zero_means() -> None:
    """The prompt once raised for every setting allowing 0 (#63's audit) — no
    test went past the keyboard."""
    screen = render_setting_prompt(
        find("global", TOP_LIMIT_KEY), 15, locale="ru", back="a:sg:lists"
    )
    assert "без ограничения" in screen.text
    assert screen.keyboard is not None


def test_a_number_with_a_real_minimum_has_no_zero_hint() -> None:
    screen = render_setting_prompt(
        find("global", "hltb_page_size"), 5, locale="ru", back="a:sg:hltb"
    )
    assert "0 —" not in screen.text


async def test_render_user_list_shows_visibility_icons_on_body_and_buttons(
    repo: Repo,
) -> None:
    # User 1: Xbox (active) + Steam (hidden) + PSN (visible)
    await repo.ensure_user(1, "allplatforms", "Alex")
    await repo.link_xbox_account(await repo.person_id(1), "xuid-1", "AlexXbox", 100)
    await repo.save_refresh_token(await repo.person_id(1), b"enc")
    await repo.link_platform_account(await repo.person_id(1), "steam", "steam-1", "AlexSteam")
    await repo.link_platform_account(await repo.person_id(1), "psn", "psn-1", "AlexPsn")
    await repo.set_achievements_visible(await repo.person_id(1), "steam", False)
    await repo.set_achievements_visible(await repo.person_id(1), "psn", True)

    # User 2: PSN only (hidden)
    await repo.ensure_user(2, "psnonly", "Igor")
    await repo.link_platform_account(await repo.person_id(2), "psn", "psn-2", "IgorPsn")
    await repo.set_achievements_visible(await repo.person_id(2), "psn", False)

    text, markup = await render_user_list(repo, 0, locale="ru")

    # Body check
    assert "🟢✅⚫⚠️🔵✅" in text
    assert "🔵⚠️" in text

    # Buttons check
    button_texts = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("🟢✅⚫⚠️🔵✅" in btn_text for btn_text in button_texts)
    assert any("🔵⚠️" in btn_text for btn_text in button_texts)


async def test_the_rarity_threshold_is_a_global_setting(repo: Repo) -> None:
    """One threshold for every chat (owner, 2026-10-01): the first row of the
    settings' «Правила», never on a chat's card."""
    from bot.views.admin import render_chat_card

    await repo.upsert_chat(-100, "Гейминг-чат", 1)

    async def rules():
        return render_settings_group("rules", await registry_values(repo, "global"), locale="ru")

    first = (await rules()).keyboard.inline_keyboard[0][0]
    assert first.callback_data == "a:s:rare_threshold_percent" and ": 10 " in first.text

    await repo.set_app_setting("rare_threshold_percent", "7.5")
    assert ": 7.5 " in (await rules()).keyboard.inline_keyboard[0][0].text

    text, markup = await render_chat_card(repo, -100, locale="ru")
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert not any(cb and "rare_threshold" in cb for cb in callbacks)
    assert "Порог" not in text
