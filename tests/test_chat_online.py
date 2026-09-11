"""/online: presence rendering and the group hub keyboard (SPEC 6.3)."""

from __future__ import annotations

import pytest

from bot.db.repo import Repo
from bot.handlers.chat import hub_keyboard
from bot.i18n import AVAILABLE_LOCALES, gettext

XUID_A = "xuid-a"
XUID_B = "xuid-b"
CHAT_ID = -100500


def test_hub_keyboard_has_exactly_five_buttons_and_carries_the_chat_id() -> None:
    markup = hub_keyboard("mybot", CHAT_ID)
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert len(buttons) == 5
    connect_button = next(b for b in buttons if b.text == "🔗 XBOX")
    assert connect_button.url is not None
    assert f"start=connect{CHAT_ID}" in connect_button.url
    steam_button = next(b for b in buttons if b.text == "🎮 Steam")
    assert steam_button.url == "https://t.me/mybot?start=connectsteam"
    psn_button = next(b for b in buttons if b.text == "🎮 PSN")
    assert psn_button.url == "https://t.me/mybot?start=connectpsn"


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
    assert {row.platform for row in rows} == {"modern"}


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
    assert rows[0].platform == "modern"


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
    """Rewritten 2026-09-05: no more connect/subscribe walkthrough in the
    text — the hub's own buttons (hub_keyboard) already cover both,
    intuitively enough on their own — just what the bot is and the
    commands people actually come back to use.

    Checked per locale (#48): the command list is the same in every
    language, so a translation that quietly dropped one shows up here. Reads
    the key directly rather than through a module-level HELP_TEXT constant —
    that constant froze whichever locale was loaded at import time, and
    nothing in the bot itself used it."""
    help_text = gettext("chat", "chat-help-text", locale=locale)
    intro = help_text.split("\n\n")[0].lower()
    assert "xbox" in intro and "steam" in intro
    for command in ("/stats", "/online", "/who", "/recent", "/summary", "/hltb"):
        assert command in help_text
    assert "/subscribe" not in help_text
    assert "/unsubscribe" not in help_text


async def test_record_chat_seen_ignores_an_unknown_tg_id(repo: Repo) -> None:
    """Same rule as update_username: writing in a chat must not create a user
    row for someone the bot has never otherwise seen."""
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.record_chat_seen(CHAT_ID, 999999)  # no such user — must not raise

    rows = await repo.chat_member_presence(CHAT_ID)

    assert rows == []
