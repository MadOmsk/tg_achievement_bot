"""/online: presence rendering and the group hub keyboard (SPEC 6.3)."""

from __future__ import annotations

import pytest

from bot.db.repo import Repo
from bot.i18n import AVAILABLE_LOCALES, gettext
from bot.views.chat import hub_keyboard

XUID_A = "xuid-a"
XUID_B = "xuid-b"
CHAT_ID = -100500


def test_hub_keyboard_has_the_expected_buttons_and_carries_the_chat_id() -> None:
    markup = hub_keyboard("mybot", CHAT_ID)
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert len(buttons) == 11
    connect_button = next(b for b in buttons if b.text == "🔗 XBOX")
    assert connect_button.url is not None
    assert f"start=connect{CHAT_ID}" in connect_button.url
    steam_button = next(b for b in buttons if b.text == "🎮 Steam")
    assert steam_button.url == "https://t.me/mybot?start=connectsteam"
    psn_button = next(b for b in buttons if b.text == "🎮 PSN")
    assert psn_button.url == "https://t.me/mybot?start=connectpsn"
    assert any(b.callback_data == "hub:who" for b in buttons)
    assert any(b.callback_data == "hub:online" for b in buttons)
    assert any(b.callback_data == "hub:recent" for b in buttons)
    assert any(b.callback_data == "hub:summary_day" for b in buttons)
    assert any(b.callback_data == "hub:summary_month" for b in buttons)
    assert markup.inline_keyboard[-2] == [connect_button, psn_button, steam_button]
    assert markup.inline_keyboard[-1][0].callback_data == "msg:close"


def test_hub_keyboard_adds_open_app_when_mini_url_is_set() -> None:
    markup = hub_keyboard("mybot", CHAT_ID, mini_app_url="https://app.example/")
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert len(buttons) == 12
    open_app = next(b for b in buttons if b.text == "Открыть приложение")
    assert open_app.url == f"https://t.me/mybot?startapp=c{CHAT_ID}"
    assert markup.inline_keyboard[0] == [open_app]


async def test_chat_member_presence_orders_playing_first(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    for tg_id, xuid, tag in ((1, XUID_A, "Offline"), (2, XUID_B, "Playing")):
        await repo.ensure_user(tg_id, tag.lower())
        await repo.link_xbox_account(tg_id, xuid, tag, 0)
        await repo.subscribe(CHAT_ID, tg_id)
    await repo.save_presence_state(XUID_A, "Offline", None, None, changed=True)
    await repo.save_presence_state(XUID_B, "Online", "123", "Halo Infinite", changed=True)

    rows = await repo.chat_member_presence(CHAT_ID)

    assert [row.gamertag for row in rows] == ["Playing", "Offline"]
    assert {row.platform for row in rows} == {"xbox_modern"}


async def test_chat_member_presence_reports_platform_for_steam_only_and_mixed(
    repo: Repo,
) -> None:
    """SPEC 9, M-Steam-2e: platform is exposed so /online can colour the
    icon — a Steam-only person with no presence data at all yet gets
    'none' (Follow-up 2026-09-08: nothing has ever been tracked, so there
    is no platform nickname to vouch for), and whichever platform actually
    updated more recently wins for someone with both connected and tracked."""
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)

    await repo.ensure_user(1, "steamonly")
    await repo.link_platform_account(1, "steam", "76561197960287930", "SteamOnly")
    await repo.subscribe(CHAT_ID, 1)

    await repo.ensure_user(2, "both")
    await repo.link_xbox_account(2, XUID_B, "Both", 0)
    await repo.link_platform_account(2, "steam", "76561197981065056", "BothSteam")
    await repo.subscribe(CHAT_ID, 2)
    await repo.save_presence_state(XUID_B, "Online", "123", "Halo Infinite", changed=True)
    await repo.save_steam_presence_state("76561197981065056", 1, "550", "L4D2", changed=True)
    # Both writes land in the same second at second-resolution timestamps —
    # backdate the Xbox one so which is "fresher" is unambiguous, the same
    # as it always would be at real 60s-apart tick granularity.
    await repo._conn.execute(
        "UPDATE presence_state SET updated_at = '2020-01-01T00:00:00+00:00' WHERE xuid = ?",
        (XUID_B,),
    )
    await repo._conn.commit()

    rows = {row.tg_id: row for row in await repo.chat_member_presence(CHAT_ID)}

    assert rows[1].platform == "none"  # no presence data at all, only a Steam link
    assert rows[2].platform == "steam"  # both playing (tied activity level), Steam fresher


