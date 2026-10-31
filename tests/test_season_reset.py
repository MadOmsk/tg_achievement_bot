"""The one-time wipe of the first season's pass (TEMPORARY, owner, 2026-10-30)."""

from __future__ import annotations

import pytest

from bot.db.repo import Repo
from bot.services import season_reset


async def _fill(repo: Repo) -> int:
    cursor = await repo._conn.execute(
        "INSERT INTO users (tg_id, created_at, updated_at) VALUES (1, '2026-10-01', '2026-10-01')"
        " RETURNING id"
    )
    person = int((await cursor.fetchone())[0])
    for month, kind, palette in (
        ("2026-10", "theme", "ocean"),
        ("2026-10", "code", None),
        ("2026-11", "theme", "mint"),
    ):
        cursor = await repo._conn.execute(
            "INSERT INTO pass_items (kind, palette, points, state, created_at, month)"
            " VALUES (?, ?, 100, 'live', '2026-10-01', ?) RETURNING item_id",
            (kind, palette, month),
        )
        item = int((await cursor.fetchone())[0])
        await repo._conn.execute(
            "INSERT INTO pass_item_codes (item_id, code, person_id, claimed_at)"
            " VALUES (?, 'KEY', ?, '2026-10-02')",
            (item, person),
        )
        await repo._conn.execute(
            "INSERT INTO pass_reached (person_id, item_id, month, reached_at)"
            " VALUES (?, ?, ?, '2026-10-02')",
            (person, item, month),
        )
    await repo._conn.execute("INSERT INTO pass_seasons (month, title) VALUES ('2026-10', 'Zero')")
    await repo._conn.execute("INSERT INTO pass_seasons (month, title) VALUES ('2026-11', 'Two')")
    for palette, month in (("ocean", "2026-10"), ("halloween", "2026-10"), ("mint", "2026-11")):
        await repo._conn.execute(
            "INSERT INTO pass_claims (person_id, palette, month, claimed_at)"
            " VALUES (?, ?, ?, '2026-10-02')",
            (person, palette, month),
        )
    await repo._conn.commit()
    return person


async def _count(repo: Repo, table: str) -> int:
    cursor = await repo._conn.execute(f"SELECT COUNT(*) FROM {table}")
    return int((await cursor.fetchone())[0])


@pytest.mark.asyncio
async def test_the_first_seasons_pass_is_wiped_once_the_second_begins(repo: Repo) -> None:
    await _fill(repo)
    # Not yet: October.
    assert await season_reset.reset_for_second_season(repo, now_month="2026-10") is False
    assert await _count(repo, "pass_items") == 3

    assert await season_reset.reset_for_second_season(repo, now_month="2026-11") is True
    # The first season's levels, codes, claims, reached marks and name are gone;
    # the second season's own stay.
    assert await _count(repo, "pass_items") == 1
    assert await _count(repo, "pass_item_codes") == 1
    assert await _count(repo, "pass_reached") == 1
    assert await _count(repo, "pass_claims") == 1
    assert await _count(repo, "pass_seasons") == 1
    cursor = await repo._conn.execute("SELECT palette FROM pass_claims")
    assert [row[0] for row in await cursor.fetchall()] == ["mint"]

    # Once: a second run finds the marker and touches nothing.
    await repo._conn.execute(
        "INSERT INTO pass_claims (person_id, palette, month, claimed_at)"
        " SELECT person_id, 'rose', '2026-10', '2026-10-30' FROM pass_claims LIMIT 1"
    )
    await repo._conn.commit()
    assert await season_reset.reset_for_second_season(repo, now_month="2026-12") is False
    assert await _count(repo, "pass_claims") == 2
