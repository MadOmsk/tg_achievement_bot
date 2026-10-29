"""poller/cadence.py — shared timing math, extracted out of presence.py and
steam_presence.py (they used to duplicate this byte-for-byte). Covered
indirectly through both pollers' own tests too, but pure functions this
small deserve direct coverage rather than only being exercised as a side
effect of a full tick().
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bot.poller.cadence import debounce_passed, is_due, presence_interval
from bot.services.poll_cadence import Cadence

NOW = datetime.now(UTC)

CADENCE = Cadence(
    in_game=60,
    online=120,
    offline=300,
    idle=900,
    idle_after=7200,
    dormant=1800,
    dormant_after_days=14,
)


def _ago(seconds: float) -> str:
    return (NOW - timedelta(seconds=seconds)).isoformat()


def test_is_due_when_never_updated() -> None:
    assert is_due(None, 120) is True


def test_is_due_respects_the_interval() -> None:
    assert is_due(_ago(200), 120) is True
    assert is_due(_ago(10), 120) is False


def test_debounce_passed_when_never_polled() -> None:
    assert debounce_passed(None, 120) is True


def test_debounce_passed_respects_the_interval() -> None:
    assert debounce_passed(_ago(200), 120) is True
    assert debounce_passed(_ago(10), 120) is False


def _interval(*, online: bool, in_game: bool = False, changed_at: str | None = None) -> int:
    return presence_interval(online=online, in_game=in_game, changed_at=changed_at, cadence=CADENCE)


def test_presence_interval_online_in_game() -> None:
    assert _interval(online=True, in_game=True) == 60


def test_presence_interval_online_not_in_game() -> None:
    assert _interval(online=True) == 120


def test_presence_interval_offline_recently() -> None:
    assert _interval(online=False, changed_at=_ago(60)) == 300


def test_presence_interval_idle_after_a_long_offline_stretch() -> None:
    assert _interval(online=False, changed_at=_ago(CADENCE.idle_after + 60)) == 900


def test_presence_interval_dormant_after_days_offline() -> None:
    """New with the settings (#184 stage 0): an account offline for the
    dormancy threshold is asked on the dormant step."""
    assert _interval(online=False, changed_at=_ago(15 * 86400)) == 1800


def test_presence_interval_offline_with_no_changed_at_is_not_idle() -> None:
    """No changed_at at all reads as "just now" (offline_for = 0), not as
    idle — same defensive default the pollers relied on before extraction."""
    assert _interval(online=False) == 300
