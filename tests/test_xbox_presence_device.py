"""The Xbox device an achievement was earned on comes only from presence
(owner, 2026-09-24) — including the exit poll of a game just left, which was
played on the device presence last reported."""

from __future__ import annotations

from types import SimpleNamespace

from bot.constants import Platform
from bot.db.repo import PollTarget
from bot.poller.presence import PresencePoller


class _FakeFetcher:
    def __init__(self) -> None:
        self.polls: list[tuple[str, str | None]] = []

    async def poll_title(self, tg_id, xuid, gamertag, title_id, platform, title_name, device=None):
        self.polls.append((title_id, device))
        return 0


def _poller(fetcher: _FakeFetcher) -> PresencePoller:
    settings = SimpleNamespace(achievement_poll_interval=60)
    return PresencePoller(settings, None, None, fetcher)  # type: ignore[arg-type]


def _target(device: str | None) -> PollTarget:
    return PollTarget(
        tg_id=1,
        xuid="x",
        state="Online",
        title_id="t-old",
        title_name="Old",
        changed_at=None,
        last_ach_poll_at=None,
        updated_at=None,
        device=device,
    )


async def test_the_exit_poll_uses_the_device_presence_last_reported() -> None:
    fetcher = _FakeFetcher()
    target = _target("Scarlett")

    await _poller(fetcher)._poll_achievements(
        target, "gt", "t-old", "Old", force=True, device=target.device
    )

    assert fetcher.polls == [("t-old", "Scarlett")]


async def test_the_current_game_uses_this_presence_not_an_older_one() -> None:
    fetcher = _FakeFetcher()
    snapshot = SimpleNamespace(platform=Platform.XBOX_MODERN, device="WindowsOneCore")

    await _poller(fetcher)._poll_achievements(
        _target("Scarlett"), "gt", "t-new", "New", force=True, platform_hint=snapshot
    )

    assert fetcher.polls == [("t-new", "WindowsOneCore")]


async def test_no_presence_device_means_no_device() -> None:
    fetcher = _FakeFetcher()

    await _poller(fetcher)._poll_achievements(_target(None), "gt", "t-old", "Old", force=True)

    assert fetcher.polls == [("t-old", None)]
