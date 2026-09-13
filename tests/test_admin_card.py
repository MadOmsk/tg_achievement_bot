"""The admin user card (2026-09-08 rework, user request): Telegram identity
up top, one block per connected platform (nickname/id + lifetime count +
today's count [+ completions/level] + admin-only diagnostics), and a
"reset & resync" button next to each platform's refresh button."""

from __future__ import annotations

from bot.db.repo import AchievementRow, Repo
from bot.handlers.admin import _card
from bot.util import utcnow

XUID = "xuid-admin-card"


def _callback_datas(markup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row if btn.callback_data]


def _block(text: str, header_marker: str) -> list[str]:
    """The lines of one platform block (2026-09-08 restructure: nickname,
    id, status, achievements, [online] — five fixed lines, four for PSN)
    — from its header line up to the next blank line."""
    lines = text.split("\n")
    start = next(i for i, line in enumerate(lines) if header_marker in line)
    end = lines.index("", start)
    return lines[start:end]


def _achievement(title_id: str, platform: str, **overrides: object) -> AchievementRow:
    base = dict(
        title_id=title_id,
        achievement_id=f"{platform}-{title_id}-a1",
        name="A",
        description=None,
        icon_url=None,
        unlocked_at=utcnow().isoformat(timespec="seconds"),
        gamerscore=10,
        rarity_percent=None,
        platform=platform,
    )
    base.update(overrides)
    return AchievementRow(**base)  # type: ignore[arg-type]


async def test_header_shows_full_telegram_identity_not_just_one_name(repo: Repo) -> None:
    """Unlike /stats' header (one best name), the admin card shows
    everything at once: name, username, and tg_id together."""
    await repo.ensure_user(7, "igorp", "Igor", "Petrov")
    await repo.link_xbox_account(7, XUID, "GamerTag", 0)

    text, _markup = await _card(repo, 7, locale="ru")

    header = text.split("\n")[0]
    assert "Igor Petrov" in header
    assert "@igorp" in header
    assert "tg_id 7" in header


async def test_header_tgid_is_never_at_prefixed(repo: Repo) -> None:
    """A bare tg_id is not a real, resolvable username — only a genuine
    `user.username` earns the "@" (2026-09-08 user request)."""
    await repo.ensure_user(7, None, None, None)
    await repo.link_xbox_account(7, XUID, "GamerTag", 0)

    text, _markup = await _card(repo, 7, locale="ru")

    header = text.split("\n")[0]
    assert "tg_id 7" in header
    assert "@7" not in header


async def test_header_tgid_has_no_thousands_separators(repo: Repo) -> None:
    """An identifier is not a quantity. Fluent formats a number for the
    locale, so a real id came out as "tg_id 127 383 366" — unsearchable, and
    wrong about what the value is (found 2026-09-13 by capturing the real
    screens). It is passed as a string now."""
    await repo.ensure_user(127383366, "whalerider84", None, None)
    await repo.link_xbox_account(127383366, XUID, "GamerTag", 0)

    text, _markup = await _card(repo, 127383366, locale="ru")

    assert "tg_id 127383366" in text.splitlines()[0]


