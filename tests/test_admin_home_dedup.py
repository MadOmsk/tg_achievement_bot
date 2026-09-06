"""handlers/admin.py's _replace_admin_home (Follow-up 2026-09-06) — a fresh
/admin (or a settings-change confirmation redrawing home as a new message)
replaces whatever this admin had open before and arms the auto-refresh job,
same dedup+track shape as services/single_message.py but with its own
dedicated table (admin_panel_refresh) since it also auto-refreshes on a
timer, unlike the plain kinds tracked_messages covers."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.handlers.admin import _replace_admin_home
from bot.poller.service_health import KEY_CHECK_INTERVAL_KEY
from bot.services.crypto import TokenCipher
from bot.services.psn.auth import PsnAuth

ADMIN_ID = 777


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.deleted: list[tuple[int, int]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> _FakeMessage:
        message_id = len(self.sent) + 1
        self.sent.append((chat_id, text))
        return _FakeMessage(message_id)

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        self.deleted.append((chat_id, message_id))


class _FakeMessage:
    def __init__(self, message_id: int) -> None:
        self.message_id = message_id


class _FakeUsageFetcher:
    def api_usage(self) -> list[tuple[int, int, float]]:
        return []


async def test_first_call_has_nothing_to_delete_and_arms_refresh(
    repo: Repo, cipher: TokenCipher
) -> None:
    bot = FakeBot()

    await _replace_admin_home(
        bot, repo, _FakeUsageFetcher(), _FakeUsageFetcher(), PsnAuth(repo, cipher), ADMIN_ID
    )  # type: ignore[arg-type]

    assert bot.deleted == []
    assert len(bot.sent) == 1
    row = await repo.get_admin_panel_refresh(ADMIN_ID)
    assert row is not None
    assert row.message_id == 1


async def test_second_call_replaces_the_first(repo: Repo, cipher: TokenCipher) -> None:
    bot = FakeBot()
    psn_auth = PsnAuth(repo, cipher)

    await _replace_admin_home(
        bot, repo, _FakeUsageFetcher(), _FakeUsageFetcher(), psn_auth, ADMIN_ID
    )  # type: ignore[arg-type]
    await _replace_admin_home(
        bot, repo, _FakeUsageFetcher(), _FakeUsageFetcher(), psn_auth, ADMIN_ID
    )  # type: ignore[arg-type]

    assert bot.deleted == [(ADMIN_ID, 1)]
    row = await repo.get_admin_panel_refresh(ADMIN_ID)
    assert row is not None
    assert row.message_id == 2


async def test_prefix_is_prepended_to_the_home_text(repo: Repo, cipher: TokenCipher) -> None:
    bot = FakeBot()

    await _replace_admin_home(
        bot,
        repo,
        _FakeUsageFetcher(),
        _FakeUsageFetcher(),
        PsnAuth(repo, cipher),
        ADMIN_ID,
        prefix="Строк в /summary: 10",
    )  # type: ignore[arg-type]

    assert bot.sent[0][1].startswith("Строк в /summary: 10\n\n")


async def test_interval_zero_sends_but_does_not_arm_refresh(
    repo: Repo, cipher: TokenCipher
) -> None:
    await repo.set_app_setting(KEY_CHECK_INTERVAL_KEY, "0", 1)
    bot = FakeBot()

    await _replace_admin_home(
        bot, repo, _FakeUsageFetcher(), _FakeUsageFetcher(), PsnAuth(repo, cipher), ADMIN_ID
    )  # type: ignore[arg-type]

    assert len(bot.sent) == 1
    assert await repo.get_admin_panel_refresh(ADMIN_ID) is None