async def test_chat_member_presence_includes_a_psn_only_person(repo: Repo) -> None:
    """Bug #35, confirmed live (user keimaks): a PSN-only person (no Xbox)
    was dropped from /online and /who entirely, not just shown with no
    presence — `chat_member_presence()`'s WHERE clause never accounted for
    a `platform_links` row on 'psn'. PSN presence itself is real now
    (issue #1), but this person's account has never actually been polled
    yet (no psn_presence_state row) — same "no data", not "nobody home".

    `platform` reads 'none', not 'psn' (Follow-up 2026-09-08) — nothing has
    ever been tracked for this person, so there's no platform nickname to
    vouch for; online_view.py falls back to their Telegram name there."""
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.ensure_user(1, "psnonly")
    await repo.link_platform_account(1, "psn", "internal-account-id", "PsnOnly")
    await repo.subscribe(CHAT_ID, 1)

    rows = await repo.chat_member_presence(CHAT_ID)

    assert len(rows) == 1
    assert rows[0].tg_id == 1
    assert rows[0].platform == "none"
    assert rows[0].state is None  # no presence source for PSN yet


async def test_chat_member_presence_untracked_psn_never_outranks_real_activity(
    repo: Repo,
) -> None:
    """A PSN link with no presence ever recorded for it (psn_level 0, same
    as an untracked Xbox/Steam link) must never win over genuine Xbox
    activity for someone with all three linked."""
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.ensure_user(1, "triple")
    await repo.link_xbox_account(1, XUID_A, "Triple", 0)
    await repo.link_platform_account(1, "steam", "76561197981065056", "TripleSteam")
    await repo.link_platform_account(1, "psn", "internal-account-id", "TriplePsn")
    await repo.subscribe(CHAT_ID, 1)
    await repo.save_presence_state(XUID_A, "Online", "123", "Halo Infinite", changed=True)

    rows = await repo.chat_member_presence(CHAT_ID)

    assert len(rows) == 1
    assert rows[0].platform == "xbox_modern"


async def test_chat_member_presence_psn_wins_when_actually_playing(repo: Repo) -> None:
    """(issue #1) With a real psn_presence_state row, PSN presence now
    plays exactly the same role Xbox/Steam always have — playing beats
    everything else, same activity-level ordering."""
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.ensure_user(1, "psnplayer")
    await repo.link_xbox_account(1, XUID_A, "PsnPlayer", 0)
    await repo.link_platform_account(1, "psn", "internal-account-id", "PsnPlayerPsn")
    await repo.subscribe(CHAT_ID, 1)
    await repo.save_presence_state(XUID_A, "Online", None, None, changed=True)  # online, idle
    await repo.save_psn_presence_state(
        "internal-account-id", "Online", "CUSA14296_00", "Rust", changed=True
    )

    rows = await repo.chat_member_presence(CHAT_ID)

    assert len(rows) == 1
    row = rows[0]
    assert row.platform == "psn"
    assert row.state == "Online"
    assert row.title_id == "CUSA14296_00"
    assert row.title_name == "Rust"


