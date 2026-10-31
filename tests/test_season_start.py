"""The season's start told at noon on the 1st, in each person's own time zone."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bot.db.repo import Repo
from bot.i18n import gettext
from bot.poller import season_start
from bot.poller.season_start import SeasonStart
from bot.services import time_zones
from bot.services.notifier import carries, wording

MONTH = "2026-11"
_REAL_LOCAL_NOW = time_zones.local_now


class _Notifier:
    def __init__(self) -> None:
        self.told: list[tuple[int, str]] = []

    async def tell_about_season_start(self, person: int, month: str) -> None:
        self.told.append((person, month))


def _at(monkeypatch: pytest.MonkeyPatch, *when: int) -> None:
    now = datetime(*when, tzinfo=UTC)

    def local_now(tz: object) -> datetime:
        return _REAL_LOCAL_NOW(tz, now)

    monkeypatch.setattr(season_start.time_zones, "local_now", local_now)


async def _person(repo: Repo, tg_id: int, tz_name: str) -> int:
    await repo.ensure_user(tg_id)
    person = await repo.person_id(tg_id)
    await repo.update_user_settings(person, tz_name=tz_name)
    return person


async def _publish(repo: Repo, month: str = MONTH) -> None:
    await repo._conn.execute(
        "INSERT INTO pass_items (kind, points, state, month, created_at)"
        " VALUES ('code', 100, 'live', ?, 'x')",
        (month,),
    )


async def test_noon_comes_in_each_person_s_own_time_zone(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    moscow = await _person(repo, 1, "Europe/Moscow")
    omsk = await _person(repo, 2, "Asia/Omsk")
    await _publish(repo)
    notifier = _Notifier()
    job = SeasonStart(repo, notifier)
    # 06:00 UTC: 12:00 in Omsk (UTC+6), 09:00 in Moscow.
    _at(monkeypatch, 2026, 11, 1, 6, 0)
    await job.tick()
    assert notifier.told == [(omsk, MONTH)]
    # 09:00 UTC: noon in Moscow; Omsk is not told again.
    _at(monkeypatch, 2026, 11, 1, 9, 0)
    await job.tick()
    assert notifier.told == [(omsk, MONTH), (moscow, MONTH)]


async def test_not_before_noon_and_not_on_the_2nd(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _person(repo, 1, "Asia/Omsk")
    await _publish(repo)
    notifier = _Notifier()
    job = SeasonStart(repo, notifier)
    _at(monkeypatch, 2026, 11, 1, 5, 59)
    await job.tick()
    _at(monkeypatch, 2026, 11, 2, 6, 0)
    await job.tick()
    assert notifier.told == []


async def test_who_has_opened_the_pass_is_not_told(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    person = await _person(repo, 1, "Asia/Omsk")
    await _publish(repo)
    await repo.mark_pass_seen(person, MONTH)
    notifier = _Notifier()
    _at(monkeypatch, 2026, 11, 1, 6, 0)
    await SeasonStart(repo, notifier).tick()
    assert notifier.told == []


async def test_nobody_is_told_twice(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    await _person(repo, 1, "Asia/Omsk")
    await _publish(repo)
    notifier = _Notifier()
    _at(monkeypatch, 2026, 11, 1, 6, 0)
    await SeasonStart(repo, notifier).tick()
    # A restart in between: another job, the same record.
    await SeasonStart(repo, notifier).tick()
    assert len(notifier.told) == 1


async def test_an_unpublished_pass_has_not_started(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _person(repo, 1, "Asia/Omsk")
    await repo._conn.execute(
        "INSERT INTO pass_items (kind, points, state, month, created_at)"
        " VALUES ('code', 100, 'draft', ?, 'x')",
        (MONTH,),
    )
    notifier = _Notifier()
    _at(monkeypatch, 2026, 11, 1, 6, 0)
    await SeasonStart(repo, notifier).tick()
    assert notifier.told == []


def test_on_by_default_and_a_channel_can_switch_it_off() -> None:
    assert carries(frozenset(), "season_start", {}, friend=False)
    assert not carries(frozenset({"season_start:off"}), "season_start", {}, friend=False)


def test_the_words() -> None:
    named = wording("season_start", {"title": "Хэллоуин", "named": "yes"}, "ru")
    assert named == "Хэллоуин начался!\nКто первым доберётся до вершины?"
    plain = wording("season_start", {"title": "", "named": "no"}, "ru")
    assert plain.startswith("Новый сезон начался!")
    assert "Who will reach the top first?" in wording(
        "season_start", {"title": "", "named": "no"}, "en"
    )
    assert gettext("notifications", "notification-season-start", locale="en", title="", named="no")
