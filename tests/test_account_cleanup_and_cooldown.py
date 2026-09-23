"""Tests for complete platform account cleanup on user deletion and anti-abuse cooldowns."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from bot.constants import Platform, SettingKey
from bot.db.repo import AchievementRow, Repo
from bot.util import utcnow, utcnow_iso

ALICE, BOB = 1001, 1002
XBOX_XUID = "2533274790000001"
STEAM_ID = "76561190000000001"
PSN_ID = "psn_account_001"


def _achievement(
    platform: str = "steam",
    xuid: str = STEAM_ID,
    achievement_id: str = "a1",
    title_id: str = "550",
) -> AchievementRow:
    return AchievementRow(
        title_id=title_id,
        achievement_id=achievement_id,
        name="Test Achievement",
        description="Description",
        icon_url="https://example.com/icon.png",
        unlocked_at=utcnow_iso(),
        gamerscore=10,
        rarity_percent=5.0,
        platform=platform,
    )


async def test_delete_user_cleans_platform_accounts_and_achievements(
    repo: Repo, tmp_path: Path, monkeypatch
) -> None:
    """Deleting a user wipes all orphaned platform accounts, seen achievements,
    publications, title history, presence/poll state, and local avatar files."""
    monkeypatch.setattr("bot.services.avatars.avatar_dir", lambda: tmp_path)

    await repo.ensure_user(ALICE, "alice")
    await repo.link_xbox_account(ALICE, XBOX_XUID, "AliceXbox", 100)
    await repo.link_platform_account(ALICE, Platform.STEAM, STEAM_ID, "AliceSteam")
    await repo.link_platform_account(ALICE, Platform.PSN, PSN_ID, "AlicePSN")

    # Insert achievements for all three
    await repo.insert_new_achievements(
        XBOX_XUID,
        [_achievement(platform="xbox_modern", xuid=XBOX_XUID, achievement_id="x1", title_id="101")],
        is_backfill=False,
    )
    await repo.insert_new_achievements_steam(
        ALICE,
        STEAM_ID,
        [_achievement(platform="steam", xuid=STEAM_ID, achievement_id="s1", title_id="201")],
        is_backfill=False,
    )
    await repo.insert_new_achievements_psn(
        ALICE,
        PSN_ID,
        [_achievement(platform="psn", xuid=PSN_ID, achievement_id="p1", title_id="NPWR001")],
        is_backfill=False,
    )

    # Insert publications
    await repo.record_publication(10, XBOX_XUID, "101", "x1", 1001)
    await repo.record_publication(10, STEAM_ID, "201", "s1", 1002)
    await repo.record_publication(10, PSN_ID, "NPWR001", "p1", 1003)

    # Insert title history
    await repo._conn.execute(
        "INSERT INTO title_history (xuid, title_id, updated_at) VALUES (?, ?, ?)",
        (XBOX_XUID, "101", utcnow_iso()),
    )
    await repo._conn.commit()

    # Insert presence state
    await repo.save_presence_state(XBOX_XUID, "Online", "101", "Game1", changed=True)
    await repo.save_steam_presence_state(STEAM_ID, 1, "201", "Game2", changed=True)
    await repo.save_psn_presence_state(PSN_ID, "Online", "NPWR001", "Game3", changed=True)
    await repo.set_psn_title_progress(PSN_ID, "NPWR001", 50)
    await repo.mark_psn_backfill_done(PSN_ID)

    # Create dummy avatar file
    avatar_file = tmp_path / f"steam_{STEAM_ID}.jpg"
    avatar_file.write_bytes(b"avatar-bytes")
    await repo.set_account_avatar(
        Platform.STEAM, STEAM_ID, "http://example.com/avatar.jpg", avatar_file.name, "hash123"
    )

    # Verify everything exists before deletion
    assert await repo.account_has_history("xbox", XBOX_XUID) is True
    assert await repo.account_has_history("steam", STEAM_ID) is True
    assert await repo.account_has_history("psn", PSN_ID) is True
    assert avatar_file.is_file() is True

    # Delete user
    deleted = await repo.delete_user(ALICE)
    assert deleted is True

    # Verify platform data is completely purged
    assert await repo.account_has_history("xbox", XBOX_XUID) is False
    assert await repo.account_has_history("steam", STEAM_ID) is False
    assert await repo.account_has_history("psn", PSN_ID) is False
    assert await repo.account_owner("xbox", XBOX_XUID) is None
    assert await repo.account_owner("steam", STEAM_ID) is None
    assert await repo.account_owner("psn", PSN_ID) is None
    assert not avatar_file.exists()


async def test_delete_user_preserves_platform_account_if_held_by_another_owner(
    repo: Repo,
) -> None:
    """If another user currently actively holds the platform account, deleting ALICE
    does not delete the account or its achievements."""
    await repo.ensure_user(ALICE, "alice")
    await repo.ensure_user(BOB, "bob")

    await repo.link_platform_account(ALICE, Platform.STEAM, STEAM_ID, "AliceSteam")
    await repo.insert_new_achievements_steam(
        ALICE,
        STEAM_ID,
        [_achievement(platform="steam", xuid=STEAM_ID, achievement_id="s1", title_id="201")],
        is_backfill=False,
    )

    # BOB takes over the account
    await repo.link_platform_account(BOB, Platform.STEAM, STEAM_ID, "BobSteam")
    assert await repo.account_owner("steam", STEAM_ID) == BOB

    # ALICE deletes her bot account
    await repo.delete_user(ALICE)

    # Account and achievements still exist for BOB
    assert await repo.account_owner("steam", STEAM_ID) == BOB
    assert await repo.account_has_history("steam", STEAM_ID) is True


async def test_cooldown_first_reset_allows_immediate_relink(repo: Repo) -> None:
    """1st account deletion allows immediate re-linking (1 free relink)."""
    await repo.ensure_user(ALICE, "alice")
    await repo.link_xbox_account(ALICE, XBOX_XUID, "AliceXbox", 50)

    # 1st deletion by user
    await repo.delete_user(ALICE, is_admin=False)

    # Check cooldown
    check = await repo.check_platform_cooldown(ALICE, "xbox", XBOX_XUID)
    assert check.is_blocked is False
    assert check.reset_count == 1


async def test_cooldown_second_reset_blocks_relink(repo: Repo) -> None:
    """2nd account deletion within the cooldown window triggers blocking."""
    await repo.ensure_user(ALICE, "alice")
    await repo.link_xbox_account(ALICE, XBOX_XUID, "AliceXbox", 50)

    # 1st deletion
    await repo.delete_user(ALICE, is_admin=False)

    # ALICE returns and links again
    await repo.ensure_user(ALICE, "alice")
    await repo.link_xbox_account(ALICE, XBOX_XUID, "AliceXbox", 50)

    # 2nd deletion within window
    await repo.delete_user(ALICE, is_admin=False)

    # Now blocked!
    check = await repo.check_platform_cooldown(ALICE, "xbox", XBOX_XUID)
    assert check.is_blocked is True
    assert check.reset_count == 2
    assert check.remaining_seconds > 0
    assert check.remaining_seconds <= 24 * 3600


async def test_cooldown_per_platform_isolation(repo: Repo) -> None:
    """Cooldowns are tracked independently per platform (xbox, steam, psn)."""
    await repo.ensure_user(ALICE, "alice")
    await repo.link_xbox_account(ALICE, XBOX_XUID, "AliceXbox", 50)

    # 1st reset Xbox
    await repo.delete_user(ALICE, is_admin=False)
    # 2nd reset Xbox
    await repo.ensure_user(ALICE, "alice")
    await repo.link_xbox_account(ALICE, XBOX_XUID, "AliceXbox", 50)
    await repo.delete_user(ALICE, is_admin=False)

    # Xbox is blocked
    check_xbox = await repo.check_platform_cooldown(ALICE, "xbox", XBOX_XUID)
    assert check_xbox.is_blocked is True

    # Steam and PSN are NOT blocked
    check_steam = await repo.check_platform_cooldown(ALICE, Platform.STEAM, STEAM_ID)
    assert check_steam.is_blocked is False

    check_psn = await repo.check_platform_cooldown(ALICE, Platform.PSN, PSN_ID)
    assert check_psn.is_blocked is False


async def test_cooldown_blocks_by_external_id_across_different_tg_ids(repo: Repo) -> None:
    """A user cannot bypass the cooldown by deleting their account and using
    a different Telegram user to link the same platform account."""
    await repo.ensure_user(ALICE, "alice")
    await repo.link_platform_account(ALICE, Platform.STEAM, STEAM_ID, "AliceSteam")

    # 2 resets for ALICE
    await repo.delete_user(ALICE, is_admin=False)
    await repo.ensure_user(ALICE, "alice")
    await repo.link_platform_account(ALICE, Platform.STEAM, STEAM_ID, "AliceSteam")
    await repo.delete_user(ALICE, is_admin=False)

    # BOB tries to link the same STEAM_ID
    check_bob = await repo.check_platform_cooldown(BOB, Platform.STEAM, STEAM_ID)
    assert check_bob.is_blocked is True


async def test_cooldown_setting_zero_disables_cooldown(repo: Repo) -> None:
    """Setting account_reset_cooldown_hours = 0 disables the cooldown completely."""
    await repo.set_app_setting(SettingKey.ACCOUNT_RESET_COOLDOWN_HOURS, "0", updated_by=None)

    await repo.ensure_user(ALICE, "alice")
    await repo.link_xbox_account(ALICE, XBOX_XUID, "AliceXbox", 50)
    await repo.delete_user(ALICE, is_admin=False)

    await repo.ensure_user(ALICE, "alice")
    await repo.link_xbox_account(ALICE, XBOX_XUID, "AliceXbox", 50)
    await repo.delete_user(ALICE, is_admin=False)

    check = await repo.check_platform_cooldown(ALICE, "xbox", XBOX_XUID)
    assert check.is_blocked is False


async def test_admin_deletion_exempt_from_cooldown(repo: Repo) -> None:
    """Admin operations (is_admin=True) do not impose cooldowns and clear existing ones."""
    await repo.ensure_user(ALICE, "alice")
    await repo.link_xbox_account(ALICE, XBOX_XUID, "AliceXbox", 50)

    # User deletion creates 1 reset
    await repo.delete_user(ALICE, is_admin=False)
    # Admin deletion clears cooldown
    await repo.ensure_user(ALICE, "alice")
    await repo.link_xbox_account(ALICE, XBOX_XUID, "AliceXbox", 50)
    await repo.delete_user(ALICE, is_admin=True)

    check = await repo.check_platform_cooldown(ALICE, "xbox", XBOX_XUID)
    assert check.is_blocked is False
    assert check.reset_count == 0


async def test_expired_cooldown_allows_relink(repo: Repo) -> None:
    """After the cooldown period has elapsed, linking is permitted."""
    await repo.ensure_user(ALICE, "alice")
    await repo.link_xbox_account(ALICE, XBOX_XUID, "AliceXbox", 50)
    await repo.delete_user(ALICE, is_admin=False)

    # Manually backdate the reset timestamp to 25 hours ago
    past_iso = (utcnow() - timedelta(hours=25)).isoformat(timespec="seconds")
    await repo._conn.execute(
        "UPDATE platform_cooldowns SET reset_count = 2, last_reset_at = ? WHERE tg_id = ?",
        (past_iso, ALICE),
    )
    await repo._conn.commit()

    check = await repo.check_platform_cooldown(ALICE, "xbox", XBOX_XUID)
    assert check.is_blocked is False
