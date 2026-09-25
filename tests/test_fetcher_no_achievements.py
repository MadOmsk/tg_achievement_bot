"""The Xbox poller stops asking about titles with no achievements (#122)."""

from __future__ import annotations

from bot.constants import Platform
from bot.poller.fetcher import Fetcher


class _Client:
    def __init__(self) -> None:
        self.asked: list[str] = []

    async def title_achievements_with_total(self, tg_id, title_id, platform, **kwargs):
        self.asked.append(title_id)
        return [], 0  # every contract answered empty


async def test_title_zero_is_never_asked_about(repo) -> None:
    client = _Client()
    fetcher = Fetcher(repo, client, None, anthropic_auth=None)  # type: ignore[arg-type]

    assert await fetcher.poll_title(1, "xuid", "gt", "0", Platform.XBOX_MODERN, None) == 0
    assert client.asked == []


async def test_a_title_with_no_achievements_is_asked_once(repo) -> None:
    client = _Client()
    fetcher = Fetcher(repo, client, None, anthropic_auth=None)  # type: ignore[arg-type]

    for _ in range(3):
        await fetcher.poll_title(1, "xuid", "gt", "1694119475", Platform.XBOX_MODERN, None)

    assert client.asked == ["1694119475"]
