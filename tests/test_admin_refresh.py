"""/admin's auto-refresh (Follow-up 2026-09-06) — same shape as
test_online_refresh.py, one row per admin instead of per chat, cadence
shared with poller/service_health.py's own key-check interval."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bot.db.repo import Repo
from bot.poller.admin_refresh import AdminPanelRefresh
from bot.poller.service_health import KEY_CHECK_INTERVAL_KEY
from bot.services.crypto import TokenCipher
from bot.services.psn.auth import PsnAuth

ADMIN_ID = 777


class FakeBot:
    def __init__(self, *, fail: bool = False) -> None:
        self.edits: list[tuple[int, int, str]] = []
        self._fail = fail

    async def edit_message_text(
        self, *, chat_id: int, message_id: int, text: str, **kwargs: object
    ) -> None:
        if self._fail:
            raise RuntimeError("message not found")
        self.edits.append((chat_id, message_id, text))


class _FakeUsageFetcher:
    def api_usage(self) -> list[tuple[int, int, float]]:
        return []


async def _backdate(repo: Repo, *, minutes_ago: int) -> None:
    when = (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")
    await repo._conn.execute(
        "UPDATE admin_panel_refresh SET created_at = ?, last_updated_at = ? WHERE admin_id = ?",
        (when, when, ADMIN_ID),
    )
    await repo._conn.commit()


def _refresh(bot: FakeBot, repo: Repo, cipher: TokenCipher) -> AdminPanelRefresh:
    return AdminPanelRefresh(
        bot, repo, _FakeUsageFetcher(), _FakeUsageFetcher(), PsnAuth(repo, cipher)
    )  # type: ignore[arg-type]


async def test_start_supersedes_a_previous_row(repo: Repo) -> None:
    await repo.start_admin_panel_refresh(ADMIN_ID, 1)
    await repo.start_admin_panel_refresh(ADMIN_ID, 2)

    rows = await repo.all_admin_panel_refreshes()

    assert len(rows) == 1
    assert rows[0].message_id == 2


async def test_get_admin_panel_refresh_round_trips(repo: Repo) -> None:
    assert await repo.get_admin_panel_refresh(ADMIN_ID) is None
    await repo.start_admin_panel_refresh(ADMIN_ID, 42)
    row = await repo.get_admin_panel_refresh(ADMIN_ID)
    assert row is not None
    assert row.message_id == 42


async def test_tick_refreshes_a_screen_past_its_interval(repo: Repo, cipher: TokenCipher) -> None:
    await repo.start_admin_panel_refresh(ADMIN_ID, 42)
    await _backdate(repo, minutes_ago=31)

    bot = FakeBot()
    await _refresh(bot, repo, cipher).tick()

    assert len(bot.edits) == 1
    chat_id, message_id, text = bot.edits[0]
    assert (chat_id, message_id) == (ADMIN_ID, 42)
    assert "Администрирование" in text
    rows = await repo.all_admin_panel_refreshes()
    assert rows[0].last_updated_at != rows[0].created_at


async def test_tick_leaves_a_fresh_screen_alone(repo: Repo, cipher: TokenCipher) -> None:
    await repo.start_admin_panel_refresh(ADMIN_ID, 42)
    await _backdate(repo, minutes_ago=1)

    bot = FakeBot()
    await _refresh(bot, repo, cipher).tick()

    assert bot.edits == []


async def test_interval_zero_disables_refreshing(repo: Repo, cipher: TokenCipher) -> None:
    await repo.start_admin_panel_refresh(ADMIN_ID, 42)
    await _backdate(repo, minutes_ago=60)
    await repo.set_app_setting(KEY_CHECK_INTERVAL_KEY, "0", 1)

    bot = FakeBot()
    await _refresh(bot, repo, cipher).tick()

    assert bot.edits == []


async def test_a_failed_edit_stops_tracking_the_admin(repo: Repo, cipher: TokenCipher) -> None:
    await repo.start_admin_panel_refresh(ADMIN_ID, 42)
    await _backdate(repo, minutes_ago=31)

    await _refresh(FakeBot(fail=True), repo, cipher).tick()

    assert await repo.all_admin_panel_refreshes() == []