async def test_xbox_block_shows_id_count_today_and_gamerscore(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    await repo.link_xbox_account(1, XUID, "GamerTag", 500)
    await repo.insert_new_achievements(XUID, [_achievement("1", "xbox_modern")], is_backfill=False)

    text, _markup = await _card(repo, 1, locale="ru")

    block = _block(text, "XBOX:")
    assert "GamerTag" in block[0]
    assert block[1] == f"XUID {XUID}"
    achievements_line = block[3]
    assert "1 достижение" in achievements_line
    assert "сегодня 1" in achievements_line
    assert "gamerscore 500" in achievements_line


async def test_steam_block_shows_id_and_count(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    await repo.link_platform_account(1, "steam", "76561197960287930", "SteamPerson")
    await repo.insert_new_achievements_steam(
        1, "76561197960287930", [_achievement("550", "steam", gamerscore=0)], is_backfill=False
    )

    text, _markup = await _card(repo, 1, locale="ru")

    block = _block(text, "Steam:")
    assert "SteamPerson" in block[0]
    assert block[1] == "id 76561197960287930"
    achievements_line = block[3]
    assert "1 достижение" in achievements_line
    assert "сегодня 1" in achievements_line


async def test_steam_status_line_shows_visibility_not_nickname(repo: Repo) -> None:
    """#5/#novel restructure: the status line is achievement visibility,
    worded like /panel — and does not repeat the nickname already on the
    header line above it (2026-09-08 user request)."""
    await repo.ensure_user(1, "someone")
    await repo.link_platform_account(1, "steam", "76561197960287930", "SteamPerson")
    await repo.set_achievements_visible(1, "steam", True)

    text, _markup = await _card(repo, 1, locale="ru")

    status_line = _block(text, "Steam:")[2]
    assert "ачивки видны" in status_line
    assert "SteamPerson" not in status_line


async def test_psn_block_shows_trophies_wording_and_level(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    await repo.link_platform_account(1, "psn", "acc-1", "PsnPerson")
    await repo.set_psn_trophy_level(1, 42)
    await repo.insert_new_achievements_psn(
        1,
        "acc-1",
        [_achievement("NPWR00001_00", "psn", gamerscore=0)],
        is_backfill=False,
    )

    text, _markup = await _card(repo, 1, locale="ru")

    block = _block(text, "PSN:")
    assert "PsnPerson" in block[0]
    assert block[1] == "account_id acc-1"
    assert len(block) == 5  # PSN now has its own "last online" line too (issue #1)
    achievements_line = block[3]
    assert "1 трофей" in achievements_line
    assert "сегодня 1" in achievements_line
    assert "уровень 42" in achievements_line


async def test_psn_block_shows_last_online_from_the_presence_poller(repo: Repo) -> None:
    """(issue #1) The presence poller (poller/psn_presence.py) now feeds
    this line the same way it already does for Xbox/Steam."""
    await repo.ensure_user(1, "someone")
    await repo.link_platform_account(1, "psn", "acc-1", "PsnPerson")
    await repo.save_psn_presence_state("acc-1", "Online", "CUSA14296_00", "Rust", changed=True)

    text, _markup = await _card(repo, 1, locale="ru")

    online_line = _block(text, "PSN:")[4]
    assert "Rust" in online_line


async def test_psn_status_line_shows_visibility_not_nickname(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    await repo.link_platform_account(1, "psn", "acc-1", "PsnPerson")
    await repo.set_achievements_visible(1, "psn", False)

    text, _markup = await _card(repo, 1, locale="ru")

    status_line = _block(text, "PSN:")[2]
    assert "ачивки скрыты" in status_line
    assert "PsnPerson" not in status_line


async def test_blocks_appear_in_the_one_display_order(repo: Repo) -> None:
    """Xbox, PlayStation, Steam — the same order /panel and /stats use
    (constants.platform_display_rank, owner decision 2026-09-13)."""
    await repo.ensure_user(1, "someone")
    await repo.link_xbox_account(1, XUID, "GamerTag", 0)
    await repo.link_platform_account(1, "steam", "76561197960287930", "SteamPerson")
    await repo.link_platform_account(1, "psn", "acc-1", "PsnPerson")

    text, _markup = await _card(repo, 1, locale="ru")

    assert text.index("XBOX:") < text.index("PSN:") < text.index("Steam:")


async def test_reset_button_appears_next_to_each_connected_platforms_refresh_button(
    repo: Repo,
) -> None:
    await repo.ensure_user(1, "someone")
    await repo.link_xbox_account(1, XUID, "GamerTag", 0)
    await repo.link_platform_account(1, "steam", "76561197960287930", "SteamPerson")
    await repo.link_platform_account(1, "psn", "acc-1", "PsnPerson")

    _text, markup = await _card(repo, 1, locale="ru")

    datas = _callback_datas(markup)
    assert "a:sync:xbox:1" in datas and "a:reset:xbox:1" in datas
    assert "a:sync:steam:1" in datas and "a:reset:steam:1" in datas
    assert "a:sync:psn:1" in datas and "a:reset:psn:1" in datas


async def test_no_reset_buttons_for_platforms_never_connected(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    await repo.link_xbox_account(1, XUID, "GamerTag", 0)

    _text, markup = await _card(repo, 1, locale="ru")

    datas = _callback_datas(markup)
    assert not any(d.startswith("a:reset:steam") or d.startswith("a:reset:psn") for d in datas)


async def test_reset_xbox_data_clears_achievements_and_title_history(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    await repo.link_xbox_account(1, XUID, "GamerTag", 0)
    await repo.insert_new_achievements(
        XUID,
        [_achievement("1", "xbox_modern"), _achievement("2", "xbox_360")],
        is_backfill=False,
    )
    await repo._conn.execute(
        "INSERT INTO title_history "
        "(xuid, title_id, achievements_unlocked, achievements_total, updated_at) "
        "VALUES (?, '1', 1, 3, '2026-01-01T00:00:00+00:00')",
        (XUID,),
    )
    await repo._conn.commit()

    deleted = await repo.reset_xbox_data(1, XUID)

    assert deleted == 2
    assert await repo.xbox_achievement_count(1) == 0
    cursor = await repo._conn.execute("SELECT COUNT(*) FROM title_history WHERE xuid = ?", (XUID,))
    row = await cursor.fetchone()
    assert row[0] == 0


async def test_reset_steam_data_clears_only_that_persons_steam_rows(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    await repo.ensure_user(2, "other")
    await repo.link_platform_account(1, "steam", "111", "Someone")
    await repo.link_platform_account(2, "steam", "222", "Other")
    await repo.insert_new_achievements_steam(
        1, "111", [_achievement("550", "steam", gamerscore=0)], is_backfill=False
    )
    await repo.insert_new_achievements_steam(
        2, "222", [_achievement("550", "steam", gamerscore=0)], is_backfill=False
    )

    # By account, not by person (#52): the rows belong to the account, so
    # that is what a reset addresses.
    deleted = await repo.reset_steam_data("111")

    assert deleted == 1
    assert await repo.platform_achievement_count(1, "steam") == 0
    assert await repo.platform_achievement_count(2, "steam") == 1


async def test_reset_psn_data_clears_achievements_progress_and_backfill_flag(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    await repo.insert_new_achievements_psn(
        1, "acc-1", [_achievement("NPWR00001_00", "psn", gamerscore=0)], is_backfill=True
    )
    await repo.mark_psn_backfill_done("acc-1")
    await repo.set_psn_title_progress("acc-1", "NPWR00001_00", 100)

    deleted = await repo.reset_psn_data(1, "acc-1")

    assert deleted == 1
    assert await repo.platform_achievement_count(1, "psn") == 0
    assert await repo.get_psn_title_progress("acc-1", "NPWR00001_00") is None
    assert await repo.psn_backfill_done("acc-1") is False