async def test_chat_member_presence_psn_offline_can_still_be_the_last_active_platform(
    repo: Repo,
) -> None:
    """Same "last active platform" tie-break Xbox/Steam already had
    (Follow-up 2026-09-08), extended to a 3-way candidate set: with all
    three known-offline, the most recently polled one wins the nickname."""
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.ensure_user(1, "alloffline")
    await repo.link_xbox_account(1, XUID_A, "AllOffline", 0)
    await repo.link_platform_account(1, "steam", "76561197981065056", "AllOfflineSteam")
    await repo.link_platform_account(1, "psn", "internal-account-id", "AllOfflinePsn")
    await repo.subscribe(CHAT_ID, 1)

    await repo.save_presence_state(XUID_A, "Offline", None, None, changed=True)
    await repo.save_steam_presence_state("76561197981065056", 0, None, None, changed=True)
    await repo.save_psn_presence_state("internal-account-id", "Offline", None, None, changed=True)
    await repo._conn.execute(
        "UPDATE presence_state SET updated_at = '2020-01-01T00:00:00+00:00' WHERE xuid = ?",
        (XUID_A,),
    )
    await repo._conn.execute(
        "UPDATE steam_presence_state SET updated_at = '2020-01-02T00:00:00+00:00' "
        "WHERE steam_id = ?",
        ("76561197981065056",),
    )
    await repo._conn.commit()

    rows = await repo.chat_member_presence(CHAT_ID)

    assert len(rows) == 1
    assert rows[0].platform == "psn"  # polled most recently of the three


async def test_playing_on_one_platform_beats_merely_online_on_the_other(repo: Repo) -> None:
    """Found live: Mad Omsk was playing on Steam and merely online (not
    playing) on Xbox, but /online showed Xbox — because the first version
    of this merge compared `updated_at` alone, and Xbox happened to get
    polled a moment later (every poll bumps updated_at, changed or not).
    'Playing' must always outrank 'online' regardless of which platform
    updated more recently — freshness only breaks a tie at the *same*
    activity level (SPEC 9, M-Steam-2e, "играет > онлайн > офлайн")."""
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.ensure_user(1, "madomsk")
    await repo.link_xbox_account(1, XUID_A, "MadOmsk", 0)
    await repo.link_platform_account(1, "steam", "76561197981065056", "MadOmskSteam")
    await repo.subscribe(CHAT_ID, 1)

    # Steam: playing. Xbox: online, not playing — but polled after Steam,
    # so its updated_at is the more recent one.
    await repo.save_steam_presence_state(
        "76561197981065056", 1, "550", "Left 4 Dead 2", changed=True
    )
    await repo.save_presence_state(XUID_A, "Online", None, None, changed=True)

    rows = await repo.chat_member_presence(CHAT_ID)

    assert len(rows) == 1
    row = rows[0]
    assert row.platform == "steam"
    assert row.title_id == "550"
    assert row.title_name == "Left 4 Dead 2"


async def test_chat_member_presence_offline_shows_the_last_active_platform(repo: Repo) -> None:
    """Follow-up 2026-09-08: with both Xbox and Steam known-offline (not
    merely untracked), the more recently polled one wins the nickname —
    freshness is safe here specifically because nobody is "online" in
    either case, unlike the playing/online tie-break above where it would
    misreport who is actually active."""
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.ensure_user(1, "bothoffline")
    await repo.link_xbox_account(1, XUID_A, "BothOffline", 0)
    await repo.link_platform_account(1, "steam", "76561197981065056", "BothOfflineSteam")
    await repo.subscribe(CHAT_ID, 1)

    await repo.save_presence_state(XUID_A, "Offline", None, None, changed=True)
    await repo.save_steam_presence_state("76561197981065056", 0, None, None, changed=True)
    await repo._conn.execute(
        "UPDATE presence_state SET updated_at = '2020-01-01T00:00:00+00:00' WHERE xuid = ?",
        (XUID_A,),
    )
    await repo._conn.commit()

    rows = await repo.chat_member_presence(CHAT_ID)

    assert len(rows) == 1
    assert rows[0].platform == "steam"  # polled more recently than Xbox


async def test_chat_member_presence_carries_platform_names_and_telegram_identity(
    repo: Repo,
) -> None:
    """Follow-up 2026-09-08: online_view.py's row label needs the Steam/PSN
    display names and the Telegram identity alongside the winning platform —
    this is where they get joined in."""
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.ensure_user(1, "someone", "Igor", "Petrov")
    await repo.link_platform_account(1, "steam", "76561197981065056", "SteamNick")
    await repo.link_platform_account(1, "psn", "internal-account-id", "PsnNick")
    await repo.subscribe(CHAT_ID, 1)

    rows = await repo.chat_member_presence(CHAT_ID)

    assert len(rows) == 1
    row = rows[0]
    assert row.steam_display_name == "SteamNick"
    assert row.psn_display_name == "PsnNick"
    assert row.username == "someone"
    assert row.first_name == "Igor"
    assert row.last_name == "Petrov"


