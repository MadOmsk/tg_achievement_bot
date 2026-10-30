"""How often each platform's presence (and PSN's trophy scan) is asked
(owner, 2026-10-29; #184 stage 0): global admin settings, one group
per platform in both admin panels, read by the pollers on every tick so a
change needs no restart.

The environment's old `presence_interval_*` and `psn_*_poll_interval`
seed them once (`seed_once`); from then on the panel owns them. Dormancy
starts at its default, 7 days (owner, 2026-10-29), whatever
`catchup_idle_threshold_days` says. Steps are whole minutes: the scheduler ticks once a
minute, so nothing finer could be kept anyway.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.config import Settings
    from bot.db.repo import Repo

PLATFORMS = ("xbox", "steam", "psn")


@dataclass(frozen=True, slots=True)
class Field:
    name: str
    #: An `admin.ftl` key, `admin-setting-poll-<name>`.
    label: str
    min: int
    max: int
    #: Only PSN has a trophy scan of its own.
    psn_only: bool = False


FIELDS: tuple[Field, ...] = (
    Field("in_game", "admin-setting-poll-in-game", 1, 15),
    Field("online", "admin-setting-poll-online", 1, 30),
    Field("offline", "admin-setting-poll-offline", 1, 60),
    Field("idle", "admin-setting-poll-idle", 1, 120),
    Field("idle_after", "admin-setting-poll-idle-after", 10, 2880),
    Field("dormant", "admin-setting-poll-dormant", 1, 120),
    Field("dormant_after", "admin-setting-poll-dormant-after", 1, 90),
    Field("scan_online", "admin-setting-poll-scan-online", 1, 60, psn_only=True),
    Field("scan_offline", "admin-setting-poll-scan-offline", 1, 240, psn_only=True),
    Field("scan_dormant", "admin-setting-poll-scan-dormant", 30, 2880, psn_only=True),
    # Not minutes: how many times rarer an account without its own token is
    # asked (#233) — the shared token is the bottleneck.
    Field("shared_slowdown", "admin-setting-poll-shared-slowdown", 1, 10, psn_only=True),
)


def fields_of(platform: str) -> tuple[Field, ...]:
    return tuple(f for f in FIELDS if platform == "psn" or not f.psn_only)


def key(platform: str, field: str) -> str:
    return f"poll_{platform}_{field}"


def group(platform: str) -> str:
    return f"poll_{platform}"


# Every step in minutes, `dormant_after` in days. Steam is asked in one batch
# for everybody due, so a minute everywhere costs it one request a minute
# (owner, 2026-10-29: D7). "Dormant" is new for presence: an account offline a
# week is asked once an hour — often enough to see it come back the same hour —
# and PSN scans its trophies once a day.
DEFAULTS: dict[str, dict[str, int]] = {
    "xbox": {
        "in_game": 1,
        "online": 2,
        "offline": 5,
        "idle": 15,
        "idle_after": 120,
        "dormant": 60,
        "dormant_after": 7,
    },
    "steam": {
        "in_game": 1,
        "online": 1,
        "offline": 1,
        "idle": 1,
        "idle_after": 120,
        "dormant": 1,
        "dormant_after": 7,
    },
    "psn": {
        "in_game": 1,
        "online": 2,
        "offline": 5,
        "idle": 15,
        "idle_after": 120,
        "dormant": 60,
        "dormant_after": 7,
        "scan_online": 2,
        "scan_offline": 30,
        "scan_dormant": 1440,
        "shared_slowdown": 3,
    },
}


@dataclass(frozen=True, slots=True)
class Cadence:
    """One platform's steps, in seconds (the pollers' unit)."""

    in_game: int
    online: int
    offline: int
    idle: int
    idle_after: int
    dormant: int
    dormant_after_days: int
    scan_online: int = 0
    scan_offline: int = 0
    scan_dormant: int = 0
    #: PSN: an account read with the shared token waits this many times longer.
    shared_slowdown: int = 1


def _minutes(seconds: int) -> int:
    return max(1, math.ceil(seconds / 60))


def _seeds(platform: str, settings: Settings) -> dict[str, int]:
    """What the environment said, where it said anything for this platform.
    Steam's presence steps are not seeded: one batch a minute covers all."""
    seeds = dict(DEFAULTS[platform])
    if platform != "steam":
        seeds["in_game"] = _minutes(settings.presence_interval_in_game)
        seeds["online"] = _minutes(settings.presence_interval_online)
        seeds["offline"] = _minutes(settings.presence_interval_offline)
        seeds["idle"] = _minutes(settings.presence_interval_idle)
    if platform == "psn":
        seeds["scan_online"] = _minutes(settings.achievement_poll_interval)
        seeds["scan_offline"] = _minutes(settings.psn_offline_poll_interval)
        seeds["scan_dormant"] = _minutes(settings.psn_dormant_poll_interval)
    return seeds


async def seed_once(repo: Repo, settings: Settings) -> None:
    """Writes the environment's values for every step not stored yet."""
    for platform in PLATFORMS:
        seeds = _seeds(platform, settings)
        for field in fields_of(platform):
            if await repo.get_app_setting(key(platform, field.name)) is None:
                value = min(max(seeds[field.name], field.min), field.max)
                await repo.set_app_setting(key(platform, field.name), str(value), None)


async def load(repo: Repo, platform: str) -> Cadence:
    """The platform's steps as stored now; a missing or broken value reads as
    its default."""
    minutes: dict[str, int] = {}
    for field in fields_of(platform):
        raw = await repo.get_app_setting(key(platform, field.name))
        try:
            value = int(raw) if raw is not None else DEFAULTS[platform][field.name]
        except ValueError:
            value = DEFAULTS[platform][field.name]
        minutes[field.name] = min(max(value, field.min), field.max)
    return Cadence(
        in_game=minutes["in_game"] * 60,
        online=minutes["online"] * 60,
        offline=minutes["offline"] * 60,
        idle=minutes["idle"] * 60,
        idle_after=minutes["idle_after"] * 60,
        dormant=minutes["dormant"] * 60,
        dormant_after_days=minutes["dormant_after"],
        scan_online=minutes.get("scan_online", 0) * 60,
        scan_offline=minutes.get("scan_offline", 0) * 60,
        scan_dormant=minutes.get("scan_dormant", 0) * 60,
        shared_slowdown=minutes.get("shared_slowdown", 1),
    )
