"""Admin panel PSN parity (#27) — the per-user card gets a 🔄 resync button
for a linked PSN account, mirroring the Xbox/Steam ones it already had."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.handlers.admin import _card

ACCOUNT_ID = "psn-acc-1"


def _callback_datas(markup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row if btn.callback_data]


async def test_card_shows_a_psn_resync_button_when_psn_is_linked(repo: Repo) -> None:
    await repo.ensure_user(1, "igor")
    await repo.link_platform_account(1, "psn", ACCOUNT_ID, "Gamer")

    _text, markup = await _card(repo, 1, locale="ru")

    assert "a:sync:psn:1" in _callback_datas(markup)


async def test_card_has_no_psn_resync_button_without_a_psn_link(repo: Repo) -> None:
    await repo.ensure_user(1, "igor")
    await repo.link_platform_account(1, "steam", "76561197960287930", "SteamOnly")

    _text, markup = await _card(repo, 1, locale="ru")

    datas = _callback_datas(markup)
    assert "a:sync:steam:1" in datas
    assert not any(d.startswith("a:sync:psn:") for d in datas)
