"""Switching and taking over an account (#52, step 2).

The repo-level rules live in test_accounts.py; this is the layer above —
what a person is told before anything changes, and who gets told after.
"""

from __future__ import annotations

from bot.constants import Platform
from bot.db.repo import AchievementRow, Repo
from bot.handlers.keyboards import switch_keyboard, switch_prompt
from bot.services import relink
from bot.util import utcnow

ALICE, BOB = 1, 2
ACCOUNT_A, ACCOUNT_B = "76561190000000001", "76561190000000002"


def _achievement(achievement_id: str) -> AchievementRow:
    return AchievementRow(
        title_id="550",
        achievement_id=achievement_id,
        name="A",
        description=None,
        icon_url=None,
        unlocked_at=utcnow().isoformat(timespec="seconds"),
        gamerscore=0,
        rarity_percent=None,
        platform="steam",
    )


async def _linked_with(repo: Repo, tg_id: int, account: str, count: int) -> None:
    await repo.ensure_user(tg_id, f"user{tg_id}")
    await repo.link_platform_account(tg_id, Platform.STEAM, account, f"Nick{account[-1]}")
    if count:
        await repo.insert_new_achievements_steam(
            tg_id, account, [_achievement(f"a{i}") for i in range(count)], is_backfill=False
        )


async def test_relinking_the_same_account_is_not_a_switch(repo: Repo) -> None:
    """The common case — running /connect_steam twice, or reconnecting after
    a failure. Asking "are you sure?" there would be noise."""
    await _linked_with(repo, ALICE, ACCOUNT_A, 3)

    preview = await relink.preview(repo, ALICE, Platform.STEAM, ACCOUNT_A)

    assert preview.is_switch is False
    assert preview.taken_from is None


async def test_a_first_link_is_not_a_switch_either(repo: Repo) -> None:
    await repo.ensure_user(ALICE, "alice")
    preview = await relink.preview(repo, ALICE, Platform.STEAM, ACCOUNT_A)
    assert preview.is_switch is False


async def test_switching_reports_what_stops_counting(repo: Repo) -> None:
    await _linked_with(repo, ALICE, ACCOUNT_A, 3)

    preview = await relink.preview(repo, ALICE, Platform.STEAM, ACCOUNT_B)

    assert preview.is_switch is True
    assert preview.current is not None
    assert preview.current.external_id == ACCOUNT_A
    assert preview.current_achievements == 3
    assert preview.incoming_achievements == 0


async def test_a_known_incoming_account_reports_what_comes_back(repo: Repo) -> None:
    """The difference between "this will take a while" and "this is
    instant" — the whole reason relinking is cheap now."""
    await _linked_with(repo, ALICE, ACCOUNT_B, 2)
    await repo.link_platform_account(ALICE, Platform.STEAM, ACCOUNT_A, "NickA")

    preview = await relink.preview(repo, ALICE, Platform.STEAM, ACCOUNT_B)

    assert preview.incoming_achievements == 2


async def test_preview_names_the_current_owner_when_taking_over(repo: Repo) -> None:
    await _linked_with(repo, ALICE, ACCOUNT_A, 1)
    await repo.ensure_user(BOB, "bob")

    preview = await relink.preview(repo, BOB, Platform.STEAM, ACCOUNT_A)

    assert preview.taken_from == ALICE


async def test_taking_someone_elses_account_asks_even_on_a_first_link(repo: Repo) -> None:
    """2026-09-12, user request. Bob has nothing linked, so this is not a
    switch of his own — but it still takes the account away from Alice, and
    that used to happen silently, with only Alice finding out afterwards."""
    await _linked_with(repo, ALICE, ACCOUNT_A, 1)
    await repo.ensure_user(BOB, "bob")

    preview = await relink.preview(repo, BOB, Platform.STEAM, ACCOUNT_A)

    assert preview.is_switch is False
    assert preview.needs_confirmation is True


async def test_a_plain_first_link_still_asks_nothing(repo: Repo) -> None:
    await repo.ensure_user(ALICE, "alice")
    preview = await relink.preview(repo, ALICE, Platform.STEAM, ACCOUNT_A)
    assert preview.needs_confirmation is False


async def test_relinking_your_own_account_still_asks_nothing(repo: Repo) -> None:
    await _linked_with(repo, ALICE, ACCOUNT_A, 3)
    preview = await relink.preview(repo, ALICE, Platform.STEAM, ACCOUNT_A)
    assert preview.needs_confirmation is False


async def test_perform_reports_the_previous_owner_so_they_can_be_told(repo: Repo) -> None:
    await _linked_with(repo, ALICE, ACCOUNT_A, 1)
    await repo.ensure_user(BOB, "bob")

    taken_from = await relink.perform(repo, BOB, Platform.STEAM, ACCOUNT_A, "NickA")

    assert taken_from == ALICE
    assert await repo.account_owner(Platform.STEAM, ACCOUNT_A) == BOB


async def test_taking_over_xbox_drops_the_previous_owners_token(repo: Repo) -> None:
    """The token authorises reading *that account*, which is no longer
    theirs — leaving it would keep the bot polling on behalf of someone who
    does not hold the account."""
    await repo.ensure_user(ALICE, "alice")
    await repo.ensure_user(BOB, "bob")
    await repo.link_xbox_account(ALICE, "xuid-1", "Someone", 0)
    await repo.save_refresh_token(ALICE, b"encrypted-token")
    assert await repo.get_token(ALICE) is not None

    taken_from = await relink.perform(repo, BOB, "xbox", "xuid-1", "Someone")

    assert taken_from == ALICE
    assert await repo.get_token(ALICE) is None


async def test_switch_prompt_mentions_the_known_history_only_when_there_is_some(i18n) -> None:
    without = switch_prompt(
        relink.LinkPreview(
            current=None,
            current_achievements=4,
            incoming_achievements=0,
            taken_from=None,
            incoming_id=ACCOUNT_B,
        ),
        "Steam",
        "NickB",
        i18n,
    )
    assert "NickB" in without
    assert "заново" not in without
    assert "⚠️" not in without  # nobody else holds it

    with_history = switch_prompt(
        relink.LinkPreview(
            current=None,
            current_achievements=4,
            incoming_achievements=7,
            taken_from=None,
            incoming_id=ACCOUNT_B,
        ),
        "Steam",
        "NickB",
        i18n,
    )
    assert "7" in with_history


def test_switch_prompt_warns_when_the_account_belongs_to_someone_else(i18n) -> None:
    text = switch_prompt(
        relink.LinkPreview(
            current=None,
            current_achievements=0,
            incoming_achievements=0,
            taken_from=BOB,
            incoming_id=ACCOUNT_A,
        ),
        "Steam",
        "NickA",
        i18n,
    )
    assert "⚠️" in text
    # Never who — that is a third party's identity (owner decision).
    assert str(BOB) not in text


def test_switch_keyboard_carries_the_platform_in_its_callbacks(i18n) -> None:
    rows = switch_keyboard("psn", i18n).inline_keyboard
    assert [row[0].callback_data for row in rows] == ["psn:switch:yes", "psn:switch:no"]