async def test_chat_exists(repo: Repo) -> None:
    assert await repo.chat_exists(CHAT_ID) is False
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    assert await repo.chat_exists(CHAT_ID) is True


async def test_online_lists_a_connected_non_publisher_who_was_seen_writing(
    repo: Repo,
) -> None:
    """/online must not be just the publisher list — someone connected who
    never pressed "Публиковать" but did write here should still show up
    (SPEC 6.3, the "test chat" bug: 2 people in the chat, /online showed 1)."""
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.ensure_user(1, "publisher")
    await repo.link_xbox_account(1, XUID_A, "Publisher", 0)
    await repo.subscribe(CHAT_ID, 1)

    await repo.ensure_user(2, "lurker")
    await repo.link_xbox_account(2, XUID_B, "Lurker", 0)
    await repo.record_chat_seen(CHAT_ID, 2)  # wrote here, never subscribed

    rows = await repo.chat_member_presence(CHAT_ID)

    assert {row.gamertag for row in rows} == {"Publisher", "Lurker"}


@pytest.mark.parametrize("locale", AVAILABLE_LOCALES)
def test_help_text_mentions_both_platforms_and_the_main_commands(locale: str) -> None:
    panel_text = gettext("chat", "chat-panel-text", locale=locale).lower()
    assert "xbox" in panel_text and "steam" in panel_text

    help_text = gettext("chat", "chat-help-text", locale=locale)
    for command in (
        "/panel",
        "/stats",
        "/online",
        "/who",
        "/recent",
        "/summary",
        "/hltb",
        "/subscribe",
        "/unsubscribe",
        "/help",
    ):
        assert command in help_text


async def test_record_chat_seen_ignores_an_unknown_tg_id(repo: Repo) -> None:
    """Same rule as update_username: writing in a chat must not create a user
    row for someone the bot has never otherwise seen."""
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.record_chat_seen(CHAT_ID, 999999)  # no such user — must not raise

    rows = await repo.chat_member_presence(CHAT_ID)

    assert rows == []


async def test_hub_callbacks(repo: Repo, i18n) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from aiogram.types import CallbackQuery, Chat, Message
    from aiogram.types import User as TgUser

    from bot.handlers.chat import (
        hub_online_callback,
        hub_recent_callback,
        hub_summary_day_callback,
        hub_summary_month_callback,
        hub_who_callback,
    )

    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    message = MagicMock(spec=Message)
    message.chat = Chat(id=CHAT_ID, type="supergroup", title="Гейминг-чат")
    message.answer = AsyncMock()

    callback = MagicMock(spec=CallbackQuery)
    callback.from_user = TgUser(id=1, is_bot=False, first_name="Tester")
    callback.message = message
    callback.answer = AsyncMock()

    bot = MagicMock()

    await hub_who_callback(callback, repo, i18n)
    assert callback.answer.called

    await hub_online_callback(callback, repo, bot, i18n)
    assert callback.answer.called

    await hub_recent_callback(callback, repo, bot, i18n)
    assert callback.answer.called

    await hub_summary_day_callback(callback, repo, bot, i18n)
    assert callback.answer.called

    await hub_summary_month_callback(callback, repo, bot, i18n)
    assert callback.answer.called


async def test_publish_command_menu_publishes_curated_group_commands() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from aiogram.types import BotCommandScopeAllGroupChats

    from bot.main import _publish_command_menu

    mock_bot = MagicMock()
    mock_bot.set_my_commands = AsyncMock()

    await _publish_command_menu(mock_bot)

    group_calls = [
        call
        for call in mock_bot.set_my_commands.call_args_list
        if isinstance(call.kwargs.get("scope"), BotCommandScopeAllGroupChats)
    ]
    assert len(group_calls) >= 1
    commands = [cmd.command for cmd in group_calls[0].args[0]]
    assert commands == ["panel", "subscribe", "hltb", "help"]
