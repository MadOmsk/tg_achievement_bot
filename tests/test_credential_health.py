"""services/credential_health.py — what one failed liveness check means (#62).

The three shared credentials share this, so it is tested once here and only
each wrapper's own wiring is tested in its own file.
"""

from __future__ import annotations

from bot.constants import TokenStatus
from bot.db.repo import Repo
from bot.services.credential_health import FAILURES_BEFORE_DEAD, CredentialHealth

STATUS_KEY = "test_key_status"
CHECKED_AT_KEY = "test_key_checked_at"


def _health(repo: Repo) -> CredentialHealth:
    return CredentialHealth(repo, STATUS_KEY, CHECKED_AT_KEY, label="test")


async def test_the_whole_life_of_one_false_alarm(repo: Repo) -> None:
    """The 2026-09-15 incident, start to finish: Sony answered one check
    with a 401, everything was fine a minute later. Nobody should hear
    about it at all."""
    dead = 0
    alive = 0

    async def _on_dead() -> None:
        nonlocal dead
        dead += 1

    async def _on_alive() -> None:
        nonlocal alive
        alive += 1

    health = _health(repo)
    await health.record(True, on_dead=_on_dead, on_alive=_on_alive)
    await health.record(False, on_dead=_on_dead, on_alive=_on_alive)
    await health.record(True, on_dead=_on_dead, on_alive=_on_alive)

    assert (dead, alive) == (0, 0)
    assert await repo.get_app_setting(STATUS_KEY) == TokenStatus.ACTIVE


async def test_a_real_death_is_reported_once_confirmed(repo: Repo) -> None:
    fired = 0

    async def _on_dead() -> None:
        nonlocal fired
        fired += 1

    health = _health(repo)
    for _ in range(FAILURES_BEFORE_DEAD - 1):
        assert await health.record(False, on_dead=_on_dead) is False
        assert await repo.get_app_setting(STATUS_KEY) is None  # nothing written yet

    await health.record(False, on_dead=_on_dead)

    assert fired == 1
    assert await repo.get_app_setting(STATUS_KEY) == TokenStatus.INVALID


async def test_an_unconfirmed_failure_does_not_move_checked_at(repo: Repo) -> None:
    """poller/service_health.py gates on this timestamp, so leaving it alone
    is what makes the retry happen on the next tick instead of after the
    whole interval — the retry being the entire point."""
    health = _health(repo)
    await health.record(True)
    first = await repo.get_app_setting(CHECKED_AT_KEY)

    await health.record(False)

    assert await repo.get_app_setting(CHECKED_AT_KEY) == first


async def test_recovery_after_a_confirmed_death_is_announced(repo: Repo) -> None:
    alive = 0

    async def _on_alive() -> None:
        nonlocal alive
        alive += 1

    health = _health(repo)
    for _ in range(FAILURES_BEFORE_DEAD):
        await health.record(False)
    assert await repo.get_app_setting(STATUS_KEY) == TokenStatus.INVALID

    await health.record(True, on_alive=_on_alive)
    await health.record(True, on_alive=_on_alive)

    assert alive == 1  # the transition, not every healthy check after it
    assert await repo.get_app_setting(STATUS_KEY) == TokenStatus.ACTIVE


async def test_a_confirmed_death_keeps_its_status_while_it_lasts(repo: Repo) -> None:
    """Once dead, every further failure writes the status and the timestamp
    again — the /admin card should show a check that really is happening,
    and at the ordinary interval rather than every minute."""
    health = _health(repo)
    for _ in range(FAILURES_BEFORE_DEAD):
        await health.record(False)
    first = await repo.get_app_setting(CHECKED_AT_KEY)
    assert first is not None

    await health.record(False)

    assert await repo.get_app_setting(STATUS_KEY) == TokenStatus.INVALID
    assert await repo.get_app_setting(CHECKED_AT_KEY) is not None
