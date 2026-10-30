"""The super-admin's polling steps (#184 stage 0): seeded once from the
environment, read on every tick, in both admin panels by the registry."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bot.db.repo import Repo
from bot.services import admin_registry, poll_cadence


def _env(**overrides: int) -> SimpleNamespace:
    values = {
        "presence_interval_in_game": 60,
        "presence_interval_online": 120,
        "presence_interval_offline": 300,
        "presence_interval_idle": 900,
        "achievement_poll_interval": 120,
        "psn_offline_poll_interval": 1800,
        "psn_dormant_poll_interval": 86400,
        "catchup_idle_threshold_days": 14,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def test_defaults_before_anything_is_stored(repo: Repo) -> None:
    psn = await poll_cadence.load(repo, "psn")
    assert (psn.in_game, psn.online, psn.offline, psn.idle) == (60, 120, 300, 900)
    assert (psn.scan_online, psn.scan_offline, psn.scan_dormant) == (120, 1800, 86400)
    steam = await poll_cadence.load(repo, "steam")
    assert (steam.in_game, steam.online, steam.offline, steam.idle, steam.dormant) == (
        60,
        60,
        60,
        60,
        60,
    )


async def test_seeded_from_the_environment_once(repo: Repo) -> None:
    await poll_cadence.seed_once(repo, _env(presence_interval_offline=600))  # type: ignore[arg-type]
    assert (await poll_cadence.load(repo, "xbox")).offline == 600
    # Steam's presence steps are not the environment's: one batch covers all.
    assert (await poll_cadence.load(repo, "steam")).offline == 60

    await admin_registry.set_value(repo, "global", "poll_xbox_offline", "7", None)
    await poll_cadence.seed_once(repo, _env(presence_interval_offline=900))  # type: ignore[arg-type]
    assert (await poll_cadence.load(repo, "xbox")).offline == 7 * 60


async def test_a_change_applies_on_the_next_read(repo: Repo) -> None:
    await admin_registry.set_value(repo, "global", "poll_psn_scan_offline", "45", None)
    assert (await poll_cadence.load(repo, "psn")).scan_offline == 45 * 60


async def test_a_broken_value_reads_as_the_default(repo: Repo) -> None:
    await repo.set_app_setting("poll_xbox_in_game", "fast", None)
    assert (await poll_cadence.load(repo, "xbox")).in_game == 60


def test_every_platform_is_a_group_of_both_panels() -> None:
    for platform in poll_cadence.PLATFORMS:
        rows = admin_registry.settings_of("global", poll_cadence.group(platform))
        names = {row.key for row in rows}
        assert poll_cadence.key(platform, "in_game") in names
        assert (poll_cadence.key(platform, "scan_online") in names) == (platform == "psn")
        assert all(row.min >= 1 for row in rows)


async def test_out_of_bounds_is_refused(repo: Repo) -> None:
    with pytest.raises(admin_registry.SettingValueError):
        await admin_registry.set_value(repo, "global", "poll_xbox_in_game", "0", None)
